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
    grimmer, sprite, grim_percentage, debit,
    check_ttest_paired, check_ttest_independent, check_anova_oneway,
    quick_sd_check, sample_size_from_t, check_chi_squared,
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


# ═══════════════════════════════════════════════════════════════════════════════
# Carlisle: direction of the Stouffer flag (bug 1)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCarlisleDirection:
    """High p-values are Carlisle's too-well-balanced fabrication signature;
    low p-values are genuinely unbalanced baselines. The labels must not be
    swapped."""

    def test_high_pvalues_flag_well_balanced(self):
        """[0.95]*10 → combined Z ≈ -5.2 → suspiciously WELL-balanced."""
        r = carlisle_stouffer_fisher([0.95] * 10)
        stouffer = [f for f in r['flags'] if 'Stouffer' in f]
        assert stouffer, "high p-values must trigger the Stouffer flag"
        assert all('well-balanced' in f for f in stouffer), stouffer

    def test_low_pvalues_flag_unbalanced(self):
        """[0.05]*10 → combined Z ≈ +5.2 → suspiciously UNbalanced."""
        r = carlisle_stouffer_fisher([0.05] * 10)
        stouffer = [f for f in r['flags'] if 'Stouffer' in f]
        assert stouffer, "low p-values must trigger the Stouffer flag"
        assert all('well-balanced' not in f and 'unbalanced' in f
                   for f in stouffer), stouffer


# ═══════════════════════════════════════════════════════════════════════════════
# GRIM: half-boundary rounding (bug 2) and invalid n (bug 12)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGrimHalfBoundary:
    """True means sitting exactly on the rounding boundary must PASS —
    they round to the reported value under half-up or banker's rounding."""

    def test_mean_075_reported_08(self):
        """Data (0,1,1,1): mean 0.75 reported as '0.8' at 1dp must pass."""
        r = grim("0.8", 4)
        assert r['possible'], r['detail']

    def test_boundary_symmetric(self):
        """0.25 rounds to '0.3' (half-up) or '0.2' (banker's) — both pass."""
        assert grim("0.3", 4)['possible']
        assert grim("0.2", 4)['possible']

    def test_canonical_fail_preserved(self):
        """18.72 with n=22 is a genuine GRIM failure and must stay FAIL."""
        assert not grim("18.72", 22)['possible']

    def test_n_zero_returns_clean_result(self):
        """n=0 must return an invalid-input result, not raise."""
        r = grim("5.0", 0)
        assert r['possible'] is None
        r = grim("5.0", -3)
        assert r['possible'] is None


# ═══════════════════════════════════════════════════════════════════════════════
# GRIMMER: multi-sum iteration, zero-SD clamp, parity (bug 3)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGrimmer:
    def test_all_grim_admitted_sums_tested(self):
        """n=25 Likert, real data sum 66 (mean 2.64→'2.6', sd 1.5242→'1.52').
        Only sum=65 fails; sum=66 works, so GRIMMER must PASS."""
        r = grimmer("2.6", "1.52", 25)
        assert r['possible'], r['detail']

    def test_zero_sd_is_possible(self):
        """Ten 5s give mean 5.0 and SD 0.0 — must PASS (clamp SD lower
        bound at 0 before squaring)."""
        r = grimmer("5.0", "0.0", 10)
        assert r['possible'], r['detail']

    def test_canonical_fail_preserved(self):
        """mean 5.0, sd 0.15, n=10: no integer sum-of-squares in range."""
        r = grimmer("5.0", "0.15", 10)
        assert not r['possible'], r['detail']

    def test_parity_constraint(self):
        """mean 5.0, sd 1.0, n=10: only candidate sum_sq is 259, but
        sum(x²) ≡ sum(x) (mod 2) forces even — truly impossible."""
        r = grimmer("5.0", "1.0", 10)
        assert not r['possible'], r['detail']

    def test_parity_never_kills_real_data(self):
        """Real dataset: eight 5s + 4 + 6 → sum 50, sum_sq 252,
        sd 0.4714 → '0.5'. Parity matches; must PASS."""
        r = grimmer("5.0", "0.5", 10)
        assert r['possible'], r['detail']

    def test_negative_sd_fails(self):
        r = grimmer("5.0", -1.0, 10)
        assert r['possible'] is False

    def test_n_zero_returns_clean_result(self):
        r = grimmer("5.0", "1.0", 0)
        assert r['possible'] is None


