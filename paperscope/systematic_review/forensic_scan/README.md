# `paperscope.systematic_review.forensic_scan`

Corpus-scale forensic data-quality scan. Run a battery of regex-based extractors over a text-extracted paper corpus, then aggregate into corpus-level statistics that no single-paper test would surface.

**Status:** v1, extracted from a working scoping-review scan (2026-05-16) that processed 2,443 text files in ~3 minutes producing 13,308 p-values, 603 effect+CI rows, 3,272 mean+SD+n triples, 2,443 funding classifications, and corpus-level p-curve / last-digit / positivity / salami summaries.

## Where this fits

- **`paperscope.analysis.forensic_stats`** = per-paper forensic tests (GRIM, GRIMMER, DEBIT, SPRITE, Carlisle, Benford, statcheck-style p-value verification). Use when you have one paper's reported summary statistics and want to verify them.
- **`paperscope.systematic_review.forensic_scan`** (this module) = corpus-scale extraction + aggregation. Use when you have thousands of papers and want population-level patterns (p-curve, publication bias, industry-funding effects, salami clustering).
- **`paperscope.systematic_review.methodological_audit`** = per-paper rubric-based methodological audit. Use when you want to grade each paper on construct adequacy, statistical hygiene, etc. (the orthogonal question to forensic data quality).

The three layers compose. The demo corpus used all three: methodological audit found 53.5% of the sampled papers `suspect` on construct adequacy; forensic scan found the corpus's data hygiene is generally clean (publication bias is the universal filter; no p-hacking, no fabrication signal); per-paper `forensic_stats` verification of the corpus-scan's specific flags found ~95% to be regex-extraction artefacts. Net result: the construct-adequacy story stands on its own, the forensic baseline is clean, and the spinoff methods finding is that off-the-shelf forensic tooling needs domain adaptation for the target literature.

## Pipeline at a glance

```
            ┌─────────────────────┐
text/*.txt ─┤  extract.py         │  regex extractors per paper:
            │                      │    extract_pvalues
            │                      │    extract_effects (HR/OR/RR + CI)
            │                      │    extract_mean_sd_n_triples
            │                      │    extract_funding_coi
            │                      │    extract_authors
            │                      │    extract_cohort_size
            │                      │    extract_positivity_mentions
            └──────────┬──────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │  aggregate.py       │  corpus-level summaries:
            │                      │    p_curve_summary (Simonsohn binom test)
            │                      │    last_digit_distribution (Newcomb-Benford)
            │                      │    positivity_rate (publication bias)
            │                      │    industry_vs_positivity (Welch t)
            │                      │    salami_screen
            └──────────┬──────────┘
                       │
                       ▼
            ┌─────────────────────┐
            │  scan.py            │  scan_corpus() orchestrator
            │                      │    writes 6 JSONLs + summary.json
            └─────────────────────┘
```

## Usage

### Full scan

```python
from paperscope.systematic_review.forensic_scan import scan_corpus

summary = scan_corpus(
    text_dir="lit-review/text/",
    out_dir="lit-review/audit/",
    progress=lambda i, n: print(f"  ...{i}/{n}"),
)
print(summary["p_curve"])
print(summary["positivity"])
print(summary["industry_vs_positivity"])
```

### Individual extractors

```python
from paperscope.systematic_review.forensic_scan.extract import (
    extract_pvalues, extract_effects, extract_funding_coi,
)
text = open("text/12345678.txt").read()
pvals = extract_pvalues(text, pmid="12345678")
effs = extract_effects(text, pmid="12345678")
funding = extract_funding_coi(text, pmid="12345678")
```

### Verifying a corpus-scan flag

```python
# corpus scan surfaced 11 statcheck-style flags; verify per paper
from paperscope.analysis.forensic_stats import check_anova_oneway
# for each flag, manually re-extract the test statistic + p from the paper
# and run the corresponding forensic_stats function with correct interpretation
```

## What works well at corpus scale

- **P-curve at corpus level** is robust. Even if individual p-value extractions are noisy, the aggregate shape (right-skew toward 0.01 = real effects; flat or left-skew toward 0.05 = p-hacking) is reliable from ~500 papers up. The demo corpus's 8,442 significant p-values gave a definitive Simonsohn binom test p ≈ 0 for right-skew.
- **Result-positivity ratio** as a publication-bias indicator. Average across the corpus is a stable population measure even with per-paper noise.
- **Last-digit distribution** distinguishes Newcomb-Benford (natural data) from fraud patterns (preference for 4/5/7 + avoidance of 0/9). The demo corpus found Newcomb-Benford, ruling out a fraud pattern.
- **Industry vs non-industry positivity** is a powerful cross-tab that needs both funding classification AND positivity per paper; the corpus scale makes the Welch t-test interpretable.
- **Salami screen** (author × cohort-size overlap) is high-precision when it fires; it misses distinct-cohort author-overlap salami.

## What false-positives at corpus scale (document explicitly)

1. **Statcheck-style p-value recomputation false-positives 95%+** on non-psychology papers. Mechanisms:
   - One-sided p-values mis-recomputed as two-sided
   - Omnibus ANOVA F mis-paired with post-hoc p (Tukey/LSD)
   - Mann-Whitney/Kruskal-Wallis rows mis-paired in dense table cells
   - η²ₚ effect sizes mis-parsed as p-values (PDF line-wrap)
   - Figure-caption asterisks read as inferential p-values
   The corpus-level **p-curve and last-digit distributions are valid** even with this — they depend on the p-value extractions, not the test-stat pairings.

2. **GRIM-style integer-decomposition false-positives 100%** on continuous-valued means. Such means are continuous (percentages, regression coefficients, rates, measured levels). Filter to integer-summed data (Likert scales, counts) before applying GRIM via `paperscope.analysis.forensic_stats.grim`.

3. **Salami false-positives** for legitimate companion papers from the same lab. The author × cohort-size overlap is a candidate flag, not a verdict.

4. **Funding classification is keyword-based.** Catches common pharma + COI language; misses non-Western pharma, academic-spinoff arrangements, subtle text.

## Output schema

- `forensic-per-paper.jsonl` — one row per paper: pmid, n_pvalues, n_effects, n_triples, n_wide_ci, n_ci_inconsistent, positivity_ratio, funding_classification, industry_linked, authors_set, cohort_size
- `forensic-pvalues.jsonl` — every extracted p-value: pmid, p_reported, p_str, op, test_type (if found), test_params, context_excerpt
- `forensic-effects.jsonl` — every effect+CI row: pmid, kind (HR/OR/RR), estimate, ci_lo, ci_hi, ci_consistent, excludes_null, implausibly_wide, width_over_est, context_excerpt
- `forensic-mean-sd-n.jsonl` — every mean+SD+n triple: pmid, mean, sd, n_candidates, n_used, decimals, context_excerpt (use with `forensic_stats.grim` after filtering for integer-data)
- `forensic-funding.jsonl` — per-paper funding/COI classification
- `forensic-salami.jsonl` — pmid-pair flags with shared cohort size + author overlap
- `forensic-summary.json` — corpus-level aggregates (p-curve, last-digit, positivity, industry × positivity, salami count)

## See also

- `paperscope.analysis.forensic_stats` — per-paper forensic tests
- `paperscope.systematic_review.methodological_audit` — per-paper rubric-based audit (orthogonal failure mode: does the paper ask the right question? vs forensic: are the numbers honest?)
- Demo: the headline numbers quoted above come from the author's (private) scoping-review run; the output files in the schema above are everything needed to write the equivalent findings report for your own corpus
