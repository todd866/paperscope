"""Unit tests for the validate submodule (rubric, workbook, reconcile).

Self-contained — builds tiny in-memory fixtures, no external corpus needed.

  python tests/test_validate.py    # standalone, prints PASS/FAIL
  pytest tests/test_validate.py    # under pytest
"""

from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from paperscope.systematic_review.validate.rubric import load_friction_rubric, default_rubric  # noqa: E402
from paperscope.systematic_review.validate.workbook import build_workbook  # noqa: E402
from paperscope.systematic_review.validate.reconcile import reconcile, summarize  # noqa: E402


DECISIONS = [
    {"record_id": "101", "decision": "include", "themes": ["dx"], "reason": "AI ECG model, AUC reported"},
    {"record_id": "102", "decision": "exclude", "themes": [], "reason": "review article, no metric"},
]
RECORDS = {
    "101": {"record_id": "101", "title": "DL AF detection", "abstract": "CNN on ECG; AUC 0.93."},
    "102": {"record_id": "102", "title": "AI in cardiology: a review", "abstract": "Survey; no new metric."},
}
SELF_AUDIT = {
    "101": {"record_id": "101", "confidence": 0.9, "flag": False, "reasoning": "clear"},
    "102": {"record_id": "102", "confidence": 0.55, "flag": True, "reasoning": "double-check review-only"},
}


def test_rubric_yaml_bool_coercion(tmp_path):
    # YAML 1.1 parses bare yes/no as booleans; the loader must coerce to str.
    p = tmp_path / "r.yaml"
    p.write_text("dimensions:\n  - id: eligible\n    label: Eligible?\n    scale: [yes, no, unsure]\n")
    r = load_friction_rubric(p)
    assert r.ids() == ["eligible"]
    assert r.dimensions[0].scale == ["True", "False", "unsure"] or all(isinstance(s, str) for s in r.dimensions[0].scale)
    assert all(isinstance(s, str) for s in r.dimensions[0].scale)


def test_default_rubric_when_none():
    r = load_friction_rubric(None)
    assert r.ids() == ["agree"]


def test_workbook_builds_and_flagged_first():
    rubric = default_rubric()
    html = build_workbook(DECISIONS, RECORDS, rubric, SELF_AUDIT, title="T", wb_id="t")
    # parses
    HTMLParser().feed(html)
    assert html.count('class="card') == 2
    # flagged (102, lower confidence) sorts before 101
    assert html.index('data-rid="102"') < html.index('data-rid="101"')
    # local abstract is embedded; the title shows
    assert "AUC 0.93" in html
    assert "DL AF detection" in html


def test_workbook_without_self_audit():
    html = build_workbook(DECISIONS, RECORDS, default_rubric(), None)
    assert html.count('class="card') == 2


def test_reconcile_and_summary():
    export = {
        "102": {"reviewed": True, "flip": True, "ratings": {"eligible": "no"}, "note": "confirmed exclude"},
        "101": {"reviewed": True, "flip": False, "ratings": {"eligible": "yes", "extraction": "yes"}, "note": ""},
    }
    overrides, requeue = reconcile(DECISIONS, export)
    assert len(overrides) == 2
    assert len(requeue) == 1 and requeue[0]["record_id"] == "102"
    # original decision is preserved in the override (append-only provenance)
    o102 = next(o for o in overrides if o["record_id"] == "102")
    assert o102["human"] == "flip"
    assert o102["original_decision"]["decision"] == "exclude"
    s = summarize(overrides)
    assert s["n_records_touched"] == 2 and s["flipped"] == 1
    assert s["agreement_rate"] == 0.5
    assert s["per_dimension"]["eligible"] == {"no": 1, "yes": 1}


def test_reconcile_does_not_mutate_inputs():
    before = [dict(d) for d in DECISIONS]
    reconcile(DECISIONS, {"101": {"flip": True}})
    assert DECISIONS == before  # append-only: source decisions untouched


if __name__ == "__main__":
    import tempfile
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                if "tmp_path" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                    with tempfile.TemporaryDirectory() as td:
                        fn(Path(td))
                else:
                    fn()
                print(f"PASS {name}")
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
