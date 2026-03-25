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
        grim, debit, sprite, correlation_bound, check_ttest_paired,
        check_ttest_independent, sample_size_from_t, effect_size_consistency,
        benfords_law, variance_ratio_test, check_change_arithmetic,
        check_sd_positive,
    )

References:
    Brown & Heathers (2017) "The GRIM Test" doi:10.1177/1948550616673876
    Heathers & Brown (2019) "GRIMMER" doi:10.31234/osf.io/6cn2h
    Jane (2024) matthewbjane.github.io/blog-posts/blog-post-1.html
    Anaya (2016) "The SPRITE Procedure" doi:10.7287/peerj.preprints.2748v1
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
    max_iter: int = 100_000,
    n_solutions: int = 5,
    seed: int = 42,
) -> dict:
    """
    SPRITE: attempt to reconstruct a valid dataset that produces the
    reported mean and SD for bounded integer data.

    If no valid dataset exists, the reported statistics are impossible.

    Args:
        mean: reported mean
        sd:   reported standard deviation
        n:    sample size
        lo:   minimum possible value (e.g. 0 for BDI)
        hi:   maximum possible value (e.g. 63 for BDI)
        max_iter:    maximum random perturbation attempts per solution
        n_solutions: number of valid datasets to find before stopping
        seed: random seed for reproducibility

    Returns:
        dict with 'possible', 'solutions_found', 'example_dataset', 'detail'.
    """
    rng = random.Random(seed)
    target_sum = round(mean * n)
    target_var = sd ** 2

    # Quick feasibility: can the sum even be achieved?
    if target_sum < lo * n or target_sum > hi * n:
        return {
            'possible': False,
            'solutions_found': 0,
            'detail': (
                f"FAIL: target sum {target_sum} is outside [{lo*n}, {hi*n}] "
                f"for n={n} with range [{lo}, {hi}]"
            ),
        }

    solutions = []

    for attempt in range(n_solutions * 3):
        if len(solutions) >= n_solutions:
            break

        # Initialize: spread values to hit the target sum
        data = [lo] * n
        remaining = target_sum - lo * n
        for i in range(n):
            add = min(remaining, hi - lo)
            data[i] = lo + add
            remaining -= add
            if remaining <= 0:
                break

        rng.shuffle(data)

        # Iteratively perturb to match SD
        best_var_diff = float('inf')
        for _ in range(max_iter):
            current_mean = sum(data) / n
            current_var = sum((x - current_mean) ** 2 for x in data) / (n - 1)
            var_diff = abs(current_var - target_var)

            if var_diff < 0.005:  # close enough (rounding tolerance)
                solutions.append(list(data))
                break

            if var_diff < best_var_diff:
                best_var_diff = var_diff

            # Pick two random indices and perturb
            i, j = rng.sample(range(n), 2)

            if current_var < target_var:
                # Need more spread: move values apart
                if data[i] < hi and data[j] > lo:
                    data[i] += 1
                    data[j] -= 1
            else:
                # Need less spread: move values closer to mean
                if data[i] > current_mean and data[i] > lo:
                    idx_far = i
                elif data[j] > current_mean and data[j] > lo:
                    idx_far = j
                elif data[i] < current_mean and data[i] < hi:
                    idx_far = i
                else:
                    idx_far = j

                if data[idx_far] > current_mean and data[idx_far] > lo:
                    data[idx_far] -= 1
                    # Find someone below mean to increment
                    below = [k for k in range(n) if data[k] < current_mean and data[k] < hi]
                    if below:
                        data[rng.choice(below)] += 1
                elif data[idx_far] < current_mean and data[idx_far] < hi:
                    data[idx_far] += 1
                    above = [k for k in range(n) if data[k] > current_mean and data[k] > lo]
                    if above:
                        data[rng.choice(above)] -= 1

    possible = len(solutions) > 0
    result = {
        'possible': possible,
        'solutions_found': len(solutions),
        'target_mean': mean,
        'target_sd': sd,
        'n': n,
        'range': [lo, hi],
    }

    if solutions:
        example = sorted(solutions[0])
        actual_mean = sum(example) / n
        actual_sd = (sum((x - actual_mean) ** 2 for x in example) / (n - 1)) ** 0.5
        result['example_dataset'] = example
        result['reconstructed_mean'] = round(actual_mean, 4)
        result['reconstructed_sd'] = round(actual_sd, 4)
        result['detail'] = (
            f"PASS: found {len(solutions)} valid dataset(s). "
            f"Example reconstructs mean={actual_mean:.2f}, SD={actual_sd:.2f}"
        )
    else:
        result['detail'] = (
            f"FLAG: could not reconstruct any dataset with mean={mean}, SD={sd}, "
            f"n={n}, range=[{lo},{hi}] in {max_iter} iterations. "
            f"Statistics may be impossible or extremely constrained."
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
    ci_lower = diff - t_crit * se
    ci_upper = diff + t_crit * se

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