# ═══════════════════════════════════════════════════════════════════════════════
# SPRITE: zero-SD clamp, hi>63, dp-derived SD tolerance, verdicts (bug 4)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSprite:
    def test_zero_sd_is_possible(self):
        """Ten 5s: mean 5.0, SD 0.0, range [1,7] — must PASS."""
        r = sprite(mean=5.0, sd=0.0, n=10, lo=1, hi=7, dp=1)
        assert r['possible'], r['detail']
        assert r['example_dataset'] == [5] * 10

    def test_search_works_above_63(self):
        """Scales above the old BDI literal 63 must be searchable."""
        r = sprite(mean=90.0, sd=2.0, n=10, lo=80, hi=100, max_iter=200_000)
        assert r['possible'], r['detail']
        assert all(80 <= x <= 100 for x in r['example_dataset'])

    def test_sd_tolerance_from_dp(self):
        """SD '0.46' at 2dp has no valid sum-of-squares for mean 5.0, n=10
        (interval [0.455, 0.465] admits none) — analytic FAIL. The old
        hardcoded ±0.05 tolerance wrongly admitted sum_sq 252."""
        r = sprite(mean=5.0, sd=0.46, n=10, lo=0, hi=10, dp_sd=2)
        assert r['possible'] is False
        assert r['detail'].startswith('FAIL')
        assert r['n_feasible_sum_targets'] == 0

    def test_search_exhausted_is_flag_not_fail(self):
        """A feasible target not found within a tiny budget must be FLAG
        ('not found within budget'), never a FAIL verdict."""
        r = sprite(mean=3.5, sd=1.5, n=100, lo=1, hi=7,
                   max_iter=10, n_seeds=1)
        assert r['possible'] is None
        assert r['detail'].startswith('FLAG')
        assert 'budget' in r['detail']

    def test_n_zero_returns_clean_result(self):
        r = sprite(mean=5.0, sd=1.0, n=0, lo=1, hi=7)
        assert r['possible'] is None


# ═══════════════════════════════════════════════════════════════════════════════
# correlation_bound: rounding tolerance + zero denominator (bug 5)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCorrelationBoundRounding:
    def test_correctly_rounded_sds_pass(self):
        """SDs 2.6, 2.8, 0.1 from a genuine r=1.0 dataset (rounded to 1dp)
        must PASS: implied r ≤ 1 somewhere in the ±half-ulp box."""
        r = correlation_bound(2.6, 2.8, 0.1)
        assert r['possible'], r['detail']

    def test_genuinely_impossible_still_fails(self):
        """Pre 0.10, Post 0.30, Change 0.05: |r|>1 across the whole
        rounding interval — must stay FAIL."""
        r = correlation_bound(0.10, 0.30, 0.05)
        assert not r['possible'], r['detail']

    def test_zero_denominator_is_undetermined(self):
        """Constant pre/post data is valid; r is undefined, not impossible."""
        r = correlation_bound(0, 0, 0)
        assert r['possible'] is None
        assert 'UNDETERMINED' in r['detail']


# ═══════════════════════════════════════════════════════════════════════════════
# Zero-variance degenerate cases (bug 6)
# ═══════════════════════════════════════════════════════════════════════════════

class TestZeroVarianceDegenerate:
    """SD exactly 0 → degenerate/cannot-recompute, never 'impossible'.
    Negative SD stays FAIL."""

    def test_paired_ttest_zero_sd_degenerate(self):
        r = check_ttest_paired(1.0, 0.0, 10, 0.001)
        assert r['plausible'] is None
        assert 'degenerate' in r['detail']
        assert 'FAIL' not in r['detail']

    def test_paired_ttest_negative_sd_fails(self):
        r = check_ttest_paired(1.0, -1.0, 10, 0.001)
        assert r['plausible'] is False
        assert 'FAIL' in r['detail']

    def test_independent_ttest_zero_se_degenerate(self):
        r = check_ttest_independent(5.0, 0.0, 10, 5.0, 0.0, 10, 0.5)
        assert r['plausible'] is None
        assert 'degenerate' in r['detail']

    def test_independent_ttest_negative_sd_fails(self):
        r = check_ttest_independent(5.0, -1.0, 10, 5.0, 1.0, 10, 0.5)
        assert r['plausible'] is False

    def test_anova_zero_within_variance_degenerate(self):
        r = check_anova_oneway([5.0, 6.0], [0.0, 0.0], [10, 10])
        assert 'degenerate' in r['detail']
        assert 'FAIL' not in r['detail']

    def test_anova_negative_sd_fails(self):
        r = check_anova_oneway([5.0, 6.0], [-1.0, 1.0], [10, 10])
        assert 'FAIL' in r['detail']


