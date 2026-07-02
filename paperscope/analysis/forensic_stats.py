#!/usr/bin/env python3
"""
Forensic statistics checker for peer review.

Implements the data-integrity tests used by statistical sleuths
(Meyerowitz-Katz, Brown/Heathers GRIM, etc.) to detect impossible
or implausible summary statistics in published papers.

Usage:
    Import the check functions and feed in extracted table data:

    from paperscope.analysis.forensic_stats import (
        grim, grim_column, grim_row,
        grimmer, grim_percentage, sprite, correlation_bound,
        check_ttest_paired, check_ttest_independent,
        check_anova_oneway, check_chi_squared,
        sample_size_from_t, effect_size_consistency,
        carlisle_stouffer_fisher, check_sd_se_confusion,
        quick_sd_check, check_contingency_table,
        benfords_law, variance_ratio_test,
        check_change_arithmetic, check_sd_positive,
        check_frozen_sds, infer_column_dp,
    )

Verdict semantics (cardinal rule of a forensic tool): NEVER brand possible
data impossible.  When a check cannot be computed (degenerate or invalid
input), the verdict is "undetermined / cannot test" — never FAIL.

References:
    Heathers (2025) "An Introduction to Forensic Metascience" doi:10.5281/zenodo.14871843
    Brown & Heathers (2017) "The GRIM Test" doi:10.1177/1948550616673876
    Anaya (2016) "The GRIMMER Test" doi:10.7287/peerj.preprints.2400v1
    Jane (2024) matthewbjane.github.io/blog-posts/blog-post-1.html
    Heathers, Anaya, van der Zee & Brown (2018) "SPRITE" doi:10.7287/peerj.preprints.26968v1
    Carlisle (2017) doi:10.1111/anae.13938
"""

from __future__ import annotations

import math
import random
import warnings
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from scipy import stats as sp


# ═══════════════════════════════════════════════════════════════════════════════
# 0. HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _dp_from_str(s: str) -> int:
    """Extract decimal places from a string representation of a number."""
    s = s.strip()
    if '.' in s:
        return len(s.split('.')[-1])
    return 0


def infer_column_dp(values: List[Union[str, float]]) -> int:
    """
    Infer the decimal-place precision for a column of reported values.

    Papers often drop trailing zeros (e.g., "26.9" when other values in the
    same column are reported to 2 dp like "11.26").  The correct dp for GRIM
    is the *maximum* across the column, because the trailing zero was merely
    suppressed in display.

    Accepts strings (preferred — preserves trailing zeros like "26.90") or
    floats (trailing zeros lost by Python's float representation).

    Ref: Gideon Meyerowitz-Katz.
    """
    max_dp = 0
    for v in values:
        s = v if isinstance(v, str) else f"{v}"
        max_dp = max(max_dp, _dp_from_str(s))
    return max_dp


# ═══════════════════════════════════════════════════════════════════════════════
# 1. GRIM (Granularity-Related Inconsistency of Means)
# ═══════════════════════════════════════════════════════════════════════════════

def grim(mean: Union[str, float], n: int, scale: int = 1,
         dp: Optional[int] = None) -> dict:
    """
    GRIM test: is this mean possible for n integer-valued observations?

    Args:
        mean:  reported mean.  Pass as a *string* (e.g., "26.90") to
               preserve trailing zeros and get correct dp inference.
               Float input works but may lose trailing-zero precision.
        n:     sample size
        scale: granularity of the instrument (1 for integers, 0.5 for
               half-points, etc.)
        dp:    decimal places reported.  If None, inferred from `mean`:
               - string "26.90" → dp=2
               - float 26.9 → dp=1 (trailing zero lost!)
               Prefer passing strings or explicit dp for safety.

    Returns:
        dict with 'possible' (bool), 'implied_sum', 'nearest_achievable',
        and 'detail' (str).
    """
    if isinstance(mean, str):
        if dp is None:
            dp = _dp_from_str(mean)
        mean = float(mean)
    elif dp is None:
        dp = _dp_from_str(f"{mean}")
    if n <= 0:
        return {
            'possible': None,
            'reported_mean': mean,
            'n': n,
            'detail': f"UNDETERMINED: invalid sample size n={n} — cannot test",
        }
    implied_sum = mean * n
    granularity = scale

    # Rounding tolerance: the true mean can sit up to half a unit of the
    # last reported decimal place away.  The boundary is *inclusive*: a
    # true mean exactly 0.5 ulp away still rounds to the reported value
    # under half-up or banker's rounding, so allow a small epsilon for
    # float noise rather than a strict inequality.
    half_ulp = 0.5 * (10 ** -dp)
    eps = 1e-9

    lower = math.floor(implied_sum / granularity) * granularity / n
    upper = math.ceil(implied_sum / granularity) * granularity / n
    near_integer = (abs(lower - mean) <= half_ulp + eps or
                    abs(upper - mean) <= half_ulp + eps)

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


