"""Corpus-scale forensic data-quality scan.

This module runs forensic data-integrity checks at corpus scale (thousands of
text-extracted papers). It complements `paperscope.analysis.forensic_stats`,
which implements the individual single-paper tests (GRIM, GRIMMER, DEBIT,
SPRITE, Carlisle, Benford, statcheck-style p-value verification).

What this module ADDS:

  - **Corpus-scale extraction** of p-values, effect-size+CI rows, mean+SD+n
    triples, funding/COI statements, and author surnames.
  - **Corpus-level aggregations**:
        * p-curve (Simonsohn) — corpus-level p-value distribution
        * result-positivity ratio — publication-bias signature
        * p-value last-digit distribution (Newcomb-Benford)
        * funding × positivity cross-tabulation
        * salami-screen via author × cohort-size overlap

What this module does NOT do (intentionally):

  - Single-paper forensic tests (GRIM, statcheck, etc.) — those live in
    `paperscope.analysis.forensic_stats`. This module extracts data; that
    module verifies it.

Known false-positive modes (DOCUMENTED; the demo corpus found them the hard way):

  1. **statcheck false positives ~95%** on the target corpus because the
     literature does not use APA-formatted `t(df) = X, p = Y` notation.
     Dominant failure modes:
        - One-sided p-values mis-recomputed as two-sided
        - Omnibus ANOVA F mis-paired with post-hoc p (Tukey/LSD)
        - Mann-Whitney/Kruskal-Wallis rows mis-paired in dense table cells
        - η²ₚ effect sizes mis-parsed as p-values when PDF wraps the line
        - Figure-caption asterisks captured as inferential p-values
     The corpus-level p-curve and last-digit distributions are STILL valid;
     individual statcheck flags need manual verification.

  2. **GRIM false positives ~100%** on this corpus because the reported means
     are almost universally continuous (percentages, regression coefficients,
     rates, measured levels). GRIM assumes integer-summed data; without that
     assumption, the integer-decomposition test gives meaningless results.
     A continuous-vs-integer filter is on the v0.3 roadmap; until then, treat
     GRIM-flagged means as candidates for manual verification, not findings.

  3. **Last-digit distribution non-uniformity is usually Newcomb-Benford,
     not fraud.** Naturally-arising numerical data have first-digit and last-
     digit distributions concentrated at smaller digits because of the
     logarithmic underlying distribution of magnitudes. Fraud patterns show
     PREFERENCE for digits 4, 5, 7 and AVOIDANCE of 0, 9. Inspect the shape
     before concluding fabrication.

  4. **Salami-slicing false positives** when ≥3-author overlap occurs between
     legitimate companion papers from the same lab. The screen flags
     candidates; manual review distinguishes companion-paper from salami.

  5. **Funding-COI classification is rough.** The keyword-based industry
     detector catches common pharma names + COI language but misses
     non-Western pharma, academic-spinoff consulting arrangements, and
     subtle text like "the funder had no role in study design."

Use this module to GENERATE the corpus-level patterns; use `forensic_stats`
to VERIFY individual papers; use the agent-orchestration layer of your choice
(Anthropic SDK / OpenAI SDK / local) for high-confidence manual verification
of specific flags.

Submodules:
    extract      — text-corpus extractors for p-values, effect+CI rows,
                   mean+SD+n triples, funding/COI, authors, cohort-size
    aggregate    — p-curve, last-digit distribution, positivity,
                   industry × positivity, salami screen
    scan         — top-level orchestrator that runs the full v2 scan
"""

from paperscope.systematic_review.forensic_scan.extract import (
    extract_pvalues,
    extract_effects,
    extract_mean_sd_n_triples,
    extract_funding_coi,
    extract_authors,
    extract_cohort_size,
)
from paperscope.systematic_review.forensic_scan.aggregate import (
    p_curve_summary,
    last_digit_distribution,
    positivity_rate,
    industry_vs_positivity,
    salami_screen,
)
from paperscope.systematic_review.forensic_scan.scan import scan_corpus

__all__ = [
    "extract_pvalues",
    "extract_effects",
    "extract_mean_sd_n_triples",
    "extract_funding_coi",
    "extract_authors",
    "extract_cohort_size",
    "p_curve_summary",
    "last_digit_distribution",
    "positivity_rate",
    "industry_vs_positivity",
    "salami_screen",
    "scan_corpus",
]