# ═══════════════════════════════════════════════════════════════════════════════
# quick_sd_check: n-aware sample-SD bound (bug 7)
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuickSdCheck:
    def test_sample_sd_above_population_bound_is_possible(self):
        """[0, 0, 10] has sample SD 5.774 > range/2 — must not be branded
        impossible when n=3 is known."""
        r = quick_sd_check(5.77, 3, 0, 10)
        assert not any('IMPOSSIBLE' in f for f in r['flags']), r['flags']

    def test_above_n_aware_bound_still_impossible(self):
        """(range/2)*sqrt(3/2) = 6.124; 6.2 exceeds it."""
        r = quick_sd_check(6.2, 3, 0, 10)
        assert any('IMPOSSIBLE' in f for f in r['flags']), r['flags']

    def test_impossible_does_not_skip_bimodality_flag(self):
        """The impossible flag must not short-circuit the softer flag."""
        r = quick_sd_check(6.2, 3, 0, 10)
        assert any('bimodal' in f for f in r['flags']), r['flags']

    def test_unknown_n_uses_population_bound(self):
        r = quick_sd_check(5.1, None, 0, 10)
        assert any('IMPOSSIBLE' in f for f in r['flags']), r['flags']


# ═══════════════════════════════════════════════════════════════════════════════
# sample_size_from_t: rounding-aware p inversion (bug 8)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSampleSizeFromT:
    def test_consistent_ns_pass(self):
        """t=2.5, p=0.02: every n in 16-64 gives an exact p that rounds
        to 0.02, so all must PASS."""
        flagged = [n for n in range(16, 65)
                   if not sample_size_from_t(2.5, 0.02, n)['plausible']]
        assert flagged == [], f"falsely flagged: {flagged}"

    def test_inconsistent_p_flagged(self):
        """t=2.5, n=44 gives p≈0.016 — a reported p=0.2 is inconsistent
        over its whole rounding interval [0.15, 0.25]."""
        r = sample_size_from_t(2.5, 0.2, 44)
        assert r['plausible'] is False

    def test_implied_n_range_returned(self):
        r = sample_size_from_t(2.5, 0.02, 44)
        lo, hi = r['implied_n_range']
        assert lo <= 20 and hi >= 60


# ═══════════════════════════════════════════════════════════════════════════════
# grim_percentage (formerly misnamed 'debit') (bug 9)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGrimPercentage:
    def test_grim_percentage_works(self):
        """40.0% of 26 = 10.4 people — impossible at 1dp."""
        r = grim_percentage(40.0, 26)
        assert not r['possible']

    def test_debit_alias_deprecated_and_equivalent(self):
        with pytest.warns(DeprecationWarning):
            r_old = debit(40.0, 26)
        r_new = grim_percentage(40.0, 26)
        assert r_old['possible'] == r_new['possible']
        assert r_old['implied_count'] == r_new['implied_count']

    def test_docstring_is_not_invented_debit(self):
        doc = grim_percentage.__doc__
        assert 'Distribution of Effects Based on Imprecise Totals' not in doc
        assert 'Brown & Heathers' in doc  # GRIM citation
        assert 'pm825' in doc             # points at the real DEBIT

    def test_n_zero_returns_clean_result(self):
        r = grim_percentage(50.0, 0)
        assert r['possible'] is None


# ═══════════════════════════════════════════════════════════════════════════════
# check_chi_squared: Yates continuity correction for 2x2 (bug 10)
# ═══════════════════════════════════════════════════════════════════════════════

