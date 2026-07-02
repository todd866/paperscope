"""Regression test: dogfood the systematic_review module against a working review.

Loads a working scoping review's extraction.jsonl + screening.jsonl +
records.jsonl through the new generic pipeline and asserts the aggregations +
PRISMA flow reproduce that review's working synthesis-tables.json — proving the
port is faithful.

Two run modes:
  python tests/test_systematic_review.py    # standalone script, prints PASS/FAIL
  pytest tests/test_systematic_review.py    # under pytest

The review corpus is a private caller's and is not shipped with the repo. Point
the PAPERSCOPE_SR_CORPUS environment variable at a directory holding the
review's extraction.jsonl / screening.jsonl / records.jsonl /
synthesis-tables.json to run the regression (check via
_corpus_inputs_available); if it is unset or the inputs are missing, the tests
skip gracefully.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from paperscope.systematic_review import ReviewConfig, load_jsonl  # noqa: E402
from paperscope.systematic_review.synthesise import aggregate, prisma_flow  # noqa: E402


# The private review corpus is supplied by the caller, not committed here. Read
# its location from an env var; default to a placeholder path that does not
# exist so the test skips cleanly when the corpus is absent.
_CORPUS_ENV = "PAPERSCOPE_SR_CORPUS"
_PLACEHOLDER_CORPUS = "/nonexistent/paperscope-sr-corpus"
CORPUS_DIR = Path(os.environ.get(_CORPUS_ENV, _PLACEHOLDER_CORPUS)).expanduser()
REVIEW_YAML = ROOT / "paperscope/systematic_review/examples/example-review.yaml"


def _corpus_inputs_available() -> bool:
    return (
        (CORPUS_DIR / "extraction.jsonl").exists()
        and (CORPUS_DIR / "screening.jsonl").exists()
        and (CORPUS_DIR / "records.jsonl").exists()
        and (CORPUS_DIR / "synthesis-tables.json").exists()
    )


# Pytest: skip the whole module if the review data isn't on disk. This is an
# integration test against an external, private corpus; it can't run in CI or on
# a fresh machine without those files. Script mode does its own check in
# `_run_all_as_script`. The try/except keeps the file importable when pytest
# isn't installed (e.g. running as a plain script).
try:
    import pytest as _pytest  # noqa: E402

    pytestmark = _pytest.mark.skipif(
        not _corpus_inputs_available(),
        reason=f"review corpus not available (set {_CORPUS_ENV})",
    )
except ImportError:
    pass


_CACHE: dict = {}


def _load() -> tuple[list, list, list, dict, dict]:
    if "loaded" not in _CACHE:
        extraction = load_jsonl(CORPUS_DIR / "extraction.jsonl")
        screening = load_jsonl(CORPUS_DIR / "screening.jsonl")
        records = load_jsonl(CORPUS_DIR / "records.jsonl")
        old_tables = json.loads((CORPUS_DIR / "synthesis-tables.json").read_text())
        cfg = ReviewConfig.from_yaml(REVIEW_YAML)
        new_tables = aggregate(extraction, cfg.aggregation)
        _CACHE["loaded"] = (extraction, screening, records, old_tables, new_tables)
    return _CACHE["loaded"]


def _norm_rows(rows: list) -> list:
    """Order-insensitive row-list comparison: convert each dict to a frozen,
    sorted tuple of items."""
    return sorted(tuple(sorted(r.items())) for r in rows)


# --- the regression assertions ---------------------------------------------


def test_corpus_size():
    _, _, _, old, new = _load()
    # New pipeline reproduces the review's own corpus count (whatever it is).
    assert new["corpus_n"] == old["corpus_n"]
    assert new["corpus_n"] > 0


def test_lead_time_summary():
    _, _, _, old, new = _load()
    n, o = new["lead_time"], old["lead_time"]
    assert n["n_studies_with_figure"] == o["n_studies_with_figure"]
    assert n["n_extracted_values"] == o["n_extracted_values"]
    assert n["min"] == o["min_hours"]
    assert n["max"] == o["max_hours"]
    assert n["median_of_reported"] == o["median_of_reported"]
    assert n["values_in_6_to_48_band"] == o["values_6_to_48h"]


def test_lead_time_detail_rows():
    _, _, _, old, new = _load()
    # The detail rows carry pmid + (renamed) tier/design + text — same set
    # of pmids should appear in both
    new_pmids = {r["pmid"] for r in new["lead_time_detail"]}
    old_pmids = {r["pmid"] for r in old["lead_time_detail"]}
    assert new_pmids == old_pmids


def test_warning_indicators_top40():
    _, _, _, old, new = _load()
    # JSON serialisation makes both lists-of-[str,int]; compare directly
    assert new["warning_indicators_top40"] == old["warning_indicators_top40"]


def test_confounders_top40_and_drops():
    _, _, _, old, new = _load()
    assert new["confounders_top40"] == old["confounders_top40"]
    assert (
        new["confounders_index_labels_dropped"]
        == old["confounders_index_labels_dropped"]
    )


def test_themes():
    _, _, _, old, new = _load()
    assert new["themes"] == old["themes"]


def test_designs():
    _, _, _, old, new = _load()
    assert new["designs"] == old["designs"]


def test_tiers():
    _, _, _, old, new = _load()
    assert new["tiers"] == old["tiers"]


def test_countries_top15():
    _, _, _, old, new = _load()
    assert new["countries_top15"] == old["countries_top15"]


def test_region_breakdowns():
    _, _, _, old, new = _load()
    assert _norm_rows(new["region_breakdowns"]) == _norm_rows(old["region_breakdowns"])


def test_impact_texts():
    _, _, _, old, new = _load()
    assert _norm_rows(new["impact_texts"]) == _norm_rows(old["impact_texts"])


def test_model_forecast_by_category():
    _, _, _, old, new = _load()
    assert new["model_forecast_by_category"] == old["model_forecast"]["by_category"]


def test_model_forecast_charted_bool_matches():
    _, _, _, old, new = _load()
    # "charted" is derivable: any category other than "uncharted" appears
    derived_charted = any(
        c != "uncharted" for c in new["model_forecast_by_category"]
    )
    assert derived_charted == old["model_forecast"]["charted"]


def test_model_validation_texts():
    _, _, _, old, new = _load()
    assert _norm_rows(new["model_validation_texts"]) == _norm_rows(
        old["model_forecast"]["validation_texts"]
    )


def test_prisma_flow_pilot_numbers():
    _, screening, records, _, _ = _load()
    flow = prisma_flow(records=records, screening=screening)
    # MEDLINE-only pilot, no cross-database dedup needed. Assert the funnel is
    # internally consistent rather than hardcoding the (private) corpus counts:
    # every identified record is screened and gets one decision, and the
    # include / exclude / maybe piles partition the screened set.
    assert flow["identified_total"] == flow["screened"] == flow["screened_decisions"]
    assert flow["identified_total"] > 0
    assert (
        flow["included_for_charting"]
        + flow["excluded_at_title_abstract"]
        + flow["maybe_full_text_needed"]
        == flow["screened_decisions"]
    )
    assert flow["included_for_charting"] > 0


# --- script mode -----------------------------------------------------------


def _run_all_as_script() -> int:
    if not _corpus_inputs_available():
        print(f"SKIP: review corpus not found (set {_CORPUS_ENV})")
        return 0
    tests = sorted(
        [(k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)]
    )
    failed: list[tuple[str, str]] = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append((name, str(e) or "assertion failed"))
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ERR   {name}: {type(e).__name__}: {e}")
    print()
    if failed:
        print(f"FAILED  {len(failed)} / {len(tests)}")
        return 1
    print(f"PASSED  {len(tests)} / {len(tests)}")
    return 0


if __name__ == "__main__":
    sys.exit(_run_all_as_script())
