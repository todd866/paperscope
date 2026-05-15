"""Regression test: dogfood the systematic_review module against the MND review.

Loads md-project's extraction.jsonl + screening.jsonl + records.jsonl through
the new generic pipeline and asserts the aggregations + PRISMA flow reproduce
md-project's working synthesis-tables.json — proving the port is faithful.

Two run modes:
  python tests/test_systematic_review.py    # standalone script, prints PASS/FAIL
  pytest tests/test_systematic_review.py    # under pytest

The MND review materials must be at ~/Desktop/medicine/md-project/lit-review/corpus/
(check via _md_inputs_available); if missing, the tests skip gracefully.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from paperscope.systematic_review import ReviewConfig, load_jsonl  # noqa: E402
from paperscope.systematic_review.synthesise import aggregate, prisma_flow  # noqa: E402


MD_PROJECT = Path.home() / "Desktop/medicine/md-project"
MND_CORPUS = MD_PROJECT / "lit-review/corpus"
MND_YAML = ROOT / "paperscope/systematic_review/examples/mnd-pilot.yaml"


def _md_inputs_available() -> bool:
    return (
        (MND_CORPUS / "extraction.jsonl").exists()
        and (MND_CORPUS / "screening.jsonl").exists()
        and (MND_CORPUS / "records.jsonl").exists()
        and (MND_CORPUS / "synthesis-tables.json").exists()
    )


# Pytest: skip the whole module if the MND review data isn't on disk. This is
# an integration test against an external corpus; it can't run in CI or on a
# fresh machine without those files. Script mode does its own check in
# `_run_all_as_script`. The try/except keeps the file importable when pytest
# isn't installed (e.g. running as a plain script).
try:
    import pytest as _pytest  # noqa: E402

    pytestmark = _pytest.mark.skipif(
        not _md_inputs_available(),
        reason=f"MND review data not available at {MND_CORPUS}",
    )
except ImportError:
    pass


_CACHE: dict = {}


def _load() -> tuple[list, list, list, dict, dict]:
    if "loaded" not in _CACHE:
        extraction = load_jsonl(MND_CORPUS / "extraction.jsonl")
        screening = load_jsonl(MND_CORPUS / "screening.jsonl")
        records = load_jsonl(MND_CORPUS / "records.jsonl")
        old_tables = json.loads((MND_CORPUS / "synthesis-tables.json").read_text())
        cfg = ReviewConfig.from_yaml(MND_YAML)
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
    assert new["corpus_n"] == old["corpus_n"] == 1464


def test_delay_summary():
    _, _, _, old, new = _load()
    n, o = new["delay"], old["delay"]
    assert n["n_studies_with_figure"] == o["n_studies_with_figure"]
    assert n["n_extracted_values"] == o["n_extracted_values"]
    assert n["min"] == o["min_months"]
    assert n["max"] == o["max_months"]
    assert n["median_of_reported"] == o["median_of_reported"]
    assert n["values_in_8_to_20_band"] == o["values_8_to_20mo"]


def test_delay_detail_rows():
    _, _, _, old, new = _load()
    # The detail rows carry pmid + (renamed) tier/design + text — same set
    # of pmids should appear in both
    new_pmids = {r["pmid"] for r in new["delay_detail"]}
    old_pmids = {r["pmid"] for r in old["delay_detail"]}
    assert new_pmids == old_pmids


def test_onset_features_top40():
    _, _, _, old, new = _load()
    # JSON serialisation makes both lists-of-[str,int]; compare directly
    assert new["onset_features_top40"] == old["onset_features_top40"]


def test_differentials_top40_and_drops():
    _, _, _, old, new = _load()
    assert new["differentials_top40"] == old["differentials_top40"]
    assert (
        new["differentials_index_labels_dropped"]
        == old["differentials_index_labels_dropped"]
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


def test_weight_loss_texts():
    _, _, _, old, new = _load()
    assert _norm_rows(new["weight_loss_texts"]) == _norm_rows(old["weight_loss_texts"])


def test_model_prediction_by_category():
    _, _, _, old, new = _load()
    assert new["model_prediction_by_category"] == old["model_prediction"]["by_category"]


def test_model_prediction_charted_bool_matches():
    _, _, _, old, new = _load()
    # "charted" is derivable: any category other than "uncharted" appears
    derived_charted = any(
        c != "uncharted" for c in new["model_prediction_by_category"]
    )
    assert derived_charted == old["model_prediction"]["charted"]


def test_model_validation_texts():
    _, _, _, old, new = _load()
    assert _norm_rows(new["model_validation_texts"]) == _norm_rows(
        old["model_prediction"]["validation_texts"]
    )


def test_prisma_flow_pilot_numbers():
    _, screening, records, _, _ = _load()
    flow = prisma_flow(records=records, screening=screening)
    # MEDLINE-only pilot, no cross-database dedup needed
    assert flow["identified_total"] == 6721
    assert flow["screened"] == 6721
    assert flow["screened_decisions"] == 6721
    assert flow["included_for_charting"] == 1464
    assert flow["excluded_at_title_abstract"] == 4438
    assert flow["maybe_full_text_needed"] == 819


# --- script mode -----------------------------------------------------------


def _run_all_as_script() -> int:
    if not _md_inputs_available():
        print(f"SKIP: MND review data not found at {MND_CORPUS}")
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
