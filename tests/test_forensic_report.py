"""
Tests for the forensic report layer (verdict taxonomy + table-mode runner).

verdict_of maps raw forensic_stats result dicts onto the shared
PASS/FLAG/FAIL/UNDETERMINED taxonomy; run_table_checks wires a table
spec through the individual checks and emits a Report dict.

Cardinal rule under test: FAIL is reserved for arithmetically impossible
values.  Suspicious-but-possible results must soften to FLAG, and input
problems must never produce FAIL.

All inputs below are synthetic/fabricated values constructed to exercise
a specific code path.  They do not correspond to any real publication or
author.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from paperscope.analysis.forensic_report import (
    VERDICTS, build_report, finding_from_result, run_table_checks,
    verdict_from_result, verdict_of,
)

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')


# ═══════════════════════════════════════════════════════════════════════════════
# verdict_of: the contract mapping
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerdictOf:
    """Raw check-result dicts map onto PASS/FLAG/FAIL/UNDETERMINED."""

    # -- possible / plausible / consistent keys --

    def test_possible_true_is_pass(self):
        assert verdict_of({'possible': True, 'detail': "PASS: fine"}) == "PASS"

    def test_possible_false_is_fail(self):
        """grim/grimmer impossibility (detail says FAIL) hardens to FAIL."""
        r = {'possible': False, 'detail': "FAIL: mean impossible"}
        assert verdict_of(r) == "FAIL"

    def test_possible_none_is_undetermined(self):
        r = {'possible': None, 'detail': "UNDETERMINED: cannot test"}
        assert verdict_of(r) == "UNDETERMINED"

    def test_plausible_true_is_pass(self):
        assert verdict_of({'plausible': True, 'detail': "PASS: ok"}) == "PASS"

    def test_plausible_none_is_undetermined(self):
        r = {'plausible': None, 'detail': "UNDETERMINED: degenerate"}
        assert verdict_of(r) == "UNDETERMINED"

    def test_plausible_false_with_flag_detail_softens_to_flag(self):
        """check_ttest_* p-mismatch is suspicious, NOT proven impossible:
        the check's own detail says FLAG, so the verdict must soften."""
        r = {'plausible': False, 'detail': "FLAG: ratio = 50.0x"}
        assert verdict_of(r) == "FLAG"

    def test_plausible_false_with_fail_detail_is_fail(self):
        """Negative SD inside a t-test check is genuinely impossible."""
        r = {'plausible': False, 'detail': "FAIL: a negative SD is impossible"}
        assert verdict_of(r) == "FAIL"

    def test_consistent_false_with_fail_detail_is_fail(self):
        """check_change_arithmetic mismatch: End - Baseline != Change."""
        r = {'consistent': False, 'detail': "FAIL: reported as -9.0"}
        assert verdict_of(r) == "FAIL"

    def test_consistent_false_with_flag_detail_softens_to_flag(self):
        """check_anova_oneway / check_chi_squared mismatches are FLAGs."""
        r = {'consistent': False, 'flags': ["F: calculated 3.1, reported 9.9"],
             'detail': "FLAG: F: calculated 3.1, reported 9.9"}
        assert verdict_of(r) == "FLAG"

    def test_consistent_none_is_undetermined(self):
        r = {'consistent': None, 'detail': "UNDETERMINED: degenerate"}
        assert verdict_of(r) == "UNDETERMINED"

    # -- suspicious key (carlisle_stouffer_fisher) --

    def test_suspicious_true_is_flag(self):
        r = {'suspicious': True, 'flags': ["too balanced"],
             'detail': "FLAG: too balanced"}
        assert verdict_of(r) == "FLAG"

    def test_suspicious_false_is_pass(self):
        r = {'suspicious': False, 'flags': [], 'detail': "PASS: uniform"}
        assert verdict_of(r) == "PASS"

    # -- flags-list checks (quick_sd_check, variance_ratio_test) --

    def test_empty_flags_is_pass(self):
        assert verdict_of({'flags': [], 'detail': "PASS: fine"}) == "PASS"

    def test_nonempty_flags_is_flag(self):
        r = {'flags': ["SD suspiciously similar"], 'detail': "FLAG: ..."}
        assert verdict_of(r) == "FLAG"

    def test_impossible_flag_is_fail(self):
        """quick_sd_check: SD above the theoretical maximum is impossible."""
        r = {'flags': ["SD (40) exceeds theoretical maximum (31.9) "
                       "for range [0, 63] — IMPOSSIBLE"],
             'detail': "FLAG: ..."}
        assert verdict_of(r) == "FAIL"

    # -- degenerate shapes: never bad news --

    def test_skip_result_is_undetermined(self):
        r = {'sufficient_data': False, 'detail': "SKIP: need >= 3 p-values"}
        assert verdict_of(r) == "UNDETERMINED"

    def test_unrecognized_shape_is_undetermined(self):
        assert verdict_of({'detail': "something odd"}) == "UNDETERMINED"

    def test_empty_dict_is_undetermined(self):
        assert verdict_of({}) == "UNDETERMINED"

    def test_numpy_bool_is_recognised(self):
        """check_ttest_* comparisons yield numpy bools; np.True_ is not
        the True singleton, but must still map to PASS (regression)."""
        import numpy as np
        r = {'plausible': np.bool_(True), 'detail': "PASS: ratio = 1.0x"}
        assert verdict_of(r) == "PASS"
        r = {'plausible': np.bool_(False), 'detail': "FLAG: ratio = 50.0x"}
        assert verdict_of(r) == "FLAG"

    def test_verdict_from_result_is_same_mapping(self):
        """Both entry names share one canonical implementation."""
        for r in ({'possible': True}, {'possible': False},
                  {'flags': ["odd"]}, {'suspicious': True, 'flags': ["x"]},
                  {'detail': "SKIP: n/a"}):
            assert verdict_from_result(r) == verdict_of(r)


