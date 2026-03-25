#!/usr/bin/env python3
"""
Forensic statistics checker for peer review.

Implements the data-integrity tests used by statistical sleuths
(Meyerowitz-Katz, Brown/Heathers GRIM, etc.) to detect impossible
or implausible summary statistics in published papers.

Usage:
    python -m paperscope.analysis.forensic_stats          # run demo
    python -m paperscope.analysis.forensic_stats --help    # show help

In practice, import the functions and feed in extracted table data:

    from paperscope.analysis.forensic_stats import (
        grim, grimmer, debit, sprite, correlation_bound,
        check_ttest_paired, check_ttest_independent,
        check_anova_oneway, check_chi_squared,
        sample_size_from_t, effect_size_consistency,
        carlisle_stouffer_fisher, check_sd_se_confusion,
        quick_sd_check, check_contingency_table,
        benfords_law, variance_ratio_test,
        check_change_arithmetic, check_sd_positive,
    )

References:
    Heathers (2025) "An Introduction to Forensic Metascience" doi:10.5281/zenodo.14871843
    Brown & Heathers (2017) "The GRIM Test" doi:10.1177/1948550616673876
    Heathers & Brown (2019) "GRIMMER" doi:10.31234/osf.io/6cn2h
    Jane (2024) matthewbjane.github.io/blog-posts/blog-post-1.html
    Anaya (2016) "The SPRITE Procedure" doi:10.7287/peerj.preprints.2748v1
    Carlisle (2017) doi:10.1111/anae.13938
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Tuple

from scipy import stats as sp


# ═══════════════════════════════════════════════════════════════════════════════
# 1. GRIM (Granularity-Related Inconsistency of Means)
# ═══════════════════════════════════════════════════════════════════════════════

def grim(mean: float, n: int, scale: int = 1, dp: int = 2) -> dict:
    """
    GRIM test: is this mean possible for n integer-valued observations?

    Args:
        mean:  reported mean
        n:     sample size
        scale: granularity of the instrument (1 for integers, 0.5 for
               half-points, etc.)
        dp:    decimal places reported (2 = reported to hundredths)

    Returns:
        dict with 'possible' (bool), 'implied_sum', 'nearest_achievable',
        and 'detail' (str).
    """
    implied_sum = mean * n
    granularity = scale
    remainder = (implied_sum / granularity) % 1.0

    # Rounding tolerance: last decimal place could be ±0.5 units
    tolerance = 0.5 * (10 ** -dp) * n
    near_integer = (remainder < (tolerance / granularity) or
                    remainder > 1 - (tolerance / granularity))

    lower = math.floor(implied_sum / granularity) * granularity / n
    upper = math.ceil(implied_sum / granularity) * granularity / n

    result = {
        'possible': near_integer,
        'reported_mean': mean,
        'n': n,
        'implied_sum': round(implied_sum, dp + 2),
        'nearest_achievable': [round(lower, dp + 2), round(upper, dp + 2)],
    }
    if near_integer:
        result['detail'] = f"PASS: mean {mean} is achievable with n={n}"
    else:
        result['detail'] = (
            f"FAIL: mean {mean} x n={n} = {implied_sum:.4f}; "
            f"nearest achievable means are {lower:.{dp+2}f} and {upper:.{dp+2}f}"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DEBIT (Distribution of Effects Based on Imprecise Totals)
# ═══════════════════════════════════════════════════════════════════════════════

def debit(percentage: float, n: int, dp: int = 1) -> dict:
    """
    DEBIT: GRIM for percentages/proportions from discrete counts.

    If a paper says "88.5% of 26 participants responded", that implies
    26 * 0.885 = 23.01 people — impossible. The count must be an integer.

    Args:
        percentage: reported percentage (e.g. 88.5 for 88.5%)
        n:          sample size (denominator)
        dp:         decimal places in the reported percentage

    Returns:
        dict with 'possible', 'implied_count', 'nearest_achievable', 'detail'.
    """
    proportion = percentage / 100.0
    implied_count = proportion * n

    # The count must be an integer
    tolerance = 0.5 * (10 ** -dp) / 100.0 * n
    near_integer = abs(implied_count - round(implied_count)) <= tolerance

    lower_count = math.floor(implied_count)
    upper_count = math.ceil(implied_count)
    lower_pct = round(lower_count / n * 100, dp + 2)
    upper_pct = round(upper_count / n * 100, dp + 2)

    result = {
        'possible': near_integer,
        'reported_percentage': percentage,
        'n': n,
        'implied_count': round(implied_count, 4),
        'nearest_achievable_pcts': [lower_pct, upper_pct],
        'nearest_achievable_counts': [lower_count, upper_count],
    }
    if near_integer:
        result['detail'] = (
            f"PASS: {percentage}% of {n} = {implied_count:.2f} "
            f"(rounds to integer {round(implied_count)})"
        )
    else:
        result['detail'] = (
            f"FAIL: {percentage}% of {n} = {implied_count:.4f} people — "
            f"not an integer. Nearest achievable: "
            f"{lower_pct}% ({lower_count}/{n}) or "
            f"{upper_pct}% ({upper_count}/{n})"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 3. SPRITE (Sample Parameter Reconstruction via Iterative TEchniques)
# ═══════════════════════════════════════════════════════════════════════════════

def sprite(
    mean: float,
    sd: float,
    n: int,
    lo: int = 0,
    hi: int = 63,
    max_iter: int = 2_000_000,
    n_seeds: int = 5,
    seed: int = 42,
    dp: Optional[int] = None,
) -> dict:
    """
    SPRITE: attempt to reconstruct a valid dataset that produces the
    reported mean and SD for bounded integer data.

    If no valid dataset exists, the reported statistics are impossible.

    Two-phase approach:
      Phase 1 (analytical): enumerate all integer sums compatible with
        the reported mean (within rounding), then check whether valid
        integer sum-of-squares targets exist for the reported SD.
      Phase 2 (search): for each feasible (sum, sum_sq) pair, run
        randomized perturbation search with multiple seeds.

    Args:
        mean: reported mean
        sd:   reported standard deviation
        n:    sample size
        lo:   minimum possible value (e.g. 0 for BDI)
        hi:   maximum possible value (e.g. 63 for BDI)
        max_iter: perturbation attempts per seed per target sum (default 2M)
        n_seeds:  number of independent random seeds to try per sum
        seed: base random seed for reproducibility
        dp:   decimal places of the reported mean (auto-detected if None)

    Returns:
        dict with 'possible', 'grim_possible', 'n_target_sums',
        'n_sumsq_targets', 'example_dataset', 'closest', and 'detail'.
    """
    # Auto-detect decimal places
    if dp is None:
        s = str(mean)
        dp = len(s.split('.')[-1]) if '.' in s else 0

    # ── Phase 1: analytical feasibility ──
    half_unit = 0.5 * 10**(-dp)
    lo_mean = mean - half_unit
    hi_mean = mean + half_unit
    lo_sum = max(math.ceil(lo_mean * n), lo * n)
    hi_sum = min(math.floor(hi_mean * n), hi * n)
    possible_sums = list(range(lo_sum, hi_sum + 1))

    if not possible_sums:
        return {
            'possible': False,
            'grim_possible': False,
            'n_target_sums': 0,
            'detail': (
                f"FAIL: no integer sum compatible with mean={mean}, n={n} "
                f"(GRIM failure). Range [{lo_mean*n:.4f}, {hi_mean*n:.4f}] "
                f"contains no integer."
            ),
        }

    # For each possible sum, find valid sum-of-squares range
    sd_lo = sd - 0.05  # rounding tolerance on SD (1 dp)
    sd_hi = sd + 0.05
    target_var = sd ** 2

    feasible_targets = []  # list of (target_sum, lo_sumsq, hi_sumsq)
    total_sumsq_targets = 0
    for ts in possible_sums:
        lo_sumsq = sd_lo**2 * (n - 1) + ts**2 / n
        hi_sumsq = sd_hi**2 * (n - 1) + ts**2 / n
        lo_int = math.ceil(lo_sumsq)
        hi_int = math.floor(hi_sumsq)
        if lo_int <= hi_int:
            feasible_targets.append((ts, lo_int, hi_int))
            total_sumsq_targets += hi_int - lo_int + 1

    # ── Phase 2: randomized search ──
    best_var_diff = float('inf')
    best_dataset = None
    best_stats = None
    found_dataset = None

    for target_sum, _, _ in feasible_targets:
        for seed_offset in range(n_seeds):
            if found_dataset is not None:
                break

            rng = random.Random(seed + seed_offset + target_sum)

            # Initialize dataset to hit target sum
            data = [lo] * n
            remaining = target_sum - lo * n
            for i in range(n):
                add = min(remaining, hi - lo)
                data[i] = lo + add
                remaining -= add
                if remaining <= 0:
                    break
            rng.shuffle(data)

            for _ in range(max_iter):
                cur_mean = sum(data) / n
                cur_var = sum((x - cur_mean) ** 2 for x in data) / (n - 1)
                vd = abs(cur_var - target_var)

                if vd < best_var_diff:
                    best_var_diff = vd
                    best_dataset = list(data)
                    best_stats = (cur_mean, cur_var ** 0.5)

                if vd < 0.005:
                    found_dataset = list(data)
                    break

                # Perturb: swap toward/away from target variance
                i, j = rng.sample(range(n), 2)
                if cur_var < target_var:
                    if data[i] < hi and data[j] > lo:
                        data[i] += 1
                        data[j] -= 1
                else:
                    mid = int(round(cur_mean))
                    if abs(data[i] - mid) > abs(data[j] - mid):
                        far, near = i, j
                    else:
                        far, near = j, i
                    if data[far] > mid and data[far] > lo:
                        data[far] -= 1
                        if data[near] < hi:
                            data[near] += 1
                    elif data[far] < mid and data[far] < 63:
                        data[far] += 1
                        if data[near] > lo:
                            data[near] -= 1

        if found_dataset is not None:
            break

    # ── Build result ──
    result = {
        'possible': found_dataset is not None,
        'grim_possible': True,
        'n_target_sums': len(possible_sums),
        'possible_sums': possible_sums,
        'n_feasible_sum_targets': len(feasible_targets),
        'n_sumsq_targets': total_sumsq_targets,
        'target_mean': mean,
        'target_sd': sd,
        'n': n,
        'range': [lo, hi],
        'max_iter': max_iter,
        'n_seeds': n_seeds,
        'total_iterations': max_iter * n_seeds * len(feasible_targets),
    }

    if found_dataset is not None:
        example = sorted(found_dataset)
        actual_mean = sum(example) / n
        actual_sd = (sum((x - actual_mean) ** 2 for x in example) / (n - 1)) ** 0.5
        result['example_dataset'] = example
        result['reconstructed_mean'] = round(actual_mean, 4)
        result['reconstructed_sd'] = round(actual_sd, 4)
        result['detail'] = (
            f"PASS: valid dataset found. "
            f"Reconstructs mean={actual_mean:.4f}, SD={actual_sd:.4f}"
        )
    else:
        result['closest_var_diff'] = round(best_var_diff, 6)
        if best_stats:
            result['closest_mean'] = round(best_stats[0], 4)
            result['closest_sd'] = round(best_stats[1], 4)
        if not feasible_targets:
            result['detail'] = (
                f"FAIL: GRIM passes but no integer sum-of-squares is compatible "
                f"with SD={sd} for any valid sum. "
                f"The mean and SD are mutually impossible for n={n}, range=[{lo},{hi}]."
            )
        else:
            result['detail'] = (
                f"FLAG: {total_sumsq_targets} valid (sum, sum_sq) targets exist, "
                f"but no dataset found in {result['total_iterations']:,} iterations "
                f"({n_seeds} seeds x {len(feasible_targets)} targets x {max_iter:,}). "
                f"Closest SD: {best_stats[1]:.4f} (target {sd}, gap {best_var_diff:.6f}). "
                f"Statistics may be achievable but are highly constrained."
            )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Correlation bound from pre/post/change SDs
# ═══════════════════════════════════════════════════════════════════════════════

def correlation_bound(sd_pre: float, sd_post: float, sd_change: float) -> dict:
    """
    Reverse-engineer the implied Pearson r between pre and post scores
    from their SDs and the SD of the change score.

    Var(change) = Var(pre) + Var(post) - 2*r*SD(pre)*SD(post)
    => r = (SD_pre^2 + SD_post^2 - SD_change^2) / (2 * SD_pre * SD_post)

    If |r| > 1, the reported SDs are mutually inconsistent.
    """
    numerator = sd_pre**2 + sd_post**2 - sd_change**2
    denominator = 2 * sd_pre * sd_post

    if denominator == 0:
        return {
            'possible': False,
            'implied_r': float('inf'),
            'detail': "FAIL: denominator is zero (one or both SDs are 0)"
        }

    implied_r = numerator / denominator
    min_sd_change = abs(sd_pre - sd_post)
    max_sd_change = sd_pre + sd_post

    possible = -1.0 <= round(implied_r, 6) <= 1.0
    result = {
        'possible': possible,
        'implied_r': round(implied_r, 4),
        'sd_pre': sd_pre,
        'sd_post': sd_post,
        'sd_change': sd_change,
        'min_possible_sd_change': round(min_sd_change, 4),
        'max_possible_sd_change': round(max_sd_change, 4),
    }
    if possible:
        result['detail'] = (
            f"PASS: implied r = {implied_r:.4f} (within [-1, 1]). "
            f"Plausible SD(change) range: [{min_sd_change:.4f}, {max_sd_change:.4f}]"
        )
    else:
        result['detail'] = (
            f"FAIL: implied r = {implied_r:.4f} — IMPOSSIBLE (outside [-1, 1]). "
            f"Reported SD(change) = {sd_change}, but valid range is "
            f"[{min_sd_change:.4f}, {max_sd_change:.4f}]"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 5. P-value recalculation
# ═══════════════════════════════════════════════════════════════════════════════

def check_ttest_paired(mean_change: float, sd_change: float, n: int,
                       reported_p: float) -> dict:
    """Recalculate a paired t-test p-value from reported change statistics."""
    if sd_change <= 0:
        return {
            'plausible': False,
            'detail': f"FAIL: SD of change ({sd_change}) is <= 0, impossible"
        }

    se = sd_change / math.sqrt(n)
    t_val = mean_change / se
    df = n - 1
    p_calc = sp.t.sf(abs(t_val), df) * 2

    ratio = max(p_calc, 1e-20) / max(reported_p, 1e-20)
    plausible = 0.1 < ratio < 10

    return {
        'plausible': plausible,
        't_calculated': round(t_val, 4),
        'df': df,
        'p_calculated': p_calc,
        'p_reported': reported_p,
        'ratio': round(ratio, 2),
        'detail': (
            f"{'PASS' if plausible else 'FLAG'}: "
            f"t({df}) = {t_val:.4f}, calculated p = {p_calc:.2e}, "
            f"reported p = {reported_p}. "
            f"Ratio = {ratio:.1f}x"
        )
    }


def check_ttest_independent(mean1: float, sd1: float, n1: int,
                            mean2: float, sd2: float, n2: int,
                            reported_p: float) -> dict:
    """Recalculate an independent-samples t-test (Welch's) from reported stats."""
    se = math.sqrt(sd1**2 / n1 + sd2**2 / n2)
    if se == 0:
        return {'plausible': False, 'detail': "FAIL: pooled SE is 0"}

    t_val = (mean1 - mean2) / se
    num = (sd1**2 / n1 + sd2**2 / n2)**2
    den = (sd1**2 / n1)**2 / (n1 - 1) + (sd2**2 / n2)**2 / (n2 - 1)
    df = num / den
    p_calc = sp.t.sf(abs(t_val), df) * 2

    ratio = max(p_calc, 1e-20) / max(reported_p, 1e-20)
    plausible = 0.1 < ratio < 10

    return {
        'plausible': plausible,
        't_calculated': round(t_val, 4),
        'df': round(df, 2),
        'p_calculated': p_calc,
        'p_reported': reported_p,
        'ratio': round(ratio, 2),
        'detail': (
            f"{'PASS' if plausible else 'FLAG'}: "
            f"t({df:.1f}) = {t_val:.4f}, calculated p = {p_calc:.2e}, "
            f"reported p = {reported_p}. Ratio = {ratio:.1f}x"
        )
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Sample size back-calculation
# ═══════════════════════════════════════════════════════════════════════════════

def sample_size_from_t(t_val: float, p_reported: float,
                       reported_n: int, two_tailed: bool = True) -> dict:
    """
    From a reported t-statistic and p-value, back-calculate what df (and
    hence n) would be needed. Compare with the stated n.

    Args:
        t_val:       reported t-statistic
        p_reported:  reported p-value
        reported_n:  stated sample size (for comparison)
        two_tailed:  whether the test is two-tailed
    """
    # Find df that produces reported_p for the given t
    # p = 2 * sf(|t|, df) for two-tailed
    # We search df from 1 to 10000
    best_df = None
    best_diff = float('inf')

    for df_candidate in range(1, 10001):
        if two_tailed:
            p_calc = sp.t.sf(abs(t_val), df_candidate) * 2
        else:
            p_calc = sp.t.sf(abs(t_val), df_candidate)
        diff = abs(p_calc - p_reported)
        if diff < best_diff:
            best_diff = diff
            best_df = df_candidate

    implied_n = best_df + 1  # for one-sample/paired: n = df + 1

    match = abs(implied_n - reported_n) <= 2  # allow small rounding

    return {
        'plausible': match,
        'implied_df': best_df,
        'implied_n': implied_n,
        'reported_n': reported_n,
        'discrepancy': implied_n - reported_n,
        'detail': (
            f"{'PASS' if match else 'FLAG'}: "
            f"t={t_val} with p={p_reported} implies df={best_df} (n~{implied_n}), "
            f"reported n={reported_n}"
            f"{'' if match else f' [discrepancy: {implied_n - reported_n}]'}"
        )
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Effect size consistency (RIVETS-style)
# ═══════════════════════════════════════════════════════════════════════════════

def effect_size_consistency(
    mean1: float, sd1: float, n1: int,
    mean2: float, sd2: float, n2: int,
    reported_d: Optional[float] = None,
    reported_p: Optional[float] = None,
    reported_ci_lower: Optional[float] = None,
    reported_ci_upper: Optional[float] = None,
) -> dict:
    """
    Check mutual consistency of reported effect sizes, p-values, and CIs.

    Computes Cohen's d, t-statistic, p-value, and 95% CI from the raw
    statistics and flags discrepancies with any reported values.
    """
    # Pooled SD (Cohen's d denominator)
    pooled_sd = math.sqrt(((n1 - 1) * sd1**2 + (n2 - 1) * sd2**2) / (n1 + n2 - 2))
    if pooled_sd == 0:
        return {'possible': False, 'detail': "FAIL: pooled SD is 0"}

    calc_d = (mean1 - mean2) / pooled_sd

    # t and p via Welch's
    se = math.sqrt(sd1**2 / n1 + sd2**2 / n2)
    t_val = (mean1 - mean2) / se if se > 0 else float('inf')
    num = (sd1**2 / n1 + sd2**2 / n2)**2
    den = (sd1**2 / n1)**2 / (n1 - 1) + (sd2**2 / n2)**2 / (n2 - 1)
    df = num / den if den > 0 else 1
    calc_p = sp.t.sf(abs(t_val), df) * 2

    # 95% CI for the mean difference
    diff = mean1 - mean2
    t_crit = sp.t.ppf(0.975, df)
    ci_lower = float(diff - t_crit * se)
    ci_upper = float(diff + t_crit * se)

    flags = []

    if reported_d is not None:
        d_diff = abs(calc_d - reported_d)
        if d_diff > 0.1:
            flags.append(
                f"Cohen's d: calculated {calc_d:.3f}, reported {reported_d:.3f} "
                f"(diff {d_diff:.3f})"
            )

    if reported_p is not None:
        ratio = max(calc_p, 1e-20) / max(reported_p, 1e-20)
        if not (0.1 < ratio < 10):
            flags.append(
                f"p-value: calculated {calc_p:.2e}, reported {reported_p} "
                f"(ratio {ratio:.1f}x)"
            )

    if reported_ci_lower is not None and reported_ci_upper is not None:
        ci_lower_diff = abs(ci_lower - reported_ci_lower)
        ci_upper_diff = abs(ci_upper - reported_ci_upper)
        if ci_lower_diff > 0.5 or ci_upper_diff > 0.5:
            flags.append(
                f"95% CI: calculated [{ci_lower:.2f}, {ci_upper:.2f}], "
                f"reported [{reported_ci_lower}, {reported_ci_upper}]"
            )

    consistent = len(flags) == 0
    result = {
        'consistent': consistent,
        'calculated_d': round(calc_d, 4),
        'calculated_p': calc_p,
        'calculated_ci': [round(ci_lower, 4), round(ci_upper, 4)],
        'calculated_t': round(t_val, 4),
        'df': round(df, 2),
        'flags': flags,
    }
    if consistent:
        result['detail'] = (
            f"PASS: effect sizes internally consistent. "
            f"d={calc_d:.3f}, p={calc_p:.2e}, 95% CI [{ci_lower:.2f}, {ci_upper:.2f}]"
        )
    else:
        result['detail'] = (
            f"FLAG: {len(flags)} inconsistenc{'y' if len(flags) == 1 else 'ies'} "
            f"detected: {'; '.join(flags)}"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Benford's law
# ═══════════════════════════════════════════════════════════════════════════════

def benfords_law(values: List[float], label: str = "") -> dict:
    """
    Test whether the first digits of a set of values follow Benford's
    distribution. Fabricated data tends to have too-uniform first digits.

    Uses a chi-squared goodness-of-fit test. Requires >= 50 values
    for meaningful results.

    Args:
        values: list of numeric values (zeros and negatives are handled)
        label:  optional label for the dataset
    """
    # Extract first significant digits
    digits = []
    for v in values:
        v = abs(v)
        if v == 0:
            continue
        # Normalize to [1, 10)
        while v < 1:
            v *= 10
        while v >= 10:
            v /= 10
        digits.append(int(v))

    n = len(digits)
    if n < 50:
        return {
            'sufficient_data': False,
            'n': n,
            'detail': f"SKIP: only {n} values; need >= 50 for Benford's test"
        }

    # Expected Benford frequencies
    benford_expected = {d: math.log10(1 + 1/d) for d in range(1, 10)}

    observed = Counter(digits)
    chi2 = 0
    digit_details = {}
    for d in range(1, 10):
        obs = observed.get(d, 0)
        exp = benford_expected[d] * n
        chi2 += (obs - exp) ** 2 / exp
        digit_details[d] = {
            'observed': obs,
            'expected': round(exp, 1),
            'obs_pct': round(obs / n * 100, 1),
            'exp_pct': round(benford_expected[d] * 100, 1),
        }

    # Chi-squared with 8 df (9 digits - 1)
    p_value = sp.chi2.sf(chi2, df=8)
    conforms = p_value > 0.05

    result = {
        'conforms': conforms,
        'chi2': round(chi2, 4),
        'p_value': round(p_value, 6),
        'n': n,
        'digit_details': digit_details,
    }
    if conforms:
        result['detail'] = (
            f"PASS: {label + ': ' if label else ''}"
            f"first digits conform to Benford's law "
            f"(chi2={chi2:.2f}, p={p_value:.4f}, n={n})"
        )
    else:
        result['detail'] = (
            f"FLAG: {label + ': ' if label else ''}"
            f"first digits deviate from Benford's law "
            f"(chi2={chi2:.2f}, p={p_value:.4f}, n={n}). "
            f"May indicate fabrication or non-natural data generation."
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Variance ratio test
# ═══════════════════════════════════════════════════════════════════════════════

def variance_ratio_test(
    sds: List[float],
    ns: List[int],
    labels: Optional[List[str]] = None,
) -> dict:
    """
    Check whether the reported SDs across groups are implausibly similar.

    Fabricated data often shows nearly identical SDs across treatment
    groups because fabricators assume "random" means "equal variance."

    Uses an F-test on the ratio of largest to smallest variance and
    flags suspiciously uniform SDs.

    Args:
        sds:    list of reported SDs (one per group)
        ns:     list of sample sizes (one per group)
        labels: optional group labels
    """
    if len(sds) < 2:
        return {'detail': "SKIP: need at least 2 groups for variance ratio test"}

    if labels is None:
        labels = [f"Group {i+1}" for i in range(len(sds))]

    variances = [sd**2 for sd in sds]
    max_var = max(variances)
    min_var = min(variances)

    if min_var == 0:
        return {
            'possible': False,
            'detail': "FLAG: at least one group has SD = 0"
        }

    f_ratio = max_var / min_var
    max_idx = variances.index(max_var)
    min_idx = variances.index(min_var)

    # F-test
    df1 = ns[max_idx] - 1
    df2 = ns[min_idx] - 1
    p_value = sp.f.sf(f_ratio, df1, df2) * 2  # two-tailed

    # Suspiciously similar: F-ratio very close to 1 for small samples
    # (in real data, small samples produce noisy variance estimates)
    total_n = sum(ns)
    suspiciously_similar = (f_ratio < 1.05 and total_n < 100 and len(sds) >= 3)

    result = {
        'f_ratio': round(f_ratio, 4),
        'p_value': round(p_value, 6),
        'suspiciously_similar': suspiciously_similar,
        'sds': dict(zip(labels, [round(s, 4) for s in sds])),
        'max_group': labels[max_idx],
        'min_group': labels[min_idx],
    }

    flags = []
    if suspiciously_similar:
        flags.append(
            f"SDs are suspiciously similar (F={f_ratio:.4f}) for "
            f"small samples (total n={total_n})"
        )
    if p_value < 0.01:
        flags.append(
            f"Significant variance heterogeneity (F={f_ratio:.2f}, p={p_value:.4f})"
        )

    result['flags'] = flags
    if flags:
        result['detail'] = f"FLAG: {'; '.join(flags)}"
    else:
        result['detail'] = (
            f"PASS: variance ratio F={f_ratio:.2f} between "
            f"{labels[max_idx]} and {labels[min_idx]} (p={p_value:.4f})"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Arithmetic consistency + SD sign check
# ═══════════════════════════════════════════════════════════════════════════════

def check_change_arithmetic(baseline: float, end: float,
                            reported_change: float, label: str = "",
                            tolerance: float = 0.15) -> dict:
    """Check whether End - Baseline = reported Change (within rounding)."""
    expected = round(end - baseline, 4)
    diff = abs(expected - reported_change)
    ok = diff <= tolerance

    return {
        'consistent': ok,
        'expected_change': expected,
        'reported_change': reported_change,
        'discrepancy': round(diff, 4),
        'detail': (
            f"{'PASS' if ok else 'FAIL'}: {label + ': ' if label else ''}"
            f"End ({end}) - Baseline ({baseline}) = {expected}, "
            f"reported as {reported_change}"
            f"{'' if ok else f' [discrepancy: {diff:.4f}]'}"
        )
    }


def check_sd_positive(sd: float, label: str = "") -> dict:
    """SDs cannot be negative."""
    ok = sd >= 0
    return {
        'possible': ok,
        'sd': sd,
        'detail': (
            f"{'PASS' if ok else 'FAIL'}: {label + ': ' if label else ''}"
            f"SD = {sd}"
            f"{'' if ok else ' — IMPOSSIBLE: standard deviation cannot be negative'}"
        )
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 11. GRIMMER (SD consistency for integer data)
# ═══════════════════════════════════════════════════════════════════════════════

def grimmer(mean: float, sd: float, n: int, scale: int = 1,
            dp_mean: int = 2, dp_sd: int = 2) -> dict:
    """
    GRIMMER test: is this SD possible for n integer-valued observations
    with the given mean?

    Extends GRIM to standard deviations. For integer data with known n
    and mean, the sum of squares must be an integer, which constrains
    the achievable SDs.

    Ref: Heathers & Brown (2019) doi:10.31234/osf.io/6cn2h

    Args:
        mean:    reported mean
        sd:      reported standard deviation
        n:       sample size
        scale:   granularity (1 for integers)
        dp_mean: decimal places of the mean
        dp_sd:   decimal places of the SD
    """
    # First check GRIM
    grim_result = grim(mean, n, scale=scale, dp=dp_mean)
    if not grim_result['possible']:
        return {
            'possible': False,
            'grim_pass': False,
            'detail': f"FAIL: GRIM fails first — mean {mean} is impossible for n={n}"
        }

    # Find the compatible integer sum
    implied_sum = round(mean * n)

    # SD^2 * (n-1) = sum_of_squares - n * mean_exact^2
    # sum_of_squares = SD^2 * (n-1) + implied_sum^2 / n
    exact_mean = implied_sum / n
    target_sumsq = sd**2 * (n - 1) + implied_sum**2 / n

    # Sum of squares must be an integer (sum of integer squares)
    # Allow rounding tolerance
    sd_lo = sd - 0.5 * 10**(-dp_sd)
    sd_hi = sd + 0.5 * 10**(-dp_sd)
    lo_sumsq = sd_lo**2 * (n - 1) + implied_sum**2 / n
    hi_sumsq = sd_hi**2 * (n - 1) + implied_sum**2 / n

    lo_int = math.ceil(lo_sumsq)
    hi_int = math.floor(hi_sumsq)

    possible = lo_int <= hi_int

    result = {
        'possible': possible,
        'grim_pass': True,
        'reported_mean': mean,
        'reported_sd': sd,
        'n': n,
        'implied_sum': implied_sum,
        'sumsq_range': [round(lo_sumsq, 4), round(hi_sumsq, 4)],
        'n_valid_sumsq': max(0, hi_int - lo_int + 1),
    }
    if possible:
        result['detail'] = (
            f"PASS: SD={sd} is achievable with mean={mean}, n={n}. "
            f"{hi_int - lo_int + 1} valid sum-of-squares target(s)."
        )
    else:
        result['detail'] = (
            f"FAIL: SD={sd} is impossible with mean={mean}, n={n}. "
            f"Required sum_sq in [{lo_sumsq:.2f}, {hi_sumsq:.2f}] — "
            f"no integer in range."
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 12. One-way ANOVA recalculation
# ═══════════════════════════════════════════════════════════════════════════════

def check_anova_oneway(
    means: List[float],
    sds: List[float],
    ns: List[int],
    reported_f: Optional[float] = None,
    reported_p: Optional[float] = None,
    labels: Optional[List[str]] = None,
) -> dict:
    """
    Recalculate a one-way ANOVA F-statistic from reported group statistics.

    F = MS_between / MS_within

    Ref: Heathers (2025) ch. "One-way ANOVA"
    """
    k = len(means)
    if k < 2:
        return {'detail': "SKIP: need at least 2 groups"}
    if labels is None:
        labels = [f"Group {i+1}" for i in range(k)]

    N = sum(ns)
    grand_mean = sum(m * n for m, n in zip(means, ns)) / N

    # Between-groups SS
    ss_between = sum(n * (m - grand_mean)**2 for m, n in zip(means, ns))
    df_between = k - 1
    ms_between = ss_between / df_between

    # Within-groups SS (from reported SDs)
    ss_within = sum((n - 1) * sd**2 for n, sd in zip(ns, sds))
    df_within = N - k
    ms_within = ss_within / df_within if df_within > 0 else float('inf')

    if ms_within == 0:
        return {'detail': "FAIL: within-group variance is 0"}

    f_calc = ms_between / ms_within
    p_calc = float(sp.f.sf(f_calc, df_between, df_within))

    flags = []
    if reported_f is not None:
        f_diff = abs(f_calc - reported_f)
        if f_diff > max(0.1, 0.1 * reported_f):
            flags.append(
                f"F: calculated {f_calc:.3f}, reported {reported_f}"
            )

    if reported_p is not None:
        ratio = max(p_calc, 1e-20) / max(reported_p, 1e-20)
        if not (0.1 < ratio < 10):
            flags.append(
                f"p: calculated {p_calc:.2e}, reported {reported_p} "
                f"(ratio {ratio:.1f}x)"
            )

    result = {
        'consistent': len(flags) == 0,
        'f_calculated': round(f_calc, 4),
        'p_calculated': p_calc,
        'df_between': df_between,
        'df_within': df_within,
        'flags': flags,
    }
    if flags:
        result['detail'] = f"FLAG: {'; '.join(flags)}"
    else:
        result['detail'] = (
            f"PASS: F({df_between},{df_within}) = {f_calc:.3f}, "
            f"p = {p_calc:.2e}"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Chi-squared recalculation
# ═══════════════════════════════════════════════════════════════════════════════

def check_chi_squared(
    observed: List[List[int]],
    reported_chi2: Optional[float] = None,
    reported_p: Optional[float] = None,
    label: str = "",
) -> dict:
    """
    Recalculate chi-squared from a contingency table.

    Args:
        observed: 2D list of observed counts (rows x cols)
        reported_chi2: reported chi-squared statistic
        reported_p: reported p-value

    Ref: Heathers (2025) ch. "Chi-squared"
    """
    import numpy as np
    obs = np.array(observed)
    row_totals = obs.sum(axis=1)
    col_totals = obs.sum(axis=0)
    n_total = obs.sum()

    if n_total == 0:
        return {'detail': "FAIL: table sums to 0"}

    # Expected frequencies
    expected = np.outer(row_totals, col_totals) / n_total

    # Chi-squared
    chi2_calc = float(np.sum((obs - expected)**2 / expected))
    df = (obs.shape[0] - 1) * (obs.shape[1] - 1)
    p_calc = float(sp.chi2.sf(chi2_calc, df))

    flags = []
    if reported_chi2 is not None:
        diff = abs(chi2_calc - reported_chi2)
        if diff > max(0.1, 0.05 * reported_chi2):
            flags.append(
                f"chi2: calculated {chi2_calc:.3f}, reported {reported_chi2}"
            )

    if reported_p is not None:
        ratio = max(p_calc, 1e-20) / max(reported_p, 1e-20)
        if not (0.1 < ratio < 10):
            flags.append(
                f"p: calculated {p_calc:.2e}, reported {reported_p}"
            )

    result = {
        'consistent': len(flags) == 0,
        'chi2_calculated': round(chi2_calc, 4),
        'p_calculated': p_calc,
        'df': df,
        'flags': flags,
    }
    if flags:
        result['detail'] = (
            f"FLAG: {label + ': ' if label else ''}{'; '.join(flags)}"
        )
    else:
        result['detail'] = (
            f"PASS: {label + ': ' if label else ''}"
            f"chi2({df}) = {chi2_calc:.3f}, p = {p_calc:.2e}"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 14. SD/SE confusion detector
# ═══════════════════════════════════════════════════════════════════════════════

def check_sd_se_confusion(
    reported_sd: float, n: int, label: str = "",
    known_range: Optional[Tuple[float, float]] = None,
) -> dict:
    """
    Check whether a reported "SD" might actually be an SE (or vice versa).

    If the reported SD seems implausibly small for the data range,
    it may be an SE (SD / sqrt(n)). Conversely, an implausibly large
    "SE" may be an SD.

    Ref: Heathers (2025) ch. "Confusing SD and SE"

    Args:
        reported_sd: the value reported as SD
        n: sample size
        label: variable label
        known_range: (min, max) of the variable if known
    """
    implied_se = reported_sd / math.sqrt(n)
    implied_sd_from_se = reported_sd * math.sqrt(n)

    flags = []

    if known_range is not None:
        data_range = known_range[1] - known_range[0]
        # SD should be < range. If "SD" > range, suspicious.
        if reported_sd > data_range:
            flags.append(
                f"reported SD ({reported_sd}) exceeds data range "
                f"({data_range}) — may be mislabeled"
            )
        # If SD is very small relative to range and n is large,
        # it might be an SE
        if n > 10 and reported_sd < data_range * 0.05:
            flags.append(
                f"reported SD ({reported_sd}) is very small relative to "
                f"range ({data_range}) — might be SE. "
                f"If SE, true SD ~ {implied_sd_from_se:.2f}"
            )

    result = {
        'reported_sd': reported_sd,
        'n': n,
        'implied_se_if_sd': round(implied_se, 4),
        'implied_sd_if_se': round(implied_sd_from_se, 4),
        'flags': flags,
    }
    if flags:
        result['detail'] = (
            f"FLAG: {label + ': ' if label else ''}{'; '.join(flags)}"
        )
    else:
        result['detail'] = (
            f"PASS: {label + ': ' if label else ''}"
            f"SD={reported_sd} (implies SE={implied_se:.4f} for n={n})"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 15. Quick SD check (SD vs range plausibility)
# ═══════════════════════════════════════════════════════════════════════════════

def quick_sd_check(
    sd: float, n: int, lo: float, hi: float, label: str = ""
) -> dict:
    """
    Heathers' 'quick SD check': is the reported SD plausible given the
    possible range of the data?

    For bounded data, SD <= range / 2 always. For most real data,
    SD << range / 2. If SD > range / 2, the data is impossible.

    Also: for integer data, there's a minimum achievable SD > 0 for
    any given n and sum — if the reported SD is below this, flag it.

    Ref: Heathers (2025) ch. "The 'quick' SD check"
    """
    data_range = hi - lo
    max_possible_sd = data_range / 2  # theoretical max (half at each extreme)

    # More realistic upper bound: SD of a uniform distribution = range / sqrt(12)
    uniform_sd = data_range / math.sqrt(12)

    flags = []
    if sd > max_possible_sd:
        flags.append(
            f"SD ({sd}) exceeds theoretical maximum ({max_possible_sd:.2f}) "
            f"for range [{lo}, {hi}] — IMPOSSIBLE"
        )
    elif sd > uniform_sd * 1.5:
        flags.append(
            f"SD ({sd}) exceeds 1.5x uniform SD ({uniform_sd:.2f}) "
            f"— data must be heavily bimodal or contain outliers"
        )

    result = {
        'sd': sd,
        'data_range': data_range,
        'max_possible_sd': round(max_possible_sd, 4),
        'uniform_sd': round(uniform_sd, 4),
        'flags': flags,
    }
    if flags:
        result['detail'] = (
            f"FLAG: {label + ': ' if label else ''}{'; '.join(flags)}"
        )
    else:
        result['detail'] = (
            f"PASS: {label + ': ' if label else ''}"
            f"SD={sd} within plausible range for [{lo}, {hi}]"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 16. Contingency table reconstruction
# ═══════════════════════════════════════════════════════════════════════════════

def check_contingency_table(
    row_totals: List[int],
    col_totals: List[int],
    reported_total: Optional[int] = None,
    label: str = "",
) -> dict:
    """
    Check whether reported row and column marginal totals of a
    contingency table are internally consistent.

    Ref: Heathers (2025) ch. "Reconstructing contingency tables"
    """
    row_sum = sum(row_totals)
    col_sum = sum(col_totals)

    flags = []
    if row_sum != col_sum:
        flags.append(
            f"Row totals sum to {row_sum}, column totals sum to {col_sum} "
            f"— must be equal"
        )

    if reported_total is not None:
        if row_sum != reported_total:
            flags.append(
                f"Row totals sum to {row_sum}, reported N = {reported_total}"
            )
        if col_sum != reported_total:
            flags.append(
                f"Column totals sum to {col_sum}, reported N = {reported_total}"
            )

    result = {
        'consistent': len(flags) == 0,
        'row_sum': row_sum,
        'col_sum': col_sum,
        'reported_total': reported_total,
        'flags': flags,
    }
    if flags:
        result['detail'] = (
            f"FAIL: {label + ': ' if label else ''}{'; '.join(flags)}"
        )
    else:
        result['detail'] = (
            f"PASS: {label + ': ' if label else ''}"
            f"marginals consistent (N={row_sum})"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 17. Carlisle-Stouffer-Fisher test (Table 1 baseline p-values)
# ═══════════════════════════════════════════════════════════════════════════════

def carlisle_stouffer_fisher(p_values: List[float], label: str = "") -> dict:
    """
    Test whether a set of baseline comparison p-values (typically from
    Table 1 of an RCT) are suspiciously well-balanced.

    In a properly randomized trial, baseline p-values should be
    uniformly distributed on [0, 1]. If they cluster too high
    (everything is perfectly balanced), the randomization may be
    fabricated.

    Uses the Stouffer method: Z = sum(Phi_inv(1 - p_i)) / sqrt(k),
    then tests whether combined Z is significantly extreme.

    Ref: Carlisle (2017) doi:10.1111/anae.13938
    Ref: Heathers (2025) ch. "Analyzing multiple Table 1 p-values"

    Args:
        p_values: list of p-values from baseline comparisons
        label: optional label
    """
    k = len(p_values)
    if k < 3:
        return {
            'sufficient_data': False,
            'detail': f"SKIP: need >= 3 p-values for Carlisle test (got {k})"
        }

    # Stouffer's method: convert p-values to z-scores and combine
    z_scores = [float(sp.norm.ppf(1 - p)) for p in p_values]
    combined_z = sum(z_scores) / math.sqrt(k)

    # Two-tailed: suspicious if combined Z is very high (too balanced)
    # or very low (too unbalanced — less common but worth flagging)
    p_combined = float(sp.norm.sf(abs(combined_z)) * 2)

    # Also check: are p-values suspiciously uniform?
    # Kolmogorov-Smirnov test against U(0,1)
    ks_stat, ks_p = sp.kstest(p_values, 'uniform')

    # Are p-values too high? (suspiciously good balance)
    mean_p = sum(p_values) / k
    median_p = sorted(p_values)[k // 2]

    flags = []
    if p_combined < 0.05 and combined_z > 0:
        flags.append(
            f"Stouffer combined Z = {combined_z:.3f} (p = {p_combined:.4f}) — "
            f"baseline variables are suspiciously well-balanced"
        )
    if p_combined < 0.05 and combined_z < 0:
        flags.append(
            f"Stouffer combined Z = {combined_z:.3f} (p = {p_combined:.4f}) — "
            f"baseline variables are suspiciously unbalanced"
        )
    if ks_p < 0.05:
        flags.append(
            f"KS test: p-values are not uniformly distributed "
            f"(D = {ks_stat:.3f}, p = {ks_p:.4f})"
        )

    result = {
        'suspicious': len(flags) > 0,
        'combined_z': round(combined_z, 4),
        'p_combined_stouffer': round(p_combined, 6),
        'ks_statistic': round(float(ks_stat), 4),
        'ks_p_value': round(float(ks_p), 6),
        'mean_p': round(mean_p, 4),
        'median_p': round(median_p, 4),
        'n_pvalues': k,
        'flags': flags,
    }
    if flags:
        result['detail'] = (
            f"FLAG: {label + ': ' if label else ''}{'; '.join(flags)}"
        )
    else:
        result['detail'] = (
            f"PASS: {label + ': ' if label else ''}"
            f"Table 1 p-values appear consistent with randomization "
            f"(Stouffer Z = {combined_z:.3f}, p = {p_combined:.4f}; "
            f"mean p = {mean_p:.3f})"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Demo: full audit of Rajizadeh et al. (2017)
# ═══════════════════════════════════════════════════════════════════════════════

def demo_magnesium_paper():
    """
    Full forensic audit of Rajizadeh et al., Nutrition 35 (2017) 56-60.
    Magnesium supplementation and depression.
    """
    print("=" * 72)
    print("FORENSIC AUDIT: Rajizadeh et al., Nutrition 35 (2017) 56-60")
    print("Magnesium supplementation and depression")
    print("=" * 72)

    findings = {'FAIL': 0, 'FLAG': 0, 'PASS': 0}

    def tally(result):
        d = result.get('detail', '')
        if d.startswith('FAIL'):
            findings['FAIL'] += 1
        elif d.startswith('FLAG'):
            findings['FLAG'] += 1
        else:
            findings['PASS'] += 1

    # ── 1. GRIM on BDI scores ──
    print("\n--- 1. GRIM TEST: Beck Depression Inventory means ---")
    print("(BDI is integer-valued: 21 items scored 0-3, total 0-63)\n")

    bdi_tests = [
        (26.9,  26, "Mg baseline"),
        (11.26, 26, "Mg end"),
        (25.6,  27, "Placebo baseline"),
        (15.2,  27, "Placebo end"),
    ]
    for mean, n, label in bdi_tests:
        dp = len(str(mean).split('.')[-1]) if '.' in str(mean) else 0
        r = grim(mean, n, scale=1, dp=dp)
        tally(r)
        status = "PASS" if r['possible'] else "FAIL"
        print(f"  [{status}] {label}: mean={mean}, n={n}")
        if not r['possible']:
            print(f"         n*mean = {mean*n:.2f}, nearest: {r['nearest_achievable']}")

    # ── 2. DEBIT on percentages ──
    print("\n--- 2. DEBIT TEST: Reported percentages ---")
    print("(counts must be integers)\n")

    debit_tests = [
        (88.5, 26, "Mg group Mg normalization"),
        (48.1, 27, "Placebo group Mg normalization"),
        (73.1, 26, "Mg group female"),
        (74.1, 27, "Placebo group female"),
    ]
    for pct, n, label in debit_tests:
        r = debit(pct, n, dp=1)
        tally(r)
        status = "PASS" if r['possible'] else "FAIL"
        print(f"  [{status}] {label}: {pct}% of n={n} = {r['implied_count']:.2f}")
        if not r['possible']:
            print(f"         nearest: {r['nearest_achievable_pcts']}")

    # ── 3. SPRITE on BDI ──
    print("\n--- 3. SPRITE: Can any valid dataset produce these BDI stats? ---")
    print("(BDI range: 0-63, integer scores)\n")

    sprite_tests = [
        (26.9, 7.1, 26, "Mg baseline"),
        (11.26, 6.9, 26, "Mg end"),
        (25.6, 6.1, 27, "Placebo baseline"),
        (15.2, 9.3, 27, "Placebo end"),
    ]
    for mean, sd, n, label in sprite_tests:
        r = sprite(mean, sd, n, lo=0, hi=63, max_iter=50_000, n_solutions=3)
        tally(r)
        status = "PASS" if r['possible'] else "FLAG"
        print(f"  [{status}] {label}: mean={mean}, SD={sd}, n={n}")
        if r['possible'] and 'reconstructed_mean' in r:
            print(f"         reconstructed: mean={r['reconstructed_mean']}, "
                  f"SD={r['reconstructed_sd']}")
        elif not r['possible']:
            print(f"         no valid dataset found")

    # ── 4. Correlation bound ──
    print("\n--- 4. CORRELATION BOUND: Serum magnesium change SDs ---\n")

    print("  Placebo: Pre SD=0.13, Post SD=0.27, Change SD=0.03")
    r = correlation_bound(0.13, 0.27, 0.03)
    tally(r)
    print(f"  {r['detail']}")

    print("\n  Mg group: Pre SD=0.19, Post SD=0.19, Change SD=0.29")
    r2 = correlation_bound(0.19, 0.19, 0.29)
    tally(r2)
    print(f"  {r2['detail']}")

    # ── 5. P-value recalculation ──
    print("\n--- 5. P-VALUE RECALCULATION ---\n")

    ptests = [
        (0.09, 0.03, 27, 0.110, "Placebo serum Mg change (paired)"),
        (0.31, 0.29, 26, 0.001, "Mg group serum Mg change (paired)"),
        (-15.65, 8.92, 26, 0.001, "Mg group BDI change (paired)"),
        (-10.40, 7.90, 27, 0.001, "Placebo BDI change (paired)"),
    ]
    for mc, sdc, n, rp, label in ptests:
        r = check_ttest_paired(mc, sdc, n, rp)
        tally(r)
        print(f"  {r['detail']}")
        print(f"         ({label})")

    # ── 6. Between-group p-value checks ──
    print("\n  Between-group t-tests:")
    btwn_tests = [
        (26.9, 7.1, 26, 25.6, 6.1, 27, 0.49, "BDI baseline"),
        (11.26, 6.9, 26, 15.2, 9.3, 27, 0.08, "BDI end"),
        (-15.65, 8.92, 26, -10.40, 7.90, 27, 0.02, "BDI change"),
        (1.77, 0.19, 26, 1.82, 0.13, 27, 0.27, "Serum Mg baseline"),
    ]
    for m1, s1, n1, m2, s2, n2, rp, label in btwn_tests:
        r = check_ttest_independent(m1, s1, n1, m2, s2, n2, rp)
        tally(r)
        print(f"  {r['detail']}")
        print(f"         ({label})")

    # ── 7. Arithmetic consistency (Table 2) ──
    print("\n--- 6. ARITHMETIC CONSISTENCY: Table 2 ---\n")

    table2 = [
        (63.33, 71.51, 44.31, "Protein, Mg"),
        (75.08, 69.67, 23.45, "Protein, Placebo"),
        (305.1, 307.49, 87.21, "Carbohydrate, Mg"),
        (364.08, 308.19, 113.34, "Carbohydrate, Placebo"),
        (81.88, 75.53, -6.35, "Fat, Mg"),
        (87.17, 81.60, 32.15, "Fat, Placebo"),
        (153.47, 170.83, 81.50, "Dietary Mg, Mg"),
        (162.96, 193.10, 90.29, "Dietary Mg, Placebo"),
    ]
    for b, e, c, label in table2:
        r = check_change_arithmetic(b, e, c, label)
        tally(r)
        print(f"  {r['detail']}")

    # ── 8. SD sign check ──
    print("\n--- 7. SD SIGN CHECK ---\n")

    sd_checks = [
        (-5.40, "Protein change SD, Placebo"),
        (-55.89, "Carbohydrate change SD, Placebo"),
        (-5.56, "Fat change SD, Placebo"),
    ]
    for sd, label in sd_checks:
        r = check_sd_positive(sd, label)
        tally(r)
        print(f"  {r['detail']}")

    # ── 9. Variance ratio ──
    print("\n--- 8. VARIANCE RATIO: Are group SDs suspiciously similar? ---\n")

    vr_tests = [
        ([7.1, 6.1], [26, 27], ["Mg", "Placebo"], "BDI baseline"),
        ([6.9, 9.3], [26, 27], ["Mg", "Placebo"], "BDI end"),
        ([0.19, 0.13], [26, 27], ["Mg", "Placebo"], "Serum Mg baseline"),
    ]
    for sds, ns, labels, name in vr_tests:
        r = variance_ratio_test(sds, ns, labels)
        tally(r)
        print(f"  {r['detail']}  ({name})")

    # ── 10. Effect size consistency on BDI change ──
    print("\n--- 9. EFFECT SIZE CONSISTENCY: BDI change ---\n")

    r = effect_size_consistency(
        mean1=-15.65, sd1=8.92, n1=26,
        mean2=-10.40, sd2=7.90, n2=27,
        reported_p=0.02,
    )
    tally(r)
    print(f"  {r['detail']}")
    print(f"  Calculated: d={r['calculated_d']:.3f}, "
          f"p={r['calculated_p']:.4f}, "
          f"95% CI {r['calculated_ci']}")

    # ── Summary ──
    print(f"\n{'=' * 72}")
    print(f"AUDIT COMPLETE")
    print(f"  FAILURES (impossible):  {findings['FAIL']}")
    print(f"  FLAGS (suspicious):     {findings['FLAG']}")
    print(f"  PASSES:                 {findings['PASS']}")
    total_issues = findings['FAIL'] + findings['FLAG']
    if total_issues > 5:
        print(f"\n  VERDICT: SEVERE data integrity concerns ({total_issues} issues).")
        print(f"  Raw data investigation warranted.")
    elif total_issues > 2:
        print(f"\n  VERDICT: MODERATE concerns ({total_issues} issues).")
        print(f"  Authors should clarify or provide raw data.")
    elif total_issues > 0:
        print(f"\n  VERDICT: MINOR concerns ({total_issues} issues).")
        print(f"  Likely rounding or transcription errors.")
    else:
        print(f"\n  VERDICT: No data integrity issues detected.")
    print(f"{'=' * 72}")


if __name__ == '__main__':
    demo_magnesium_paper()
