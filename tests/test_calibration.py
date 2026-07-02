"""Regression gate + unit tests for the forensic calibration harness.

The regression gate loads the built-in public case battery and asserts
every ``must_detect`` fires to at least its ``min_verdict`` and every
``must_pass`` comes back a clean PASS.  This is what re-runs on any
subsequent change to the checks or to the battery: if a change stops
catching a planted error (sensitivity) or starts branding valid data
impossible (specificity -- the cardinal rule), a case flips to MISMATCH
and this test goes red.

The unit tests pin down the matching logic itself (min_verdict ordering,
target_contains substring matching, false-accusation detection) against
synthetic finding lists, without running the (scipy-backed) checks.

    pytest tests/test_calibration.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from paperscope.analysis.calibration import (  # noqa: E402
    BUILTIN_CASES_DIR,
    calibrate,
    load_cases,
    match_findings,
    run_case,
)


# ═══════════════════════════════════════════════════════════════════════════
# Regression gate over the built-in public battery
# ═══════════════════════════════════════════════════════════════════════════

def test_builtin_battery_loads_at_least_five_cases():
    cases = load_cases([str(BUILTIN_CASES_DIR)])
    assert len(cases) >= 5, f"expected >= 5 built-in cases, got {len(cases)}"
    # Every built-in case is public + synthetic -- no clinical/biomedical
    # content is allowed in the public corpus.
    for case in cases:
        assert case.get("meta", {}).get("source") == "synthetic", case.get("_path")


def test_builtin_battery_every_case_ok():
    """The core regression assertion: no misses, no false accusations."""
    cases = load_cases([str(BUILTIN_CASES_DIR)])
    for case in cases:
        result = run_case(case)
        assert result["ok"], (
            f"{result['label']}: misses={result['misses']} "
            f"false_passes={result['false_passes']}")


def test_builtin_battery_perfect_sensitivity_and_specificity():
    report = calibrate([str(BUILTIN_CASES_DIR)])
    assert report["mismatches"] == [], report["summary"]
    assert report["sensitivity"] == 1.0, report["summary"]
    assert report["specificity"] == 1.0, report["summary"]
    # Both gates must actually be exercised, not vacuously satisfied.
    assert report["totals"]["detected"] >= 4, report["totals"]
    assert report["totals"]["correctly_passed"] >= 5, report["totals"]


def test_builtin_battery_exercises_each_required_check():
    """The battery must collectively cover grim, grimmer, grim_percentage,
    and p_recalculation across both must_detect and must_pass."""
    report = calibrate([str(BUILTIN_CASES_DIR)])
    per_check = report["per_check"]
    # every must_detect check we planted an error for
    for check in ("grim", "grimmer", "grim_percentage", "p_recalculation"):
        assert per_check.get(check, {}).get("detected", 0) >= 1, (check, per_check)
    # specificity guarded for every check
    for check in ("grim", "grimmer", "grim_percentage", "p_recalculation"):
        assert per_check.get(check, {}).get("correctly_passed", 0) >= 1, (
            check, per_check)


# ═══════════════════════════════════════════════════════════════════════════
# Unit tests for the matching logic
# ═══════════════════════════════════════════════════════════════════════════

def _f(check, verdict, target):
    return {"check": check, "verdict": verdict, "target": target}


def test_min_verdict_flag_satisfied_by_flag_and_fail():
    findings = [_f("grim", "FLAG", "X / treatment")]
    exp = {"must_detect": [{"check": "grim", "target_contains": "treatment",
                            "min_verdict": "FLAG"}]}
    m = match_findings(findings, exp)
    assert not m["misses"] and len(m["hits"]) == 1

    findings = [_f("grim", "FAIL", "X / treatment")]
    assert not match_findings(findings, exp)["misses"]


def test_min_verdict_fail_not_satisfied_by_flag():
    findings = [_f("grim", "FLAG", "X / treatment")]
    exp = {"must_detect": [{"check": "grim", "target_contains": "treatment",
                            "min_verdict": "FAIL"}]}
    m = match_findings(findings, exp)
    assert m["misses"] and not m["hits"]
    assert m["misses"][0]["best_verdict"] == "FLAG"


def test_min_verdict_flag_not_satisfied_by_pass_or_undetermined():
    exp = {"must_detect": [{"check": "grim", "target_contains": "t",
                            "min_verdict": "FLAG"}]}
    for verdict in ("PASS", "UNDETERMINED"):
        m = match_findings([_f("grim", verdict, "X / t")], exp)
        assert m["misses"], verdict


def test_target_contains_filters_by_substring():
    findings = [_f("grim", "FAIL", "X / control")]  # wrong target
    exp = {"must_detect": [{"check": "grim", "target_contains": "treatment",
                            "min_verdict": "FAIL"}]}
    m = match_findings(findings, exp)
    assert m["misses"] and m["misses"][0]["matched"] == 0


def test_must_detect_default_min_verdict_is_flag():
    # No min_verdict key -> defaults to FLAG, so a FLAG satisfies it.
    findings = [_f("grim", "FLAG", "X / t")]
    exp = {"must_detect": [{"check": "grim", "target_contains": "t"}]}
    assert not match_findings(findings, exp)["misses"]


def test_must_pass_pass_is_clean():
    findings = [_f("grim", "PASS", "X / control")]
    exp = {"must_pass": [{"check": "grim", "target_contains": "control"}]}
    assert match_findings(findings, exp)["false_passes"] == []


def test_must_pass_flag_is_false_accusation():
    findings = [_f("grim", "FLAG", "X / control")]
    exp = {"must_pass": [{"check": "grim", "target_contains": "control"}]}
    fp = match_findings(findings, exp)["false_passes"]
    assert len(fp) == 1 and fp[0]["best_verdict"] == "FLAG"


def test_must_pass_fail_is_false_accusation():
    findings = [_f("grim", "FAIL", "X / control")]
    exp = {"must_pass": [{"check": "grim", "target_contains": "control"}]}
    assert match_findings(findings, exp)["false_passes"]


def test_must_pass_missing_finding_counts_as_specificity_failure():
    # No matching finding -> we cannot confirm the clean PASS we asserted.
    exp = {"must_pass": [{"check": "grim", "target_contains": "control"}]}
    fp = match_findings([], exp)["false_passes"]
    assert len(fp) == 1 and fp[0]["matched"] == 0


def test_empty_expected_is_rejected_not_vacuously_passed():
    # A case that asserts nothing must NOT pass the gate — otherwise a
    # typo like `must_deteect` silently removes the planted error.
    case = {"meta": {"label": "empty"}, "table": None, "text": None,
            "expected": {"must_detect": [], "must_pass": []}}
    result = run_case(case)
    assert not result["ok"]
    assert "asserts nothing" in result["error"]


def test_unknown_expected_key_is_rejected():
    # `must_deteect` typo -> the real assertion is silently absent.
    case = {"meta": {"label": "typo"}, "table": None, "text": None,
            "expected": {"must_deteect": [{"check": "grim",
                                           "target_contains": "x"}]}}
    result = run_case(case)
    assert not result["ok"]
    assert "unknown key" in result["error"]


def test_null_table_and_text_with_real_assertion_misses():
    # Null sections don't crash; a real must_detect simply misses (no
    # findings), which is a legitimate ok=False (not a schema error).
    case = {"meta": {"label": "empty"}, "table": None, "text": None,
            "expected": {"must_detect": [{"check": "grim",
                                          "target_contains": "x"}]}}
    result = run_case(case)
    assert not result["ok"] and result["findings"] == []
    assert result["misses"] and not result.get("error")


def test_ambiguous_target_contains_is_a_miss_not_a_hit():
    # "treatment" also matches "pretreatment"; a spurious FAIL there must
    # not satisfy a must_detect whose intended target is elsewhere.
    findings = [
        {"check": "grim", "verdict": "PASS", "target": "score / treatment"},
        {"check": "grim", "verdict": "FAIL", "target": "score / pretreatment"},
    ]
    exp = {"must_detect": [{"check": "grim", "target_contains": "treatment",
                            "min_verdict": "FAIL"}]}
    m = match_findings(findings, exp)
    assert not m["hits"] and len(m["misses"]) == 1
    assert "ambiguous" in m["misses"][0]["reason"]


def test_exact_target_disambiguates():
    findings = [
        {"check": "grim", "verdict": "PASS", "target": "score / treatment"},
        {"check": "grim", "verdict": "FAIL", "target": "score / pretreatment"},
    ]
    exp = {"must_detect": [{"check": "grim", "target": "score / pretreatment",
                            "min_verdict": "FAIL"}]}
    m = match_findings(findings, exp)
    assert len(m["hits"]) == 1 and not m["misses"]


def test_load_cases_tolerates_missing_dir_and_bad_json(tmp_path):
    good = tmp_path / "good.json"
    good.write_text('{"meta": {"label": "g", "source": "synthetic"}, '
                    '"table": null, "text": null, '
                    '"expected": {"must_detect": [], "must_pass": []}}',
                    encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("not a case", encoding="utf-8")

    cases = load_cases([str(tmp_path), str(tmp_path / "does_not_exist")])
    labels = {c.get("meta", {}).get("label") for c in cases}
    assert "g" in labels
    # the bad file is surfaced, not crashed on
    assert any(c.get("_error") for c in cases)
    # the .txt is skipped
    assert len(cases) == 2


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(
        [sys.executable, "-m", "pytest", __file__, "-q"]))
