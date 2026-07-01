"""Unit tests for bib.verify retraction/correction classification.

Self-contained — synthetic Crossref ``update-to`` items and a tiny temp
Retraction Watch CSV, no network.

  python tests/test_verify_retraction.py    # standalone, prints PASS/FAIL
  pytest tests/test_verify_retraction.py     # under pytest
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from paperscope.bib.verify import check_retraction, load_retraction_watch  # noqa: E402


def test_clean_item_returns_none():
    assert check_retraction({"DOI": "10.1/clean"}) is None
    assert check_retraction({"DOI": "10.1/clean", "update-to": []}) is None


def test_plain_retraction():
    item = {"DOI": "10.1/x", "update-to": [{"type": "retraction"}]}
    status, detail = check_retraction(item)
    assert status == "retracted"
    assert "RETRACTED" in detail


def test_withdrawal_and_removal_count_as_retracted():
    for t in ("withdrawal", "removal", "partial_retraction"):
        status, _ = check_retraction({"DOI": "10.1/x", "update-to": [{"type": t}]})
        assert status == "retracted", t


def test_expression_of_concern():
    item = {"DOI": "10.1/x", "update-to": [{"type": "expression_of_concern"}]}
    status, detail = check_retraction(item)
    assert status == "concern"
    assert "CONCERN" in detail


def test_correction_is_corrected_not_fault():
    item = {"DOI": "10.1/x", "update-to": [{"type": "erratum"}]}
    status, _ = check_retraction(item)
    assert status == "corrected"


def test_retraction_dominates_correction():
    item = {"DOI": "10.1/x", "update-to": [{"type": "correction"}, {"type": "retraction"}]}
    status, _ = check_retraction(item)
    assert status == "retracted"


def test_retraction_watch_catches_what_crossref_misses():
    # Crossref says clean (no update-to); Retraction Watch knows better.
    rw = {"10.1/missed": "Retraction"}
    status, detail = check_retraction({"DOI": "10.1/MISSED"}, rw_index=rw)  # case-insensitive
    assert status == "retracted"
    assert "RetractionWatch" in detail


def test_load_retraction_watch_parses_csv():
    csv_text = (
        "OriginalPaperDOI,RetractionNature\n"
        "10.1/aaa,Retraction\n"
        "10.1/BBB,Expression of Concern\n"
        "unavailable,Retraction\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
        fh.write(csv_text)
        path = fh.name
    idx = load_retraction_watch(path)
    assert idx is not None
    assert idx["10.1/aaa"] == "Retraction"
    assert idx["10.1/bbb"] == "Expression of Concern"  # lower-cased key
    assert "unavailable" not in idx
    Path(path).unlink()


def test_load_retraction_watch_absent_returns_none():
    assert load_retraction_watch("/no/such/file.csv") is None


def _run():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