# ═══════════════════════════════════════════════════════════════════════════════
# run_table_checks: a synthetic table exercising every section
# ═══════════════════════════════════════════════════════════════════════════════

# Canonical GRIM FAIL: 18.72 * 22 = 411.84 — no integer sum rounds to
# 18.72 at 2 dp.  Control mean 17.62 * 21 = 370.02 → sum 370 works (PASS).
SYNTHETIC_TABLE = {
    "meta": {"paper": "synthetic", "table": "Table 1"},
    "scale": {"lo": 0, "hi": 63, "granularity": 1},
    "variables": [
        {"name": "Q-scale",
         "groups": [
             {"name": "treatment", "n": 22, "mean": "18.72", "sd": "9.41"},
             {"name": "control", "n": 21, "mean": "17.62", "sd": "8.87"},
         ],
         "baseline_p": 0.83},
        {"name": "age",
         "groups": [{"name": "all", "n": 43, "mean": "35.5"}],
         "baseline_p": 0.45},
        {"name": "weight",
         "groups": [{"name": "all", "n": 43, "mean": "71.5"}],
         "baseline_p": 0.62},
    ],
    "percentages": [
        # 53.2% of 25 = 13.3 people — impossible (canonical FAIL)
        {"name": "female", "group": "treatment", "n": 25,
         "percentage": 53.2, "dp": 1},
    ],
    "tests": [
        # Consistent t-test: t(38) = -3.16, p ~ 0.0031
        {"type": "ttest_independent", "target": "Q-scale end / treatment vs control",
         "mean1": 10.0, "sd1": 2.0, "n1": 20,
         "mean2": 12.0, "sd2": 2.0, "n2": 20, "reported_p": 0.003},
        # Consistent chi-squared: Pearson chi2(1) = 8.333, p ~ 0.0039
        {"type": "chi_squared", "target": "responder rate",
         "table": [[10, 15], [20, 5]],
         "reported_chi2": 8.33, "reported_p": 0.004},
        # Unknown test type must land UNDETERMINED, never FAIL
        {"type": "mystery_test", "target": "unknown analysis"},
    ],
    "pre_post": [
        {"name": "Q-scale / treatment", "sd_pre": 9.41, "sd_post": 8.5,
         "sd_change": 4.0},
    ],
    "changes": [
        {"name": "Q-scale change / treatment", "baseline": 18.72, "end": 9.34,
         "reported_change": -9.38},
    ],
    "unknown_section": [{"ignored": True}],   # unknown keys are ignored
}


@pytest.fixture(scope="module")
def report():
    return run_table_checks(SYNTHETIC_TABLE, source="synthetic.json")


def _find(report, check, target):
    hits = [f for f in report["findings"]
            if f["check"] == check and f["target"] == target]
    assert hits, f"no finding for check={check!r} target={target!r}"
    return hits[0]


