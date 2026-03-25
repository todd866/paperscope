# Paperscope

**A plugin for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and [Codex](https://developers.openai.com/codex/cli/) that analyzes academic papers.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## What This Does

Paperscope gives your AI coding assistant the ability to analyze LaTeX papers. It embeds your paper and its literature into a shared vector space, then measures distances to catch problems that normally require manual reading.

Works with Claude Code (plugin with auto-invocation) and Codex (via AGENTS.md).

### Skills

| Skill | Claude uses it when... |
|-------|----------------------|
| **analyze** | You're reviewing a paper, checking citations, or preparing for submission |
| **abstract-check** | You're finalizing a paper or checking abstract completeness |
| **journal-fit** | You're choosing where to submit |
| **revision-diff** | You're comparing paper versions or checking reviewer response |
| **related** | You're looking for missing related work |
| **cite-check** | You're verifying bibliography accuracy or cleaning up .bib files |

### What it catches

- **Citation misalignment** -- a sentence cites Reference A, but Reference B is the actual semantic match
- **Unsupported claims** -- paragraphs with no citation support that reviewers will flag
- **Novel claims without justification** -- your new contributions that need stronger backing
- **Abstract gaps** -- sections of the paper not represented in the abstract
- **Missing related work** -- papers you should cite but don't know about yet
- **Bad metadata** -- DOIs that don't match, missing DOIs, duplicate references
- **Impossible statistics** -- GRIM/DEBIT/SPRITE tests on means and percentages, correlation bound violations, p-value recalculation failures, arithmetic inconsistencies in tables
- **Fabrication signals** -- Benford's law deviations, suspiciously uniform variances, impossible SDs, effect size inconsistencies

## Install

### Claude Code

In any Claude Code session:

```
/plugin marketplace add todd866/paperscope
/plugin install paperscope@todd866-paperscope
```

Then install the Python dependencies:

```bash
pip install numpy requests sentence-transformers PyMuPDF
export PAPERSCOPE_EMAIL="you@university.edu"
```

Claude auto-invokes paperscope skills when working on LaTeX papers. You can also test with `--plugin-dir`:

```bash
git clone https://github.com/todd866/paperscope.git ~/.paperscope
pip install -r ~/.paperscope/requirements.txt
claude --plugin-dir ~/.paperscope
```

### Codex

```bash
git clone https://github.com/todd866/paperscope.git ~/.paperscope
pip install -r ~/.paperscope/requirements.txt

# Copy AGENTS.md into your paper project
cp ~/.paperscope/AGENTS.md /path/to/your/paper/AGENTS.md
```

Codex reads AGENTS.md and uses the paperscope CLI when working on your manuscript.

## Example

```
You: I've finished revising section 3, can you check the citations?

Claude: I'll run a citation analysis on your paper.
        [uses paperscope:analyze automatically]

        Citation alignment: 73% (11/15 contexts aligned)

        3 issues found:

        1. Line 142: "cortical oscillations maintain coherence"
           cites [zhang2019] but best match is [buzsaki2006]
           → Suggest replacing citation

        2. Line 203: Novel claim (max similarity: 0.28)
           "dimensional collapse below d=3 forces categorization"
           → This is your main contribution. Justification in §4 looks solid.

        3. Line 89: Weak paragraph (citation support: 0.19)
           → Consider citing [tononi2016] on integrated information.
```

## How It Works

1. **Text processing** -- LaTeX is cleaned to plain text, split into ~200-word overlapping chunks
2. **Embedding** -- Chunks encoded using sentence-transformers (all-MiniLM-L6-v2, 384-dim). Falls back to TF-IDF if the model isn't installed
3. **Similarity** -- Cosine similarity matrices between your paper chunks and literature chunks power all 12 analysis tools

For the full technical description, see the [paper (PDF)](paper/paperscope.pdf).

## CLI

The skills wrap a Python CLI. You can also run commands directly:

```bash
python3 -m paperscope analyze paper.tex --literature text/
python3 -m paperscope abstract-check paper.tex
python3 -m paperscope journal-fit paper.tex -j "BioSystems" "PLOS ONE"
python3 -m paperscope revision-diff old.tex new.tex
python3 -m paperscope related paper.tex
python3 -m paperscope extract . && python3 -m paperscope verify bibliography.json
```

### Forensic statistics

Run data-integrity checks on any paper's summary statistics tables:

```bash
# Run the demo audit (Rajizadeh et al. 2017 magnesium paper)
python3 -m paperscope.analysis.forensic_stats

# Or import individual checks
python3 -c "
from paperscope.analysis.forensic_stats import grim, debit, correlation_bound
print(grim(mean=26.9, n=26, dp=1))         # GRIM test
print(debit(percentage=88.5, n=26, dp=1))   # DEBIT test
print(correlation_bound(0.13, 0.27, 0.03))  # impossible r
"
```

**Available checks (19 functions):**

Based on techniques from Heathers (2025) [*An Introduction to Forensic Metascience*](https://jamesheathers.curve.space/) (DOI: [10.5281/zenodo.14871843](https://doi.org/10.5281/zenodo.14871843)).

| Check | Detects |
|-------|---------|
| `grim()` | Impossible means for integer-valued instruments (BDI, Likert, counts) |
| `grimmer()` | Impossible SDs for integer data (extends GRIM to standard deviations) |
| `debit()` | Impossible percentages from discrete counts |
| `sprite()` | Whether any valid dataset can produce the reported mean + SD |
| `correlation_bound()` | Impossible pre/post/change SD combinations (implied \|r\| > 1) |
| `check_ttest_paired()` | Recalculates paired t-test p-values from reported statistics |
| `check_ttest_independent()` | Recalculates independent t-test p-values |
| `check_anova_oneway()` | Recalculates one-way ANOVA F and p from group statistics |
| `check_chi_squared()` | Recalculates chi-squared from contingency tables |
| `sample_size_from_t()` | Back-calculates n from reported t and p |
| `effect_size_consistency()` | Cross-checks Cohen's d, p-values, and confidence intervals |
| `carlisle_stouffer_fisher()` | Tests whether Table 1 baseline p-values are too well-balanced |
| `check_sd_se_confusion()` | Flags likely SD/SE mix-ups given data range |
| `quick_sd_check()` | Checks SD plausibility against data range bounds |
| `check_contingency_table()` | Verifies row/column marginal totals are consistent |
| `benfords_law()` | Tests first-digit distribution against Benford's law |
| `variance_ratio_test()` | Flags suspiciously similar or divergent group variances |
| `check_change_arithmetic()` | Verifies End - Baseline = reported Change |
| `check_sd_positive()` | Flags negative standard deviations |

## Requirements

- Python 3.8+
- `numpy`, `requests`
- `sentence-transformers` (optional -- falls back to TF-IDF)
- `PyMuPDF` for PDF text extraction

## License

MIT -- see [LICENSE](LICENSE).