class TestChiSquaredYates:
    TABLE = [[10, 20], [20, 10]]  # Pearson 6.667, Yates 5.4

    def test_yates_reported_value_passes(self):
        r = check_chi_squared(self.TABLE, reported_chi2=5.4)
        assert r['consistent'], r['detail']
        assert r['chi2_matched'] == 'yates'

    def test_pearson_reported_value_passes(self):
        r = check_chi_squared(self.TABLE, reported_chi2=6.67)
        assert r['consistent'], r['detail']
        assert r['chi2_matched'] == 'pearson'

    def test_neither_still_flags(self):
        r = check_chi_squared(self.TABLE, reported_chi2=12.0)
        assert not r['consistent']


# ═══════════════════════════════════════════════════════════════════════════════
# Module citations: GRIMMER = Anaya 2016, SPRITE = Heathers et al. 2018 (bug 11)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCitations:
    def test_grimmer_cited_to_anaya_2016(self):
        import paperscope.analysis.forensic_stats as fs
        ref_lines = [l for l in fs.__doc__.splitlines()
                     if 'GRIMMER' in l and 'doi' in l]
        assert ref_lines and all('Anaya (2016)' in l for l in ref_lines)
        assert 'Anaya (2016)' in grimmer.__doc__

    def test_sprite_cited_to_heathers_et_al_2018(self):
        import paperscope.analysis.forensic_stats as fs
        ref_lines = [l for l in fs.__doc__.splitlines()
                     if 'SPRITE' in l and 'doi' in l]
        assert ref_lines
        assert all('Heathers' in l and '2018' in l for l in ref_lines)
        assert '2018' in sprite.__doc__


class TestSpriteSumPreservation:
    """Codex re-review: sprite could accept datasets with the wrong mean.

    The variance-decreasing perturbation moved data[far] without always
    compensating data[near], so the sum drifted off target; acceptance
    then only checked the SD interval.
    """

    def test_wrong_mean_sd_pair_fails(self):
        # mean 1.0 (1dp) with n=3 admits only sum 3; triples summing to 3
        # have SD 0, 1.0, or 1.732 — SD 1.2 is impossible.
        r = sprite(mean=1.0, sd=1.2, n=3, lo=0, hi=5,
                                  dp=1, dp_sd=1, max_iter=50_000)
        assert r['possible'] is not True

    def test_example_dataset_always_matches_reported_mean(self):
        r = sprite(mean=3.5, sd=1.0, n=20, lo=1, hi=7, dp=1)
        if r.get('example_dataset'):
            m = sum(r['example_dataset']) / len(r['example_dataset'])
            assert round(m, 1) == 3.5


class TestGrimmerRepresentability:
    """Codex re-review: parity is necessary, not sufficient.

    sum=15, sumsq=79, n=3 passes the parity gate but no integer triple
    achieves it (deviations need x^2+xy+y^2 = 2, not a Loeschian number).
    """

    def test_parity_consistent_but_unrepresentable_fails(self):
        r = grimmer(mean="5.0", sd="1.4", n=3)
        assert r['possible'] is not True

    def test_representable_case_still_passes(self):
        # [4, 5, 6]: mean 5.0, sample SD 1.0
        r = grimmer(mean="5.0", sd="1.0", n=3)
        assert r['possible'] is True

    def test_likert_multi_sum_case_still_passes(self):
        r = grimmer(mean="2.6", sd="1.52", n=25)
        assert r['possible'] is True

    def test_zero_sd_still_passes(self):
        r = grimmer(mean="5.0", sd="0.0", n=10)
        assert r['possible'] is True


class TestQuickSdCheckOddN:
    """Codex re-review: the even-split bound overestimates for odd n."""

    def test_odd_n_uses_floor_ceil_split_bound(self):
        # n=3 on [0,10]: true max sample SD is [0,0,10] -> 5.7735,
        # not (range/2)*sqrt(n/(n-1)) = 6.1237
        r = quick_sd_check(sd=6.0, n=3, lo=0, hi=10)
        assert any('IMPOSSIBLE' in f for f in r['flags'])

    def test_odd_n_true_max_still_possible(self):
        r = quick_sd_check(sd=5.77, n=3, lo=0, hi=10)
        assert not any('IMPOSSIBLE' in f for f in r['flags'])

    def test_even_n_bound_unchanged(self):
        # n=4 on [0,10]: [0,0,10,10] -> sample SD 5.7735
        r = quick_sd_check(sd=5.77, n=4, lo=0, hi=10)
        assert not any('IMPOSSIBLE' in f for f in r['flags'])