class TestRunTableChecks:

    def test_report_shape(self, report):
        assert report["source"] == "synthetic.json"
        assert report["mode"] == "table"
        assert set(report["counts"]) == set(VERDICTS)
        assert isinstance(report["summary"], str)
        assert "impossible" in report["summary"]

    def test_counts_match_findings(self, report):
        assert sum(report["counts"].values()) == len(report["findings"])
        for v in VERDICTS:
            n = sum(1 for f in report["findings"] if f["verdict"] == v)
            assert report["counts"][v] == n

    def test_finding_shape(self, report):
        for f in report["findings"]:
            assert set(f) >= {"check", "verdict", "target", "inputs",
                              "detail", "ref"}
            assert f["verdict"] in VERDICTS
            assert isinstance(f["inputs"], dict)

    def test_canonical_grim_fail(self, report):
        f = _find(report, "grim", "Q-scale / treatment")
        assert f["verdict"] == "FAIL"
        assert "18.72" in f["detail"]

    def test_grimmer_fail_follows_grim(self, report):
        f = _find(report, "grimmer", "Q-scale / treatment")
        assert f["verdict"] == "FAIL"

    def test_passing_variable(self, report):
        assert _find(report, "grim", "Q-scale / control")["verdict"] == "PASS"
        assert _find(report, "grim", "age / all")["verdict"] == "PASS"

    def test_quick_sd_check_runs_with_scale(self, report):
        f = _find(report, "quick_sd_check", "Q-scale / treatment")
        assert f["verdict"] == "PASS"   # SD 9.41 is fine on [0, 63]

    def test_variance_ratio_across_groups(self, report):
        f = _find(report, "variance_ratio_test", "Q-scale / SDs across groups")
        assert f["verdict"] == "PASS"

    def test_carlisle_runs_on_three_baseline_ps(self, report):
        hits = [f for f in report["findings"]
                if f["check"] == "carlisle_stouffer_fisher"]
        assert len(hits) == 1
        assert hits[0]["verdict"] == "PASS"
        assert hits[0]["inputs"]["p_values"] == [0.83, 0.45, 0.62]

    def test_grim_percentage_fail(self, report):
        f = _find(report, "grim_percentage", "female / treatment")
        assert f["verdict"] == "FAIL"
        assert "13.3" in f["detail"]

    def test_consistent_ttest_passes(self, report):
        f = _find(report, "check_ttest_independent",
                  "Q-scale end / treatment vs control")
        assert f["verdict"] == "PASS"

    def test_consistent_chi_squared_passes(self, report):
        f = _find(report, "check_chi_squared", "responder rate")
        assert f["verdict"] == "PASS"

    def test_unknown_test_type_is_undetermined(self, report):
        hits = [f for f in report["findings"]
                if f["target"] == "unknown analysis"]
        assert len(hits) == 1
        assert hits[0]["verdict"] == "UNDETERMINED"

    def test_pre_post_correlation_bound(self, report):
        f = _find(report, "correlation_bound", "Q-scale / treatment")
        assert f["verdict"] == "PASS"

    def test_change_arithmetic(self, report):
        f = _find(report, "check_change_arithmetic", "Q-scale change / treatment")
        assert f["verdict"] == "PASS"

    def test_no_fail_unless_truly_impossible(self, report):
        """Cardinal rule: every FAIL finding must carry the check's own
        FAIL detail (arithmetically impossible), never a softer one."""
        fails = [f for f in report["findings"] if f["verdict"] == "FAIL"]
        expected = {("grim", "Q-scale / treatment"),
                    ("grimmer", "Q-scale / treatment"),
                    ("grim_percentage", "female / treatment")}
        assert {(f["check"], f["target"]) for f in fails} == expected
        for f in fails:
            assert f["detail"].startswith("FAIL"), f

    def test_expected_counts(self, report):
        assert report["counts"]["FAIL"] == 3
        assert report["counts"]["FLAG"] == 0
        assert report["counts"]["UNDETERMINED"] == 1


