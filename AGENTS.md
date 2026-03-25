# Paperscope — Codex Instructions

When working on academic papers (.tex or .pdf files), you have access to paperscope analysis tools via the CLI. Use them proactively when relevant.

## When to run analysis

- **After drafting or revising a paper**: run `analyze` to check citations, novelty, and argument strength
- **Before submission**: run `abstract-check` to verify coverage, `cite-check` to verify references
- **When choosing journals**: run `journal-fit` with candidate journal names
- **After revision**: run `revision-diff` to verify changes addressed concerns
- **When reviewing bibliography**: run `related` to find missing related work
- **When reviewing an external paper**: run `critical-read` on the PDF
- **When checking reported statistics**: import functions from `paperscope.analysis.forensic_stats`

## Commands

```bash
# Full analysis: citation alignment, novelty, strength heatmap
python3 -m paperscope analyze paper.tex --literature text/

# Abstract coverage check
python3 -m paperscope abstract-check paper.tex

# Journal semantic fit ranking
python3 -m paperscope journal-fit paper.tex -j "Journal Name 1" "Journal Name 2"

# Semantic diff between revisions
python3 -m paperscope revision-diff old.tex new.tex --literature text/

# Find missing related work (requires PAPERSCOPE_EMAIL env var)
python3 -m paperscope related paper.tex

# Critical read of an external paper
python3 -m paperscope critical-read paper.pdf
python3 -m paperscope critical-read paper.pdf --authors "Name One" "Name Two"
python3 -m paperscope critical-read paper.pdf --skip-author-lookup

# Citation verification pipeline
python3 -m paperscope extract .
python3 -m paperscope verify bibliography.json
python3 -m paperscope resolve bibliography.json

# Forensic statistics demo (built-in example)
python3 -m paperscope.analysis.forensic_stats
```

## Forensic statistics

The forensic module is a Python library for checking data integrity in reported statistics. Import and call functions directly:

```python
from paperscope.analysis.forensic_stats import (
    grim, grimmer, debit, sprite, correlation_bound,
    check_ttest_paired, check_ttest_independent,
    check_anova_oneway, check_chi_squared,
    carlisle_stouffer_fisher, effect_size_consistency,
    check_sd_se_confusion, quick_sd_check,
    check_contingency_table, benfords_law,
    variance_ratio_test, check_change_arithmetic,
    check_sd_positive, sample_size_from_t,
)
```

Typical workflow: transcribe summary statistics from the paper's tables, then run applicable checks. Only report failures and flags in the review.

## Interpreting output

All commands produce JSON output. After running a command:

1. **Citation alignment**: Flag contexts with alignment below 0.4. Check whether the citation is genuinely wrong or just semantically indirect. Suggest replacement references from the bibliography.
2. **Novelty detection**: Claims with max literature similarity below 0.4 are novel. The paper's thesis being novel is expected — flag claims that are novel but lack justification.
3. **Strength heatmap**: Paragraphs with citation support below 0.3 may need references. Methodology and transition paragraphs are exceptions.
4. **Abstract check**: Sections with below-median similarity to the abstract are underrepresented. Suggest specific 1-sentence additions.
5. **Critical read**: Check the verdict severity and flags. If verdict is "incomplete", some analyses failed due to missing sections. Overclaiming scores above 0.6 are significant.
6. **Forensic stats**: Only report FAIL and FLAG results. Frame as "internal inconsistencies" and request raw data. Never allege fraud.

## Literature directory

Analysis commands need a directory of .txt files extracted from reference papers. Check these locations in order: `text/`, `literature/text/`, `literature/`, `lit/`. If missing, suggest running `python3 -m paperscope ingest` first.
