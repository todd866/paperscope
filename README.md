# Paperscope

**An AI-assisted toolkit for academic paper analysis, systematic reviews, corpus-scale evidence mapping, and review knowledge bases.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## What This Does

Paperscope is a Python toolkit for working with academic papers at both manuscript and corpus scale. It supports pre-submission checks on your own work, critical reads of someone else's manuscript, and AI-assisted scoping reviews where a review corpus becomes a queryable evidence base rather than a spreadsheet dump.

The core premise is that paper-level evaluation and corpus-level evaluation are inseparable. A paper is only meaningful relative to the literature it claims to extend, cite, contradict, ignore, or compress. Paperscope therefore treats "evaluate this paper" as a local view into "evaluate this corpus": citation checks, novelty, method resolution, overclaiming, forensic flags, and review synthesis all depend on knowing what the surrounding corpus looks like.

- **Semantic analysis** — embeds a manuscript and its literature into a shared vector space to catch citation misalignment, unsupported claims, abstract gaps, and missing related work
- **Forensic statistics** — 19 data-integrity checks (GRIM, GRIMMER, SPRITE, correlation bounds, p-value recalculation, Carlisle test, and more) based on Heathers (2025) [*An Introduction to Forensic Metascience*](https://jamesheathers.curve.space/)
- **Critical read** — author profiling, method-resolution mismatch detection, overclaiming analysis
- **Bibliography pipeline** — citation extraction, DOI resolution, retraction detection, literature discovery
- **Systematic literature reviews** — JBI / PRISMA-ScR pipeline (harvest → screen → extract → validate → synthesise) for AI-accelerated scoping reviews, with a human audit layer and a static-HTML review site. Reviews are protocol-as-data: one YAML defines PCC, search query blocks, screening rubric, charting schema, and aggregation rules. The `validate` step turns AI screening/extraction decisions into a human work queue (the model self-flags its low-confidence calls; the human adjudicates only those; flips reconcile back append-only) — see [`docs/validate.md`](docs/validate.md). See also [`paperscope/systematic_review/`](paperscope/systematic_review/) and [`docs/systematic-review.md`](docs/systematic-review.md).
- **Review knowledge bases** — emerging tooling for turning large review corpora into paper cards, cluster pages, quality flags, private source-object links, and public summaries. See [`docs/corpus-knowledge-base.md`](docs/corpus-knowledge-base.md).

## Current Dogfood Case

Paperscope is being stress-tested against a large motor neurone disease / amyotrophic lateral sclerosis review corpus: thousands of records, a 1,800+ paper working evidence base, AI-assisted charting, paper-card generation, quality flags, rich metadata, dual-rater comparison, and a searchable collaborator portal. That project is deliberately treated as a dogfood case rather than Paperscope's hard-coded identity. Generic pieces are being pulled back into Paperscope; disease-specific rubrics, claims, and synthesis outputs stay in the caller project.

The dogfood work has made the next frontier clear: Paperscope should not stop at "screen and aggregate." For large reviews, the useful product is a corpus knowledge base that lets a reader ask questions such as:

- What is this cluster of papers about?
- Which papers support this claim?
- Which studies are externally validated?
- Which papers are likely off-scope, mismatched, or methodologically weak?
- Where are the source PDFs or text extracts, and what can be shared publicly?

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

### Systematic literature reviews

```bash
# Show the composed Boolean query / per-block counts (sanity-check the strategy)
python3 -m paperscope.systematic_review search myreview.yaml --show-query
python3 -m paperscope.systematic_review search myreview.yaml --block-counts

# Harvest MEDLINE into records.jsonl
python3 -m paperscope.systematic_review search myreview.yaml

# Aggregate charted JSONL into synthesis tables
python3 -m paperscope.systematic_review aggregate myreview.yaml

# PRISMA-ScR flow from records + screening JSONL
python3 -m paperscope.systematic_review prisma --config myreview.yaml

# Static HTML review site (Covidence-style record pages, no JS)
python3 -m paperscope.systematic_review build-site --config myreview.yaml --out ./review-site

# Optional institutional-access browser harvest for the paywalled tail
python3 -m paperscope.systematic_review browser-harvest \
  --config myreview.yaml \
  --user-data-dir "$HOME/Library/Application Support/Google/Chrome" \
  --profile-directory Default \
  --group-by-publisher \
  --inter-paper-delay 5
```

Module README: [`paperscope/systematic_review/README.md`](paperscope/systematic_review/README.md). Design + roadmap: [`docs/systematic-review.md`](docs/systematic-review.md).
Corpus knowledge-base roadmap: [`docs/corpus-knowledge-base.md`](docs/corpus-knowledge-base.md).

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

## Examples

See [`examples/forensic_replication/`](examples/forensic_replication/) for 4 worked examples replicating published expert forensic analyses (Meyerowitz-Katz, Plöderl, Hussey, Cristea). Across 4 papers, Paperscope confirmed 21 of 22 expert findings (95.5%) and identified additional issues not in the original analyses.

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
