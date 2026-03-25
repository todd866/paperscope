"""
Methodology tests for forensic statistics.

These tests verify that the forensic functions are *applied correctly*
to known cases — not just that the underlying math works.  A methodology
test catches errors like:
  - Using the wrong dp for GRIM (the 26.9 vs 26.90 bug)
  - Pooling categorical and continuous p-values in Carlisle
  - Missing cross-row precision constraints

The Rajizadeh et al. (2017) magnesium paper is the primary test case
because Gideon Meyerowitz-Katz has published detailed forensic analysis
of it, giving us ground-truth expected results.

Ref: Meyerowitz-Katz (personal communication, 2026).
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
        """grim("26.90", 26) should FAIL — string preserves 2dp."""
        r = grim("26.90", 26)
        assert not r['possible'], "26.90 with n=26 must fail GRIM at 2dp"

    def test_float_loses_trailing_zero(self):
        """grim(26.9, 26) with no explicit dp should PASS at 1dp.
        This is technically correct but misleading — callers should
        use strings or explicit dp."""
        r = grim(26.9, 26)
        assert r['possible'], "26.9 (float, auto dp=1) should pass at 1dp"

    def test_float_with_explicit_dp(self):
        """grim(26.9, 26, dp=2) should FAIL — explicit dp overrides."""
        r = grim(26.9, 26, dp=2)
        assert not r['possible'], "26.9 with explicit dp=2 must fail"

    def test_column_dp_inference(self):
        """Column containing 11.26 should force dp=2 for all values."""
        dp = infer_column_dp([26.9, 11.26, 25.6, 15.2])
        assert dp == 2

    def test_column_dp_from_strings(self):
        """String input preserves trailing zeros."""
        dp = infer_column_dp(["26.90", "11.26"])
        assert dp == 2

    def test_column_dp_all_1dp(self):
        """If all values are 1dp, column dp should be 1."""
        dp = infer_column_dp([26.9, 25.6, 15.2])
        assert dp == 1


# ═══════════════════════════════════════════════════════════════════════════════
# GRIM: Rajizadeh BDI means (the primary test case)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRajizadehBdiGrim:
    """All four BDI means should fail GRIM at column-level 2dp."""

    BDI_MEANS = ["26.9", "11.26", "25.6", "15.2"]
    BDI_NS = [26, 26, 27, 27]
    BDI_LABELS = ["Mg baseline", "Mg end", "Placebo baseline", "Placebo end"]

    def test_all_four_fail_with_column_dp(self):
        results = grim_column(self.BDI_MEANS, self.BDI_NS, self.BDI_LABELS)
        for r in results:
            assert not r['possible'], (
                f"{r.get('label', r['reported_mean'])} should fail GRIM "
                f"at column dp={r['column_dp']}"
            )

    def test_mg_baseline_fails_at_2dp(self):
        """26.9 (= 26.90) × 26 = 699.4 — not an integer."""
        r = grim("26.90", 26)
        assert not r['possible']
        assert abs(r['implied_sum'] - 699.4) < 0.01

    def test_mg_end_fails(self):
        """11.26 × 26 = 292.76 — not an integer."""
        r = grim("11.26", 26)
        assert not r['possible']

    def test_placebo_baseline_fails_at_2dp(self):
        """25.60 × 27 = 691.2 — not an integer."""
        r = grim("25.60", 27)
        assert not r['possible']

    def test_placebo_end_fails_at_2dp(self):
        """15.20 × 27 = 410.4 — not an integer."""
        r = grim("15.20", 27)
        assert not r['possible']


# ═══════════════════════════════════════════════════════════════════════════════
# grim_row: cross-cell constraint checking
# ═══════════════════════════════════════════════════════════════════════════════

class TestGrimRow:
    """Cross-row precision and arithmetic constraints."""

    def test_mg_bdi_row_flags(self):
        """Mg BDI: baseline 26.9, end 11.26, change -15.65 — should flag GRIM."""
        r = grim_row("26.9", "11.26", "-15.65", 26, label="Mg BDI")
        assert r['row_dp'] == 2, "Row dp should be 2 (from 11.26 and 15.65)"
        assert not r['baseline_grim']['possible'], "Baseline should fail at 2dp"
        assert not r['end_grim']['possible'], "End should fail at 2dp"
        assert len(r['flags']) > 0

    def test_signed_change_arithmetic_ok(self):
        """With correct sign: baseline - end = 26.9 - 11.26 = 15.64 ≈ 15.65."""
        r = grim_row("26.9", "11.26", "-15.65", 26)
        assert r['arithmetic_ok'], (
            "Arithmetic should PASS with signed change: "
            "26.9 - 11.26 = 15.64 ≈ 15.65 (within rounding)"
        )

    def test_real_arithmetic_error_detected(self):
        """A genuinely wrong change value should still be caught."""
        r = grim_row("26.9", "11.26", "-20.00", 26)
        assert not r['arithmetic_ok']

    def test_consistent_row_passes(self):
        """A row with consistent values should pass."""
        # 10.00 × 20 = 200 (integer), 5.00 × 20 = 100, change = 5.00
        r = grim_row("10.00", "15.00", "5.00", 20)
        assert r['baseline_grim']['possible']
        assert r['end_grim']['possible']
        assert r['arithmetic_ok']


# ═══════════════════════════════════════════════════════════════════════════════
# Carlisle: variable-type splitting
# ═══════════════════════════════════════════════════════════════════════════════

class TestCarlisleTypeSplitting:
    """Categorical and continuous variables must be tested separately."""

    RAJIZADEH_TYPED = [
        (0.93, "categorical"),   # Sex
        (0.28, "categorical"),   # Marital
        (0.80, "categorical"),   # Education
        (0.67, "categorical"),   # Occupation
        (0.89, "continuous"),    # BMI
        (0.07, "continuous"),    # Protein
        (0.04, "continuous"),    # Carbohydrate
        (0.56, "continuous"),    # Fat
        (0.62, "continuous"),    # Dietary Mg
    ]

    def test_typed_input_auto_splits(self):
        """Mixed types should produce a list of results."""
        results = carlisle_stouffer_fisher(self.RAJIZADEH_TYPED)
        assert isinstance(results, list), "Mixed types should return list"
        types = [r['variable_type'] for r in results]
        assert 'categorical' in types
        assert 'continuous' in types
        assert 'combined' in types

    def test_combined_has_warning_note(self):
        """Combined result should have a caution note."""
        results = carlisle_stouffer_fisher(self.RAJIZADEH_TYPED)
        combined = [r for r in results if r['variable_type'] == 'combined'][0]
        assert '_note' in combined

    def test_plain_list_backward_compatible(self):
        """Plain List[float] input should still return a single dict."""
        r = carlisle_stouffer_fisher([0.93, 0.28, 0.80, 0.67])
        assert isinstance(r, dict)

    def test_single_type_returns_dict(self):
        """All same type should return a single dict, not a list."""
        r = carlisle_stouffer_fisher([
            (0.93, "categorical"), (0.28, "categorical"),
            (0.80, "categorical"), (0.67, "categorical"),
        ])
        assert isinstance(r, dict)

    def test_too_few_pvalues_skips(self):
        """Fewer than 3 p-values should return skip result."""
        r = carlisle_stouffer_fisher([0.5, 0.8])
        assert r['sufficient_data'] is False
        assert 'SKIP' in r['detail']


# ═══════════════════════════════════════════════════════════════════════════════
# Rajizadeh strongest findings (should never regress)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRajizadehStrongestFindings:
    """The findings that survive expert scrutiny must never regress."""

    def test_placebo_serum_mg_correlation_impossible(self):
        """Pre SD=0.13, Post SD=0.27, Change SD=0.03 → r=1.27 (impossible)."""
        r = correlation_bound(0.13, 0.27, 0.03)
        assert abs(r['implied_r'] - 1.27) < 0.02
        assert not r['possible']

    def test_table2_arithmetic_failures(self):
        """At least 5 of 8 Table 2 rows should have arithmetic failures."""
        table2 = [
            (63.33, 71.51, 44.31),
            (75.08, 69.67, 23.45),
            (305.1, 307.49, 87.21),
            (364.08, 308.19, 113.34),
            (81.88, 75.53, -6.35),
            (87.17, 81.60, 32.15),
            (153.47, 170.83, 81.50),
            (162.96, 193.10, 90.29),
        ]
        failures = 0
        for b, e, c in table2:
            r = check_change_arithmetic(b, e, c, "")
            if not r.get('consistent', True):
                failures += 1
        assert failures >= 5, f"Expected ≥5 arithmetic failures, got {failures}"
