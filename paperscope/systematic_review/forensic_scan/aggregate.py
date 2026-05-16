"""Corpus-level aggregations: p-curve, last-digit, positivity, industry-bias, salami.

Each function takes the per-paper extracted rows from `extract.py` and
returns a corpus-level summary dict that's suitable for writing to a report.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from scipy.stats import binomtest, chi2 as chi2_dist


def p_curve_summary(pvalue_rows: list[dict]) -> dict:
    """Simonsohn p-curve at corpus scale.

    Returns:
      - bin_counts: counts in (0, 0.01], (0.01, 0.02], ..., (0.04, 0.05]
      - n_below_025 vs n_in_025_to_05 (right-skew test inputs)
      - right_skew_binom_p: binom test p-value (small p = right-skew = real
        effects; large p = flat or left-skew = p-hacking suspect)
      - p_hacking_ratio: |[0.04, 0.05)| / |[0.01, 0.02)| — ratio < 1 means
        less concentration near significance boundary than well below it
    """
    sig = [r["p_reported"] for r in pvalue_rows if r["p_reported"] < 0.05 and r["op"] in ("=", "<")]
    if not sig:
        return {"n_significant": 0}
    bins = [0, 0.01, 0.02, 0.03, 0.04, 0.05]
    counts = [0] * (len(bins) - 1)
    for p in sig:
        for i in range(len(bins) - 1):
            if bins[i] <= p < bins[i + 1]:
                counts[i] += 1
                break
    n_low = sum(1 for p in sig if p < 0.025)
    n_high = sum(1 for p in sig if 0.025 <= p < 0.05)
    binom_p = None
    if n_low + n_high > 20:
        res = binomtest(n_low, n_low + n_high, p=0.5, alternative="greater")
        binom_p = res.pvalue
    n_just_under = sum(1 for p in sig if 0.04 <= p < 0.05)
    n_well_under = sum(1 for p in sig if 0.01 <= p < 0.02)
    return {
        "n_significant": len(sig),
        "bin_counts": dict(zip([f"<{b:.2f}" for b in bins[1:]], counts)),
        "n_below_025": n_low,
        "n_in_025_to_05": n_high,
        "right_skew_binom_p": binom_p,
        "p_hacking_ratio_04_05_over_01_02": (n_just_under / max(n_well_under, 1)) if n_well_under else None,
    }


def last_digit_distribution(pvalue_rows: list[dict]) -> dict:
    """Distribution of last-typed digit in p-values reported with `=`.
    Use the ORIGINAL string (preserves trailing zeros) — `0.020` counts as
    last-digit 0, not 2.

    Returns counts per digit + chi-square test against uniformity.

    INTERPRETATION CAVEAT: non-uniformity is usually Newcomb-Benford (small-
    digit preference from logarithmic underlying distribution), not fraud.
    Fraud patterns prefer 4/5/7 and avoid 0/9; Newcomb-Benford prefers 1-4
    and is roughly monotone-decreasing thereafter."""
    counts = Counter()
    for r in pvalue_rows:
        if r.get("op") != "=":
            continue
        s = r.get("p_str", "")
        if not s or "." not in s:
            continue
        last = s[-1]
        if last.isdigit():
            counts[int(last)] += 1
    total = sum(counts.values())
    out = {"counts": {str(d): counts.get(d, 0) for d in range(10)}, "n": total}
    if total >= 100:
        expected = [total / 10] * 10
        observed = [counts.get(d, 0) for d in range(10)]
        chi2 = sum((o - e) ** 2 / e for o, e in zip(observed, expected))
        out["chi2"] = chi2
        out["chi2_p_uniform"] = 1 - chi2_dist.cdf(chi2, 9)
        # Distinguish Newcomb-Benford from fraud
        small_digit_pct = sum(counts.get(d, 0) for d in (1, 2, 3, 4)) / total
        fraud_pattern_pct = sum(counts.get(d, 0) for d in (4, 5, 7)) / total
        zero_nine_pct = sum(counts.get(d, 0) for d in (0, 9)) / total
        out["interpretation"] = (
            "newcomb_benford" if small_digit_pct > 0.45
            else "possible_fraud" if (fraud_pattern_pct > 0.40 and zero_nine_pct < 0.10)
            else "ambiguous"
        )
    return out


def positivity_rate(positivity_rows: list[dict]) -> dict:
    """Corpus-level publication-bias indicator: average positivity ratio across
    papers that use significance language. >0.85 papers = high-positivity."""
    valid = [r for r in positivity_rows if r.get("positivity_ratio") is not None]
    if not valid:
        return {"n_papers": 0}
    rates = [r["positivity_ratio"] for r in valid]
    return {
        "n_papers_with_significance_lang": len(valid),
        "mean_positivity": sum(rates) / len(rates),
        "n_above_85pct_positive": sum(1 for r in rates if r > 0.85),
        "fraction_above_85pct": sum(1 for r in rates if r > 0.85) / len(rates),
    }


def industry_vs_positivity(funding_rows: list[dict], positivity_rows: list[dict]) -> dict:
    """Welch t-test on positivity ratio: industry-linked vs non-industry papers."""
    from scipy.stats import ttest_ind
    pos_by_pmid = {r["pmid"]: r["positivity_ratio"] for r in positivity_rows
                   if r.get("positivity_ratio") is not None}
    industry_rates: list[float] = []
    non_industry_rates: list[float] = []
    for f in funding_rows:
        pr = pos_by_pmid.get(f["pmid"])
        if pr is None:
            continue
        if f["industry_linked"]:
            industry_rates.append(pr)
        else:
            non_industry_rates.append(pr)
    if not industry_rates or not non_industry_rates:
        return {"n_industry": len(industry_rates), "n_non_industry": len(non_industry_rates)}
    t_stat, p_val = ttest_ind(industry_rates, non_industry_rates, equal_var=False)
    return {
        "n_industry": len(industry_rates),
        "n_non_industry": len(non_industry_rates),
        "mean_industry_positivity": sum(industry_rates) / len(industry_rates),
        "mean_non_industry_positivity": sum(non_industry_rates) / len(non_industry_rates),
        "welch_t": t_stat,
        "welch_p": p_val,
    }


def salami_screen(per_paper_rows: list[dict]) -> list[dict]:
    """Flag (pmid, pmid) pairs sharing ≥3 author surnames AND identical cohort
    size. Conservative — misses distinct-cohort author-overlap salami."""
    authors_per = {r["pmid"]: r.get("authors_set", set()) for r in per_paper_rows}
    cohort_per = {r["pmid"]: r.get("cohort_size") for r in per_paper_rows}
    by_size: dict[int, list[str]] = defaultdict(list)
    for pmid, n in cohort_per.items():
        if n is not None:
            by_size[n].append(pmid)
    flags = []
    for size, group in by_size.items():
        if len(group) < 3:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a = authors_per.get(group[i], set()) or set()
                b = authors_per.get(group[j], set()) or set()
                overlap = a & b
                if len(overlap) >= 3:
                    flags.append({
                        "pmid_a": group[i],
                        "pmid_b": group[j],
                        "shared_cohort_n": size,
                        "shared_authors": sorted(overlap),
                        "n_shared": len(overlap),
                    })
    return flags
