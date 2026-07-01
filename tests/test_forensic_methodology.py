"""
Methodology tests for forensic statistics.

These tests verify that the forensic functions are *applied correctly* —
not just that the underlying math works.  A methodology test catches
errors like:
  - Using the wrong dp for GRIM (the 26.9 vs 26.90 trailing-zero bug)
  - Pooling categorical and continuous p-values in Carlisle
  - Missing cross-row precision constraints

All inputs below are synthetic/fabricated values constructed to exercise
a specific code path.  They do not correspond to any real publication or
author.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from paperscope.analysis.forensic_stats import (
    grim, grim_column, grim_row,
    carlisle_stouffer_fisher, infer_column_dp,
    correlation_bound, check_change_arithmetic,
)


# ═══════════════════════════════════════════════════════════════════════════════
# GRIM: dp inference
# ═══════════════════════════════════════════════════════════════════════════════

class TestGrimDpInference:
    """Trailing-zero precision must be inferred from column context."""

    def test_string_preserves_trailing_zero(self):
        """grim("18.70", 22) should FAIL — string preserves 2dp."""
        r = grim("18.70", 22)
        assert not r['possible'], "18.70 with n=22 must fail GRIM at 2dp"

    def test_float_loses_trailing_zero(self):
        """grim(18.7, 22) with no explicit dp should PASS at 1dp.
        This is technically correct but misleading — callers should
        use strings or explicit dp."""
        r = grim(18.7, 22)
        assert r['possible'], "18.7 (float, auto dp=1) should pass at 1dp"

    def test_float_with_explicit_dp(self):
        """grim(18.7, 22, dp=2) should FAIL — explicit dp overrides."""
        r = grim(18.7, 22, dp=2)
        assert not r['possible'], "18.7 with explicit dp=2 must fail"

    def test_column_dp_inference(self):
        """Column containing 9.34 should force dp=2 for all values."""
        dp = infer_column_dp([18.7, 9.34, 17.2, 11.5])
        assert dp == 2

    def test_column_dp_from_strings(self):
        """String input preserves trailing zeros."""
        dp = infer_column_dp(["18.70", "9.34"])
        assert dp == 2

    def test_column_dp_all_1dp(self):
        """If all values are 1dp, column dp should be 1."""
        dp = infer_column_dp([18.7, 17.2, 11.5])
        assert dp == 1


# ═══════════════════════════════════════════════════════════════════════════════
# GRIM: a synthetic four-cell table (baseline/end x two groups)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyntheticTableGrim:
    """All four fabricated means should fail GRIM at column-level 2dp."""

    MEANS = ["18.72", "9.34", "17.23", "11.55"]
    NS = [22, 22, 24, 24]
    LABELS = ["A baseline", "A end", "B baseline", "B end"]

    def test_all_four_fail_with_column_dp(self):
        results = grim_column(self.MEANS, self.NS, self.LABELS)
        for r in results:
            assert not r['possible'], (
                f"{r.get('label', r['reported_mean'])} should fail GRIM "
                f"at column dp={r['column_dp']}"
            )

    def test_a_baseline_fails_at_2dp(self):
        """18.72 × 22 = 411.84 — not an integer."""
        r = grim("18.72", 22)
        assert not r['possible']
        assert abs(r['implied_sum'] - 411.84) < 0.01

    def test_a_end_fails(self):
        """9.34 × 22 = 205.48 — not an integer."""
        r = grim("9.34", 22)
        assert not r['possible']

    def test_b_baseline_fails_at_2dp(self):
        """17.23 × 24 = 413.52 — not an integer."""
        r = grim("17.23", 24)
        assert not r['possible']

    def test_b_end_fails_at_2dp(self):
        """11.55 × 24 = 277.20 — not an integer."""
        r = grim("11.55", 24)
        assert not r['possible']


# ═══════════════════════════════════════════════════════════════════════════════
# grim_row: cross-cell constraint checking
# ═══════════════════════════════════════════════════════════════════════════════

class TestGrimRow:
    """Cross-row precision and arithmetic constraints."""

    def test_row_flags_grim(self):
        """baseline 18.72, end 9.34, change -9.38 — should flag GRIM."""
        r = grim_row("18.72", "9.34", "-9.38", 22, label="A")
        assert r['row_dp'] == 2, "Row dp should be 2 (from 9.34 and 9.38)"
        assert not r['baseline_grim']['possible'], "Baseline should fail at 2dp"
        assert not r['end_grim']['possible'], "End should fail at 2dp"
        assert len(r['flags']) > 0

    def test_signed_change_arithmetic_ok(self):
        """With correct sign: baseline - end = 18.72 - 9.34 = 9.38 ≈ 9.38."""
        r = grim_row("18.72", "9.34", "-9.38", 22)
        assert r['arithmetic_ok'], (
            "Arithmetic should PASS with signed change: "
            "18.72 - 9.34 = 9.38 (within rounding)"
        )

    def test_real_arithmetic_error_detected(self):
        """A genuinely wrong change value should still be caught."""
        r = grim_row("18.72", "9.34", "-20.00", 22)
        assert not r['arithmetic_ok']

    def test_consistent_row_passes(self):
        """A row with consistent values should pass."""
        # 10.00 × 20 = 200 (integer), 15.00 × 20 = 300, change = 5.00
        r = grim_row("10.00", "15.00", "5.00", 20)
        assert r['baseline_grim']['possible']
        assert r['end_grim']['possible']
        assert r['arithmetic_ok']


# ═══════════════════════════════════════════════════════════════════════════════
# Carlisle: variable-type splitting
# ═══════════════════════════════════════════════════════════════════════════════

class TestCarlisleTypeSplitting:
    """Categorical and continuous variables must be tested separately."""

    TYPED = [
        (0.91, "categorical"),
        (0.34, "categorical"),
        (0.77, "categorical"),
        (0.61, "categorical"),
        (0.85, "continuous"),
        (0.12, "continuous"),
        (0.06, "continuous"),
        (0.52, "continuous"),
        (0.58, "continuous"),
    ]

    def test_typed_input_auto_splits(self):
        """Mixed types should produce a list of results."""
        results = carlisle_stouffer_fisher(self.TYPED)
        assert isinstance(results, list), "Mixed types should return list"
        types = [r['variable_type'] for r in results]
        assert 'categorical' in types
        assert 'continuous' in types
        assert 'combined' in types

    def test_combined_has_warning_note(self):
        """Combined result should have a caution note."""
        results = carlisle_stouffer_fisher(self.TYPED)
        combined = [r for r in results if r['variable_type'] == 'combined'][0]
        assert '_note' in combined

    def test_plain_list_backward_compatible(self):
        """Plain List[float] input should still return a single dict."""
        r = carlisle_stouffer_fisher([0.91, 0.34, 0.77, 0.61])
        assert isinstance(r, dict)

    def test_single_type_returns_dict(self):
        """All same type should return a single dict, not a list."""
        r = carlisle_stouffer_fisher([
            (0.91, "categorical"), (0.34, "categorical"),
            (0.77, "categorical"), (0.61, "categorical"),
        ])
        assert isinstance(r, dict)

    def test_too_few_pvalues_skips(self):
        """Fewer than 3 p-values should return skip result."""
        r = carlisle_stouffer_fisher([0.5, 0.8])
        assert r['sufficient_data'] is False
        assert 'SKIP' in r['detail']


# ═══════════════════════════════════════════════════════════════════════════════
# Impossibility findings (should never regress)
# ═══════════════════════════════════════════════════════════════════════════════

class TestImpossibilityFindings:
    """Findings that flag mathematically impossible statistics must not regress."""

    def test_correlation_bound_impossible(self):
        """Pre SD=0.10, Post SD=0.30, Change SD=0.05 → r=1.625 (impossible)."""
        r = correlation_bound(0.10, 0.30, 0.05)
        assert abs(r['implied_r'] - 1.625) < 0.02
        assert not r['possible']

    def test_change_arithmetic_failures(self):
        """At least 5 of 8 fabricated rows should have arithmetic failures."""
        rows = [
            (60.0, 68.0, 40.0),    # expected 8.0, reported 40.0 → FAIL
            (72.0, 66.0, 20.0),    # expected -6.0, reported 20.0 → FAIL
            (300.0, 305.0, 85.0),  # expected 5.0, reported 85.0 → FAIL
            (360.0, 305.0, 110.0), # expected -55.0, reported 110.0 → FAIL
            (80.0, 74.0, -6.0),    # expected -6.0, reported -6.0 → PASS
            (85.0, 80.0, 30.0),    # expected -5.0, reported 30.0 → FAIL
            (150.0, 168.0, 80.0),  # expected 18.0, reported 80.0 → FAIL
            (160.0, 190.0, 30.0),  # expected 30.0, reported 30.0 → PASS
        ]
        failures = 0
        for b, e, c in rows:
            r = check_change_arithmetic(b, e, c, "")
            if not r.get('consistent', True):
                failures += 1
        assert failures >= 5, f"Expected ≥5 arithmetic failures, got {failures}"