def grim_column(means: List[Union[str, float]], ns: List[int],
                labels: Optional[List[str]] = None,
                scale: int = 1) -> List[dict]:
    """
    Run GRIM on a column of means with automatic column-level dp inference.

    The dp is inferred from the *maximum* across all means in the column,
    because papers often drop trailing zeros (e.g., "26.9" when the column
    also contains "11.26", implying the real value is "26.90").

    Args:
        means:  list of reported means (strings preferred for dp safety)
        ns:     list of sample sizes (one per mean, or a single int for all)
        labels: optional labels for each mean
        scale:  instrument granularity (1 for integers)

    Returns:
        list of grim() result dicts, each with an added 'label' key.
    """
    dp = infer_column_dp(means)

    if isinstance(ns, int):
        ns = [ns] * len(means)
    if labels is None:
        labels = [None] * len(means)

    results = []
    for mean, n, label in zip(means, ns, labels):
        r = grim(mean, n, scale=scale, dp=dp)
        r['column_dp'] = dp
        if label:
            r['label'] = label
        results.append(r)
    return results


def grim_row(baseline: Union[str, float], end: Union[str, float],
             change: Union[str, float], n: int,
             scale: int = 1, label: str = "") -> dict:
    """
    Cross-cell GRIM: check baseline, end, and change with precision
    constraints enforced across the row.

    When a table reports baseline, end, and change in the same row,
    the precision of each value constrains the others.  For example,
    if end=11.26 (2dp) and change=15.65 (2dp), then baseline must
    also be at 2dp precision, even if printed as "26.9".

    Also checks arithmetic consistency: baseline - end ≈ change
    (or baseline + change ≈ end, depending on sign convention).

    Ref: Gideon Meyerowitz-Katz.

    Returns:
        dict with 'baseline_grim', 'end_grim', 'change_grim',
        'row_dp', 'arithmetic_ok', and 'detail'.
    """
    strs = [baseline if isinstance(baseline, str) else f"{baseline}",
            end if isinstance(end, str) else f"{end}",
            change if isinstance(change, str) else f"{change}"]
    row_dp = max(_dp_from_str(s) for s in strs)

    b_val = float(baseline) if isinstance(baseline, str) else baseline
    e_val = float(end) if isinstance(end, str) else end
    c_val = float(change) if isinstance(change, str) else change

    r_base = grim(b_val, n, scale=scale, dp=row_dp)
    r_end = grim(e_val, n, scale=scale, dp=row_dp)
    r_change = grim(c_val, n, scale=scale, dp=row_dp)

    # Arithmetic: check if end - baseline ≈ change OR baseline - end ≈ change
    # (sign conventions vary across papers)
    diff = e_val - b_val
    tolerance = 1.5 * (10 ** -row_dp)  # generous for rounding
    arith_ok = (abs(diff - c_val) <= tolerance or
                abs(-diff - c_val) <= tolerance)

    flags = []
    if not r_base['possible']:
        flags.append(f"baseline {b_val} fails GRIM at {row_dp}dp")
    if not r_end['possible']:
        flags.append(f"end {e_val} fails GRIM at {row_dp}dp")
    if not r_change['possible']:
        flags.append(f"change {c_val} fails GRIM at {row_dp}dp")
    if not arith_ok:
        flags.append(
            f"arithmetic: end-baseline={diff:.{row_dp}f}, "
            f"reported change={c_val}"
        )

    prefix = f"{label}: " if label else ""
    if flags:
        detail = f"FLAG: {prefix}{'; '.join(flags)}"
    else:
        detail = f"PASS: {prefix}all row values consistent at {row_dp}dp"

    return {
        'baseline_grim': r_base,
        'end_grim': r_end,
        'change_grim': r_change,
        'row_dp': row_dp,
        'arithmetic_ok': arith_ok,
        'flags': flags,
        'detail': detail,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GRIM FOR PERCENTAGES (formerly misnamed "DEBIT")
# ═══════════════════════════════════════════════════════════════════════════════

def grim_percentage(percentage: float, n: int, dp: int = 1) -> dict:
    """
    GRIM applied to percentages/proportions derived from discrete counts.

    If a paper says "88.5% of 26 participants responded", that implies
    26 * 0.885 = 23.01 people — impossible. The count must be an integer.

    Note: this is *not* the DEBIT test.  The real DEBIT (DEscriptive
    BInary Test; Heathers & Brown 2019, osf.io/pm825) is a mean/SD/n
    consistency check for binary data and is not implemented here.

    Ref: Brown & Heathers (2017) "The GRIM Test" doi:10.1177/1948550616673876

    Args:
        percentage: reported percentage (e.g. 88.5 for 88.5%)
        n:          sample size (denominator)
        dp:         decimal places in the reported percentage

    Returns:
        dict with 'possible', 'implied_count', 'nearest_achievable', 'detail'.
    """
    if n <= 0:
        return {
            'possible': None,
            'reported_percentage': percentage,
            'n': n,
            'detail': f"UNDETERMINED: invalid sample size n={n} — cannot test",
        }
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


def debit(percentage: float, n: int, dp: int = 1) -> dict:
    """
    Deprecated alias for grim_percentage().

    This function was misnamed: the real DEBIT (Heathers & Brown 2019,
    osf.io/pm825) is a different test (mean/SD/n consistency for binary
    data), while this check is GRIM applied to percentages.
    """
    warnings.warn(
        "debit() is deprecated and was misnamed — it is GRIM for "
        "percentages, not the DEBIT test. Use grim_percentage() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return grim_percentage(percentage, n, dp=dp)


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
    dp_sd: Optional[int] = None,
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

    Verdicts: an analytic-precondition impossibility is a FAIL
    ('possible': False); a search that exhausts its budget without
    finding a dataset is only a FLAG ('possible': None) — the statistics
    are not proven impossible.

    Ref: Heathers, Anaya, van der Zee & Brown (2018)
         doi:10.7287/peerj.preprints.26968v1

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
        dp_sd: decimal places of the reported SD (auto-detected if None);
               sets the SD rounding tolerance to ±0.5 ulp

    Returns:
        dict with 'possible', 'grim_possible', 'n_target_sums',
        'n_sumsq_targets', 'example_dataset', 'closest', and 'detail'.
    """
    if n <= 0:
        return {
            'possible': None,
            'n': n,
            'detail': f"UNDETERMINED: invalid sample size n={n} — cannot test",
        }
    if n == 1:
        return {
            'possible': None,
            'n': n,
            'detail': "UNDETERMINED: SD is undefined for n=1 — cannot test",
        }
    if sd < 0:
        return {
            'possible': False,
            'n': n,
            'detail': f"FAIL: SD ({sd}) is negative — impossible",
        }

    # Auto-detect decimal places (mean and SD independently)
    if dp is None:
        s = str(mean)
        dp = len(s.split('.')[-1]) if '.' in s else 0
    if dp_sd is None:
        s = str(sd)
        dp_sd = len(s.split('.')[-1]) if '.' in s else 0

    # ── Phase 1: analytical feasibility ──
    # Inclusive rounding boundaries (see grim()): a value exactly 0.5 ulp
    # away still rounds to the reported one, so pad with a small epsilon.
    eps = 1e-9
    half_unit = 0.5 * 10**(-dp)
    lo_mean = mean - half_unit
    hi_mean = mean + half_unit
    lo_sum = max(math.ceil(lo_mean * n - eps), lo * n)
    hi_sum = min(math.floor(hi_mean * n + eps), hi * n)
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

    # For each possible sum, find valid sum-of-squares range.
    # SD rounding tolerance is ±0.5 ulp at the reported precision, with
    # the lower bound clamped at 0 (an SD interval can never go negative;
    # squaring a negative lower bound would fabricate a positive minimum).
    half_sd = 0.5 * 10**(-dp_sd)
    sd_lo = max(0.0, sd - half_sd)
    sd_hi = sd + half_sd
    target_var = sd ** 2

    feasible_targets = []  # list of (target_sum, lo_sumsq, hi_sumsq)
    total_sumsq_targets = 0
    for ts in possible_sums:
        lo_sumsq = sd_lo**2 * (n - 1) + ts**2 / n
        hi_sumsq = sd_hi**2 * (n - 1) + ts**2 / n
        lo_int = math.ceil(lo_sumsq - eps)
        hi_int = math.floor(hi_sumsq + eps)
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

                # Accept when the sum is on target AND the reconstructed SD
                # rounds to the reported SD at its reported precision (the
                # sum check guards the mean — an SD match alone can come
                # from a dataset with the wrong mean)
                if (sum(data) == target_sum
                        and sd_lo - eps <= cur_var ** 0.5 <= sd_hi + eps):
                    found_dataset = list(data)
                    break

                # Perturb: swap toward/away from target variance.  Every
                # move must be a legal +1/-1 pair so the sum is invariant —
                # a one-sided move would drift the mean off target.
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
                    if data[far] > mid and data[far] > lo and data[near] < hi:
                        data[far] -= 1
                        data[near] += 1
                    elif data[far] < mid and data[far] < hi and data[near] > lo:
                        data[far] += 1
                        data[near] -= 1

        if found_dataset is not None:
            break

    # ── Build result ──
    # found → PASS; analytic impossibility → FAIL; budget exhausted with
    # feasible targets remaining → FLAG (None), not FAIL
    if found_dataset is not None:
        verdict = True
    elif not feasible_targets:
        verdict = False
    else:
        verdict = None
    result = {
        'possible': verdict,
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
                f"but no dataset found within budget "
                f"({result['total_iterations']:,} iterations: "
                f"{n_seeds} seeds x {len(feasible_targets)} targets x {max_iter:,}). "
                f"Closest SD: {best_stats[1]:.4f} (target {sd}, gap {best_var_diff:.6f}). "
                f"Not proven impossible — statistics may be achievable but "
                f"are highly constrained."
            )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Correlation bound from pre/post/change SDs
# ═══════════════════════════════════════════════════════════════════════════════

def correlation_bound(sd_pre: Union[str, float], sd_post: Union[str, float],
                      sd_change: Union[str, float],
                      dp: Optional[int] = None) -> dict:
    """
    Reverse-engineer the implied Pearson r between pre and post scores
    from their SDs and the SD of the change score.

    Var(change) = Var(pre) + Var(post) - 2*r*SD(pre)*SD(post)
    => r = (SD_pre^2 + SD_post^2 - SD_change^2) / (2 * SD_pre * SD_post)

    Reported SDs are rounded, so each is treated as a ±0.5-ulp interval
    at its reported precision.  FAIL only if |r| > 1 across the *entire*
    interval — i.e., no (pre, post, change) triple in the rounding box
    satisfies |pre - post| <= change <= pre + post.

    Args:
        sd_pre, sd_post, sd_change: reported SDs (strings preserve
            trailing zeros for dp inference)
        dp: decimal places of all three SDs.  If None, inferred from
            each value independently (see grim()).
    """
    def _half_ulp(v):
        d = dp if dp is not None else _dp_from_str(v if isinstance(v, str) else f"{v}")
        return 0.5 * (10 ** -d)

    h_pre, h_post, h_chg = (_half_ulp(sd_pre), _half_ulp(sd_post),
                            _half_ulp(sd_change))
    sd_pre = float(sd_pre)
    sd_post = float(sd_post)
    sd_change = float(sd_change)

    if sd_pre < 0 or sd_post < 0 or sd_change < 0:
        return {
            'possible': False,
            'implied_r': None,
            'detail': "FAIL: a negative SD is impossible",
        }

    numerator = sd_pre**2 + sd_post**2 - sd_change**2
    denominator = 2 * sd_pre * sd_post

    if denominator == 0:
        # Constant pre or post data is valid; r is undefined, not impossible
        return {
            'possible': None,
            'implied_r': None,
            'detail': (
                "UNDETERMINED: pre or post SD is 0 — the correlation is "
                "undefined for constant data; cannot test (not evidence "
                "of error)"
            ),
        }

    implied_r = numerator / denominator
    min_sd_change = abs(sd_pre - sd_post)
    max_sd_change = sd_pre + sd_post

    # Rounding intervals (SDs cannot go below 0)
    eps = 1e-9
    pre_lo, pre_hi = max(0.0, sd_pre - h_pre), sd_pre + h_pre
    post_lo, post_hi = max(0.0, sd_post - h_post), sd_post + h_post
    chg_lo, chg_hi = max(0.0, sd_change - h_chg), sd_change + h_chg

    # |r| <= 1 somewhere in the box iff some change in [chg_lo, chg_hi]
    # can reach [|pre - post|, pre + post] for some pre/post in range
    min_gap = max(pre_lo - post_hi, post_lo - pre_hi, 0.0)
    possible = (chg_hi >= min_gap - eps and
                chg_lo <= pre_hi + post_hi + eps)

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
            f"PASS: implied r = {implied_r:.4f} is achievable within SD "
            f"rounding. Plausible SD(change) range: "
            f"[{min_sd_change:.4f}, {max_sd_change:.4f}]"
        )
    else:
        result['detail'] = (
            f"FAIL: implied r = {implied_r:.4f} — IMPOSSIBLE (|r| > 1 across "
            f"the entire SD rounding interval). Reported SD(change) = "
            f"{sd_change}, but valid range is "
            f"[{min_sd_change:.4f}, {max_sd_change:.4f}]"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 5. P-value recalculation
# ═══════════════════════════════════════════════════════════════════════════════

def check_ttest_paired(mean_change: float, sd_change: float, n: int,
                       reported_p: float) -> dict:
    """Recalculate a paired t-test p-value from reported change statistics."""
    if sd_change < 0:
        return {
            'plausible': False,
            'detail': f"FAIL: SD of change ({sd_change}) is negative, impossible"
        }
    if n <= 1:
        return {
            'plausible': None,
            'detail': f"UNDETERMINED: invalid sample size n={n} — cannot test"
        }
    if sd_change == 0:
        # Zero change-SD is possible data (all subjects changed identically)
        return {
            'plausible': None,
            'detail': (
                "UNDETERMINED: degenerate: cannot recompute the test "
                "statistic (zero variance); not evidence of error"
            )
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
    if sd1 < 0 or sd2 < 0:
        return {'plausible': False,
                'detail': "FAIL: a negative SD is impossible"}
    if n1 <= 1 or n2 <= 1:
        return {'plausible': None,
                'detail': (f"UNDETERMINED: invalid sample sizes "
                           f"(n1={n1}, n2={n2}) — cannot test")}
    se = math.sqrt(sd1**2 / n1 + sd2**2 / n2)
    if se == 0:
        # Both SDs zero is possible data (constant groups)
        return {
            'plausible': None,
            'detail': (
                "UNDETERMINED: degenerate: cannot recompute the test "
                "statistic (zero variance); not evidence of error"
            )
        }

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

def sample_size_from_t(t_val: float, p_reported: Union[str, float],
                       reported_n: int, two_tailed: bool = True,
                       dp: Optional[int] = None) -> dict:
    """
    From a reported t-statistic and p-value, check whether they are
    consistent with the stated n.

    A reported p-value is rounded, so it cannot be inverted as exact:
    PASS if the exact p at the stated n's df rounds to the reported p
    at its reported precision; FLAG only if the exact p falls outside
    the reported p's entire rounding interval.  The range of n values
    consistent with the reported p is returned as information.

    Args:
        t_val:       reported t-statistic
        p_reported:  reported p-value (string preserves trailing zeros)
        reported_n:  stated sample size (for comparison)
        two_tailed:  whether the test is two-tailed
        dp:          decimal places of the reported p (inferred if None)
    """
    if dp is None:
        dp = _dp_from_str(p_reported if isinstance(p_reported, str)
                          else f"{p_reported}")
    p_reported = float(p_reported)

    if reported_n <= 1:
        return {
            'plausible': None,
            'reported_n': reported_n,
            'detail': (f"UNDETERMINED: invalid sample size n={reported_n} "
                       f"— cannot test"),
        }

    # Rounding interval of the reported p (inclusive boundary, see grim())
    half_ulp = 0.5 * (10 ** -dp)
    eps = 1e-12
    p_lo = p_reported - half_ulp - eps
    p_hi = p_reported + half_ulp + eps
    tails = 2 if two_tailed else 1

    # Exact p at the stated n's df (one-sample/paired: df = n - 1)
    stated_df = reported_n - 1
    p_at_stated = float(sp.t.sf(abs(t_val), stated_df)) * tails
    match = p_lo <= p_at_stated <= p_hi

    # Which df values (1..10000) are consistent with the reported p?
    import numpy as np
    dfs = np.arange(1, 10001)
    p_all = sp.t.sf(abs(t_val), dfs) * tails
    idx = np.nonzero((p_all >= p_lo) & (p_all <= p_hi))[0]
    if idx.size:
        implied_n_range = [int(dfs[idx[0]]) + 1, int(dfs[idx[-1]]) + 1]
    else:
        implied_n_range = None

    return {
        'plausible': match,
        'p_at_stated_n': p_at_stated,
        'implied_n_range': implied_n_range,
        'reported_n': reported_n,
        'detail': (
            f"{'PASS' if match else 'FLAG'}: "
            f"t={t_val} at stated n={reported_n} (df={stated_df}) gives "
            f"p={p_at_stated:.4g}, which "
            f"{'rounds to' if match else 'does not round to'} reported "
            f"p={p_reported}. "
            + (f"n consistent with reported p: "
               f"{implied_n_range[0]}-{implied_n_range[1]}"
               if implied_n_range else
               "no n in 2-10001 reproduces the reported p")
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

_DATASET_EXISTS_BUDGET = 200_000  # memo-entry cap for the exact DP


def _integer_dataset_exists(k: int, s: int, q: int, lo: int, hi: int,
                            memo: dict) -> Optional[bool]:
    """
    Exact test: do k integers in [lo, hi] exist with sum s and sum of
    squares q?  Memoized DFS over (slots, sum, sumsq) with analytic
    pruning; order is irrelevant for existence, so states stay small.
    Returns True/False, or None if the memo budget is exhausted (an
    honest "don't know", never a verdict).
    """
    if k > 500:
        return None  # recursion guard; fall back to undetermined
    if k == 0:
        return s == 0 and q == 0
    if s < k * lo or s > k * hi:
        return False
    if q * k < s * s:
        return False  # Cauchy-Schwarz: sumsq >= s^2 / k
    if q > (lo + hi) * s - k * lo * hi:
        return False  # for x in [lo, hi]: x^2 <= (lo+hi)x - lo*hi
    key = (k, s, q)
    if key in memo:
        return memo[key]
    if len(memo) >= _DATASET_EXISTS_BUDGET:
        return None
    found = False
    for v in range(hi, lo - 1, -1):
        sub = _integer_dataset_exists(k - 1, s - v, q - v * v, lo, hi, memo)
        if sub is None:
            return None  # budget hit below — don't cache, don't conclude
        if sub:
            found = True
            break
    memo[key] = found
    return found


def grimmer(mean: Union[str, float], sd: Union[str, float], n: int,
            scale: int = 1,
            dp_mean: Optional[int] = None,
            dp_sd: Optional[int] = None) -> dict:
    """
    GRIMMER test: is this SD possible for n integer-valued observations
    with the given mean?

    Extends GRIM to standard deviations. For integer data with known n
    and mean, the sum of squares must be an integer, which constrains
    the achievable SDs.  Every integer sum admitted by the GRIM gate is
    tested, and (for integer data) candidate sums of squares must match
    the parity of the sum, since sum(x^2) ≡ sum(x) (mod 2).  Those
    conditions are necessary but not sufficient, so for scale=1 each
    surviving (sum, sum-of-squares) target is verified exactly against
    an integer dataset (bounded DP); a PASS means a dataset exists, a
    FAIL means none does, and an exhausted search budget reports
    UNDETERMINED rather than a verdict.

    Ref: Anaya (2016) doi:10.7287/peerj.preprints.2400v1

    Args:
        mean:    reported mean (string preserves trailing zeros)
        sd:      reported SD (string preserves trailing zeros)
        n:       sample size
        scale:   granularity (1 for integers)
        dp_mean: decimal places of the mean (inferred from string if None)
        dp_sd:   decimal places of the SD (inferred from string if None)
    """
    if isinstance(mean, str):
        if dp_mean is None:
            dp_mean = _dp_from_str(mean)
        mean = float(mean)
    elif dp_mean is None:
        dp_mean = _dp_from_str(f"{mean}")

    if isinstance(sd, str):
        if dp_sd is None:
            dp_sd = _dp_from_str(sd)
        sd = float(sd)
    elif dp_sd is None:
        dp_sd = _dp_from_str(f"{sd}")
    if n <= 0:
        return {
            'possible': None,
            'n': n,
            'detail': f"UNDETERMINED: invalid sample size n={n} — cannot test",
        }
    if sd < 0:
        return {
            'possible': False,
            'grim_pass': None,
            'detail': f"FAIL: SD ({sd}) is negative — impossible",
        }
    # First check GRIM
    grim_result = grim(mean, n, scale=scale, dp=dp_mean)
    if not grim_result['possible']:
        return {
            'possible': False,
            'grim_pass': False,
            'detail': f"FAIL: GRIM fails first — mean {mean} is impossible for n={n}"
        }

    # Every integer sum the GRIM gate admits must be tested — the true
    # sum need not be round(mean * n) (inclusive boundary, see grim())
    eps = 1e-9
    half_mean = 0.5 * 10**(-dp_mean)
    lo_sum = math.ceil((mean - half_mean) * n / scale - eps)
    hi_sum = math.floor((mean + half_mean) * n / scale + eps)
    candidate_sums = [k * scale for k in range(lo_sum, hi_sum + 1)]
    implied_sum = round(mean * n)

    # SD^2 * (n-1) = sum_of_squares - sum^2 / n
    # Sum of squares must be an integer (sum of integer squares).
    # Allow rounding tolerance on the SD, clamping the lower bound at 0
    # (a negative bound would be squared into a spurious positive minimum)
    sd_lo = max(0.0, sd - 0.5 * 10**(-dp_sd))
    sd_hi = sd + 0.5 * 10**(-dp_sd)

    valid_sums = []
    per_sum = []
    sumsq_targets = {}  # ts -> parity-consistent integer sum-of-squares list
    n_valid_sumsq = 0
    for ts in candidate_sums:
        lo_sumsq = sd_lo**2 * (n - 1) + ts**2 / n
        hi_sumsq = sd_hi**2 * (n - 1) + ts**2 / n
        lo_int = math.ceil(lo_sumsq - eps)
        hi_int = math.floor(hi_sumsq + eps)
        n_ints = max(0, hi_int - lo_int + 1)
        if n_ints and scale == 1:
            # Parity: x^2 ≡ x (mod 2) for integers, so sum(x^2) must
            # match the parity of the sum — exact, never a false FAIL
            parity = ts % 2
            first = lo_int if lo_int % 2 == parity else lo_int + 1
            if first > hi_int:
                n_ints = 0
            else:
                n_ints = (hi_int - first) // 2 + 1
                sumsq_targets[ts] = list(range(first, hi_int + 1, 2))
        per_sum.append({
            'sum': ts,
            'sumsq_range': [round(lo_sumsq, 4), round(hi_sumsq, 4)],
            'n_valid_sumsq': n_ints,
        })
        if n_ints:
            valid_sums.append(ts)
            n_valid_sumsq += n_ints

    # Integer sum-of-squares + parity are necessary, NOT sufficient — e.g.
    # sum=15, sumsq=79, n=3 passes both, but no integer triple achieves it.
    # For scale=1, constructively verify each (sum, sumsq) target with an
    # exact bounded DP; the value bound mean ± sd_hi*(n-1)/sqrt(n) is
    # exhaustive (no dataset within SD tolerance can exceed it), so False
    # here is a proof.  Budget-exhausted → None (undetermined), never FAIL.
    representable = None
    if valid_sums and scale == 1:
        representable = False
        checked = 0
        for ts in valid_sums:
            dev = sd_hi * (n - 1) / math.sqrt(n)
            lo_b = math.floor(ts / n - dev)
            hi_b = math.ceil(ts / n + dev)
            memo = {}
            for q in sumsq_targets.get(ts, []):
                checked += 1
                if checked > 200:
                    representable = None
                    break
                exists = _integer_dataset_exists(n, ts, q, lo_b, hi_b, memo)
                if exists is None:
                    representable = None
                elif exists:
                    representable = True
                    break
            if representable is True or checked > 200:
                break
        if checked > 200 and representable is not True:
            representable = None

    if not valid_sums:
        possible = False
    elif scale != 1:
        possible = True  # necessary conditions only (multi-item averages)
    else:
        possible = representable

    result = {
        'possible': possible,
        'grim_pass': True,
        'reported_mean': mean,
        'reported_sd': sd,
        'n': n,
        'implied_sum': implied_sum,
        'candidate_sums': candidate_sums,
        'valid_sums': valid_sums,
        'per_sum': per_sum,
        'n_valid_sumsq': n_valid_sumsq,
        'representable': representable,
    }
    if possible is True:
        if scale == 1:
            result['detail'] = (
                f"PASS: SD={sd} is achievable with mean={mean}, n={n} "
                f"(an integer dataset realises one of the "
                f"{n_valid_sumsq} sum-of-squares target(s))."
            )
        else:
            result['detail'] = (
                f"PASS: SD={sd} is consistent with mean={mean}, n={n} "
                f"(necessary conditions: integer sum of squares + parity; "
                f"not constructively verified for scale={scale})."
            )
    elif possible is None:
        result['detail'] = (
            f"UNDETERMINED: SD={sd} with mean={mean}, n={n} passes the "
            f"necessary conditions but exact verification exceeded the "
            f"search budget — not evidence of error."
        )
    elif not valid_sums:
        result['detail'] = (
            f"FAIL: SD={sd} is impossible with mean={mean}, n={n}. "
            f"No integer sum of squares (with matching parity) exists "
            f"for any GRIM-consistent sum {candidate_sums}."
        )
    else:
        result['detail'] = (
            f"FAIL: SD={sd} is impossible with mean={mean}, n={n}. "
            f"Integer sum-of-squares targets exist for sum(s) {valid_sums}, "
            f"but no integer dataset realises any of them."
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
    if any(sd < 0 for sd in sds):
        return {'consistent': False,
                'detail': "FAIL: a negative SD is impossible"}
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
        # Zero within-group variance is possible data (constant groups)
        return {
            'consistent': None,
            'detail': (
                "UNDETERMINED: degenerate: cannot recompute the test "
                "statistic (zero within-group variance); not evidence "
                "of error"
            )
        }

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

    # Chi-squared (uncorrected Pearson)
    chi2_calc = float(np.sum((obs - expected)**2 / expected))
    df = (obs.shape[0] - 1) * (obs.shape[1] - 1)
    p_calc = float(sp.chi2.sf(chi2_calc, df))

    # For 2x2 tables also compute the Yates continuity-corrected value —
    # the SPSS default — and accept a reported match against either
    chi2_yates = None
    p_yates = None
    if obs.shape == (2, 2):
        chi2_yates = float(np.sum(
            np.maximum(np.abs(obs - expected) - 0.5, 0)**2 / expected))
        p_yates = float(sp.chi2.sf(chi2_yates, df))

    flags = []
    chi2_matched = None
    if reported_chi2 is not None:
        def _chi2_close(calc):
            return abs(calc - reported_chi2) <= max(0.1, 0.05 * reported_chi2)
        if _chi2_close(chi2_calc):
            chi2_matched = 'pearson'
        elif chi2_yates is not None and _chi2_close(chi2_yates):
            chi2_matched = 'yates'
        else:
            flags.append(
                f"chi2: calculated {chi2_calc:.3f} (Pearson)"
                + (f" / {chi2_yates:.3f} (Yates)" if chi2_yates is not None
                   else "")
                + f", reported {reported_chi2}"
            )

    if reported_p is not None:
        def _p_close(calc):
            ratio = max(calc, 1e-20) / max(reported_p, 1e-20)
            return 0.1 < ratio < 10
        if not (_p_close(p_calc) or
                (p_yates is not None and _p_close(p_yates))):
            flags.append(
                f"p: calculated {p_calc:.2e}, reported {reported_p}"
            )

    result = {
        'consistent': len(flags) == 0,
        'chi2_calculated': round(chi2_calc, 4),
        'chi2_yates': round(chi2_yates, 4) if chi2_yates is not None else None,
        'chi2_matched': chi2_matched,
        'p_calculated': p_calc,
        'p_yates': p_yates,
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
            + (f" (reported value matches the "
               f"{'Yates-corrected' if chi2_matched == 'yates' else 'uncorrected Pearson'}"
               f" statistic)" if chi2_matched else "")
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
    sd: float, n: Optional[int], lo: float, hi: float, label: str = ""
) -> dict:
    """
    Heathers' 'quick SD check': is the reported SD plausible given the
    possible range of the data?

    For bounded data, the *population* SD <= range / 2 (half the points
    at each extreme).  Reported SDs are *sample* SDs, whose (n-1)
    denominator inflates the bound to range * sqrt(floor(n/2)*ceil(n/2)
    / (n*(n-1))) — e.g. [0, 0, 10] has sample SD 5.774 > 5.  The n-aware
    bound is used when n is known; the population bound only when n is
    None.

    Also: for most real data, SD << range / 2 — an SD near the bound
    means heavily bimodal data or outliers, which is flagged softly.

    Ref: Heathers (2025) ch. "The 'quick' SD check"
    """
    data_range = hi - lo
    if n is not None and n >= 2:
        # Max sample SD: floor(n/2) points at one extreme, ceil(n/2) at the
        # other, (n-1) denominator.  For even n this is (range/2)*sqrt(n/(n-1));
        # for odd n the even-split form overestimates (n=3 on [0,10]: true max
        # is [0,0,10] -> 5.7735, not 6.1237)
        k_lo = n // 2
        k_hi = n - k_lo
        max_possible_sd = data_range * math.sqrt(k_lo * k_hi / (n * (n - 1)))
    else:
        max_possible_sd = data_range / 2  # population bound (n unknown)

    # More realistic upper bound: SD of a uniform distribution = range / sqrt(12)
    uniform_sd = data_range / math.sqrt(12)

    flags = []
    if sd > max_possible_sd + 1e-9:
        flags.append(
            f"SD ({sd}) exceeds theoretical maximum ({max_possible_sd:.2f}) "
            f"for range [{lo}, {hi}]"
            f"{'' if n is None else f' at n={n}'} — IMPOSSIBLE"
        )
    # Softer flag, not short-circuited by the impossible one
    if sd > uniform_sd * 1.5:
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
# 17. Frozen SDs (constant variance across timepoints)
# ═══════════════════════════════════════════════════════════════════════════════

def check_frozen_sds(
    sds: List[List[float]],
    labels: Optional[List[str]] = None,
    group_labels: Optional[List[str]] = None,
) -> dict:
    """
    Check whether SDs are suspiciously constant across timepoints.

    In real longitudinal data, standard deviations naturally fluctuate
    across measurement occasions due to dropout, treatment effects,
    regression to the mean, and measurement noise.  Perfectly constant
    SDs across 3+ timepoints for many variables is a hallmark of
    fabricated data.

    Args:
        sds: list of SD series, each a list of SDs across timepoints
             for one variable/group combination.
             E.g., [[2.97, 2.97, 3.02], [3.20, 3.20, 3.20], ...]
        labels: optional label for each SD series
        group_labels: optional labels for timepoints (e.g., ["Baseline", "Week 6", "Week 12"])

    Returns:
        dict with 'n_frozen', 'n_total', 'frozen_fraction',
        'frozen_series' (which ones are frozen), and 'detail'.
    """
    if labels is None:
        labels = [f"series_{i}" for i in range(len(sds))]

    frozen = []
    for sd_series, label in zip(sds, labels):
        if len(sd_series) >= 2 and len(set(sd_series)) == 1:
            frozen.append(label)

    n_frozen = len(frozen)
    n_total = len(sds)
    frac = n_frozen / n_total if n_total > 0 else 0

    flags = []
    if frac > 0.5:
        flags.append(
            f"{n_frozen}/{n_total} ({frac:.0%}) SD series are perfectly "
            f"constant across all timepoints"
        )
    if n_frozen >= 5:
        flags.append(
            "5+ frozen SD series is extremely unlikely in real "
            "longitudinal data"
        )

    result = {
        'n_frozen': n_frozen,
        'n_total': n_total,
        'frozen_fraction': round(frac, 4),
        'frozen_series': frozen,
        'flags': flags,
    }
    if flags:
        result['detail'] = f"FLAG: {'; '.join(flags)}"
    else:
        result['detail'] = (
            f"PASS: {n_frozen}/{n_total} SD series are constant "
            f"({frac:.0%}) — within normal range"
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 18. Carlisle-Stouffer-Fisher test (Table 1 baseline p-values)
# ═══════════════════════════════════════════════════════════════════════════════

def carlisle_stouffer_fisher(
    p_values: Union[List[float], List[Tuple[float, str]]],
    label: str = "",
) -> Union[dict, List[dict]]:
    """
    Test whether a set of baseline comparison p-values (typically from
    Table 1 of an RCT) are suspiciously well-balanced.

    In a properly randomized trial, baseline p-values should be
    uniformly distributed on [0, 1]. If they cluster too high
    (everything is perfectly balanced), the randomization may be
    fabricated.

    Uses the Stouffer method: Z = sum(Phi_inv(1 - p_i)) / sqrt(k),
    then tests whether combined Z is significantly extreme.

    **Important:** Categorical and continuous baseline variables should
    be tested separately, because they have different distributional
    properties. Pooling them can mask a real signal in one stratum.

    Args:
        p_values: Either:
            - List[float]: plain p-values (backward compatible)
            - List[Tuple[float, str]]: typed p-values where str is
              "categorical" or "continuous".  When types are mixed,
              the function auto-splits and returns a list of results
              (one per type, plus a combined result).
        label: optional label

    Returns:
        dict (single result) when all p-values are the same type or
        untyped.  list[dict] when mixed types trigger auto-split —
        each dict has 'variable_type' key.

    Ref: Carlisle (2017) doi:10.1111/anae.13938
    Ref: Heathers (2025) ch. "Analyzing multiple Table 1 p-values"
    Ref: Meyerowitz-Katz — split by type.
    """
    # Detect typed input and auto-split if needed
    if p_values and isinstance(p_values[0], (tuple, list)):
        types_seen = set(t for _, t in p_values)
        if len(types_seen) > 1:
            results = []
            for vtype in sorted(types_seen):
                sub = [p for p, t in p_values if t == vtype]
                sub_label = f"{label} ({vtype})" if label else vtype
                r = carlisle_stouffer_fisher(sub, label=sub_label)
                r['variable_type'] = vtype
                results.append(r)
            # Also run combined for reference
            all_p = [p for p, _ in p_values]
            combined_label = f"{label} (combined)" if label else "combined"
            r_all = carlisle_stouffer_fisher(all_p, label=combined_label)
            r_all['variable_type'] = 'combined'
            r_all['_note'] = (
                'Combined result — interpret with caution. '
                'Categorical and continuous variables were also '
                'tested separately (see other results).'
            )
            results.append(r_all)
            return results
        else:
            # All same type — unwrap and run normally
            p_values = [p for p, _ in p_values]
    k = len(p_values)
    if k < 3:
        return {
            'sufficient_data': False,
            'detail': f"SKIP: need >= 3 p-values for Carlisle test (got {k})"
        }

    # Stouffer's method: convert p-values to z-scores and combine.
    # With z_i = Phi_inv(1 - p_i), HIGH p-values give NEGATIVE z-scores:
    # combined Z << 0 means the p-values cluster high (too well-balanced,
    # Carlisle's fabrication signature) and combined Z >> 0 means they
    # cluster low (genuinely unbalanced baselines).
    z_scores = [float(sp.norm.ppf(1 - p)) for p in p_values]
    combined_z = sum(z_scores) / math.sqrt(k)

    # Two-tailed: suspicious in either direction
    p_combined = float(sp.norm.sf(abs(combined_z)) * 2)

    # Also check: are p-values suspiciously uniform?
    # Kolmogorov-Smirnov test against U(0,1)
    ks_stat, ks_p = sp.kstest(p_values, 'uniform')

    # Are p-values too high? (suspiciously good balance)
    mean_p = sum(p_values) / k
    median_p = sorted(p_values)[k // 2]

    flags = []
    if p_combined < 0.05 and combined_z < 0:
        flags.append(
            f"Stouffer combined Z = {combined_z:.3f} (p = {p_combined:.4f}) — "
            f"baseline variables are suspiciously well-balanced"
        )
    if p_combined < 0.05 and combined_z > 0:
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