class TestRunTableChecksBadInput:
    """Parsing/input problems never produce FAIL."""

    def test_non_dict_raises_clean_error(self):
        with pytest.raises(ValueError):
            run_table_checks(["not", "a", "table"])

    def test_empty_table_is_empty_report(self):
        r = run_table_checks({}, source="empty.json")
        assert r["findings"] == []
        assert sum(r["counts"].values()) == 0

    def test_garbage_values_yield_undetermined_not_fail(self):
        r = run_table_checks({
            "variables": [
                {"name": "X",
                 "groups": [{"name": "g", "n": 10, "mean": "not-a-number",
                             "sd": "also-bad"}]},
            ],
            "percentages": [{"name": "p", "n": 10, "percentage": "bad"}],
            "changes": [{"name": "c", "baseline": None, "end": 5,
                         "reported_change": 5}],
        })
        assert r["counts"]["FAIL"] == 0
        assert r["counts"]["UNDETERMINED"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers shared with the text-mode agent
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelpers:

    def test_finding_from_result_defaults_ref(self):
        f = finding_from_result(
            "grim", {'possible': True, 'detail': "PASS: ok"},
            "X / g", {"mean": "1.5", "n": 2})
        assert f["ref"] == "Brown & Heathers 2017"
        assert f["verdict"] == "PASS"
        assert f["detail"] == "PASS: ok"
        assert "anchor" not in f and "page" not in f

    def test_finding_from_result_anchor_and_page(self):
        f = finding_from_result(
            "grim", {'possible': True, 'detail': "PASS: ok"},
            "X", {}, anchor="M = 1.5", page=3)
        assert f["anchor"] == "M = 1.5"
        assert f["page"] == 3

    def test_build_report_counts_and_summary(self):
        findings = [
            finding_from_result(
                "grim", {'possible': False, 'detail': "FAIL: x"}, "a", {}),
            finding_from_result(
                "quick_sd_check", {'flags': ["odd"], 'detail': "FLAG: odd"},
                "b", {}),
        ]
        r = build_report("s.json", "text", findings)
        assert r["mode"] == "text"
        assert r["counts"]["FAIL"] == 1 and r["counts"]["FLAG"] == 1
        assert r["summary"].startswith("2 checks: 1 impossible, 1 flagged")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI smoke test
# ═══════════════════════════════════════════════════════════════════════════════

SMALL_TABLE = {
    "variables": [
        {"name": "Q-scale",
         "groups": [{"name": "treatment", "n": 22, "mean": "18.72",
                     "sd": "9.41"}]},
    ],
}


class TestForensicCli:

    def test_table_mode_smoke(self, tmp_path):
        table_path = tmp_path / "table.json"
        table_path.write_text(json.dumps(SMALL_TABLE), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "paperscope", "forensic", str(table_path)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert proc.returncode == 0, proc.stderr
        report_path = tmp_path / "table.forensic.json"
        assert report_path.exists(), "report JSON not written next to input"
        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert data["mode"] == "table"
        assert data["counts"]["FAIL"] >= 1
        assert "FAIL" in proc.stdout

    def test_output_flag(self, tmp_path):
        table_path = tmp_path / "table.json"
        table_path.write_text(json.dumps(SMALL_TABLE), encoding="utf-8")
        out_path = tmp_path / "custom.json"
        proc = subprocess.run(
            [sys.executable, "-m", "paperscope", "forensic",
             str(table_path), "-o", str(out_path)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert proc.returncode == 0, proc.stderr
        assert out_path.exists()

    def test_txt_input_runs_text_mode(self, tmp_path):
        # A .txt with no reported statistics runs text mode cleanly and
        # produces an empty report -- prose is never an error, and "no
        # stats found" is never a FAIL.
        txt_path = tmp_path / "paper.txt"
        txt_path.write_text("Some prose, not a table spec.", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "paperscope", "forensic", str(txt_path)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert proc.returncode == 0, proc.stderr
        report = json.loads((tmp_path / "paper.forensic.json").read_text())
        assert report["mode"] == "text"
        assert report["findings"] == []

    def test_unsupported_input_type_errors(self, tmp_path):
        bad = tmp_path / "paper.docx"
        bad.write_text("whatever", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "paperscope", "forensic", str(bad)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert proc.returncode != 0
        assert "unsupported input type" in (proc.stdout + proc.stderr)

    def test_invalid_json_errors_cleanly(self, tmp_path):
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{not json", encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "paperscope", "forensic", str(bad_path)],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert proc.returncode != 0


class TestCodexReviewTableFalseAccusations:
    """Round-2 adversarial review (Codex): string n / missing n must not
    produce a false 'IMPOSSIBLE' SD FAIL via the population bound."""

    def test_string_n_is_parsed(self):
        from paperscope.analysis.forensic_report import _int
        assert _int("2") == 2
        assert _int("22.0") == 22
        assert _int("3.5") is None
        assert _int("n/a") is None

    def test_valid_binary_sd_with_string_n_not_fail(self):
        # n="2", binary [0,1], SD 0.707 is a valid sample SD ([0,1] data)
        table = {
            "scale": {"lo": 0, "hi": 1},
            "variables": [{"name": "flag", "groups": [
                {"name": "g", "n": "2", "mean": "0.5", "sd": "0.707"}]}],
        }
        rep = run_table_checks(table)
        qsd = [f for f in rep["findings"] if f["check"] == "quick_sd_check"]
        assert all(f["verdict"] != "FAIL" for f in qsd), qsd

    def test_missing_n_skips_quick_sd_check(self):
        table = {
            "scale": {"lo": 0, "hi": 10},
            "variables": [{"name": "x", "groups": [
                {"name": "g", "mean": "5.0", "sd": "6.0"}]}],
        }
        rep = run_table_checks(table)
        qsd = [f for f in rep["findings"] if f["check"] == "quick_sd_check"]
        assert qsd == []
