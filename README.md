# Paperscope

**A toolkit for writing and reviewing academic papers.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## What This Does

Paperscope is a Python toolkit for academic paper analysis. Every tool works on both sides of peer review — check your own work before submission, or audit someone else's manuscript.

- **Semantic analysis** — embeds a manuscript and its literature into a shared vector space to catch citation misalignment, unsupported claims, abstract gaps, and missing related work
- **Forensic statistics** — 19 data-integrity checks (GRIM, GRIMMER, SPRITE, correlation bounds, p-value recalculation, Carlisle test, and more) based on Heathers (2025) [*An Introduction to Forensic Metascience*](https://jamesheathers.curve.space/)
- **Critical read** — author profiling, method-resolution mismatch detection, overclaiming analysis
- **Bibliography pipeline** — citation extraction, DOI resolution, retraction detection, literature discovery

## Install

```bash
git clone https://github.com/todd866/paperscope.git
cd paperscope
pip install -r requirements.txt
export PAPERSCOPE_EMAIL="you@university.edu"  # for OpenAlex/CrossRef polite pool
```

For better embeddings (optional but recommended):
```bash
pip install sentence-transformers
```

Without `sentence-transformers`, embedding-based tools fall back to TF-IDF (which requires `scikit-learn`, included in requirements).

### Integration with AI coding assistants

Paperscope works as a CLI that any AI assistant can call. Two tested workflows:

**Claude Code:** Clone into your project or a known path. Claude reads the `CLAUDE.md` file and uses the CLI when working on papers. You can also use `--plugin-dir` for skill auto-invocation:
```bash
claude --plugin-dir /path/to/paperscope
```

**Codex:** Copy `AGENTS.md` into your paper project directory. Codex reads it and calls the CLI when relevant:
```bash
cp /path/to/paperscope/AGENTS.md /path/to/your/paper/
```

## CLI Commands

### Semantic analysis (your own papers)

```bash
# Full analysis: citation alignment, novelty, strength heatmap
python3 -m paperscope analyze paper.tex --literature text/

# Abstract coverage check
python3 -m paperscope abstract-check paper.tex

# Journal semantic fit ranking
python3 -m paperscope journal-fit paper.tex -j "BioSystems" "PLOS ONE"

# Semantic diff between revisions
python3 -m paperscope revision-diff old.tex new.tex

# Find missing related work (needs PAPERSCOPE_EMAIL)
python3 -m paperscope related paper.tex
```

### Critical read (external papers)

```bash
# Full critical read of an external paper
python3 -m paperscope critical-read paper.pdf

# With explicit author names (skips auto-extraction)
python3 -m paperscope critical-read paper.pdf --authors "Alice Smith" "Bob Jones"

# Offline mode (skip OpenAlex author lookup)
python3 -m paperscope critical-read paper.pdf --skip-author-lookup
```

Runs four analyses: author/COI profiling, method-resolution mismatch detection, missing complementary methods, and overclaiming detection.

### Forensic statistics (data integrity)

```bash
# Run the built-in demo audit (Rajizadeh et al. 2017 magnesium paper)
python3 -m paperscope.analysis.forensic_stats

# Or import individual checks in Python
from paperscope.analysis.forensic_stats import grim, debit, correlation_bound
print(grim(mean=26.9, n=26, dp=1))         # GRIM test
print(debit(percentage=88.5, n=26, dp=1))   # DEBIT test
print(correlation_bound(0.13, 0.27, 0.03))  # impossible r
```

The forensic module is a Python library, not a CLI command. You transcribe summary statistics from the paper's tables and feed them to the functions. The checks are automated; the data entry is manual.

### Bibliography pipeline

```bash
# Extract citations from LaTeX
python3 -m paperscope extract /path/to/paper/

# Resolve missing DOIs via CrossRef
python3 -m paperscope resolve bibliography.json

# Verify DOIs and detect retractions
python3 -m paperscope verify bibliography.json

# Discover new papers matching your research profile
python3 -m paperscope harvest --config config.yaml

# Download open-access PDFs and extract text
python3 -m paperscope ingest /path/to/literature/

# Pre-submission citation check
python3 -m paperscope pre-submit paper.tex --bib bibliography.json
```

## Forensic Statistics Reference

19 functions based on techniques from Heathers (2025) [*An Introduction to Forensic Metascience*](https://jamesheathers.curve.space/) (DOI: [10.5281/zenodo.14871843](https://doi.org/10.5281/zenodo.14871843)).

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

## How It Works

**Semantic analysis** (embedding-based tools):
1. LaTeX is cleaned to plain text, split into ~200-word overlapping chunks
2. Chunks encoded using sentence-transformers (all-MiniLM-L6-v2, 384-dim), or TF-IDF as fallback
3. Cosine similarity matrices between paper chunks and literature chunks power the analysis modules

**Critical read** (external papers):
1. PDF text extracted via PyMuPDF
2. Sections auto-detected (methods, results, discussion, conclusions)
3. Four independent analyses: author COI, resolution mismatch, missing methods, overclaiming

**Forensic statistics** (data integrity):
1. Reviewer transcribes summary statistics from paper tables
2. 19 automated checks test internal consistency
3. Results classified as pass, flag (suspicious), or fail (impossible)

For the full technical description, see the [paper (PDF)](paper/paperscope.pdf).

## Example

See [`examples/rajizadeh_2017_magnesium/`](examples/rajizadeh_2017_magnesium/) for a complete worked example: a forensic audit of a published RCT that found 14 impossible statistics and 7 suspicious flags across 50 checks. Includes a 6-page PDF report, raw outputs, and LaTeX source.

## Development Workflow

Paperscope is developed using a multi-model feedback loop:

1. **Claude Code** (Opus) writes features and runs analyses
2. **Codex** reviews the code and output, producing detailed findings
3. The human routes Codex's feedback back to Claude for fixes
4. Repeat until Codex stops finding issues

This loop catches bugs that either model would miss alone -- Claude builds fast but can be overconfident about its own output; Codex is a thorough critic but doesn't write the fixes. The human's role is routing and judgment: deciding which findings matter and when the code is done.

The forensic statistics module went through three review passes this way, fixing 11 issues including empty-corpus crashes, false-negative verdicts, broken retraction detection, and over-aggressive author name filtering.

## Requirements

- Python 3.8+
- `numpy`, `scipy`, `scikit-learn`, `requests` (all in `requirements.txt`)
- `PyMuPDF` for PDF text extraction
- `sentence-transformers` (optional, recommended -- better embeddings than TF-IDF fallback)
- `matplotlib`, `networkx` (optional -- for visualization)

## License

MIT -- see [LICENSE](LICENSE).
