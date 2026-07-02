# PaperScope

**An AI-assisted toolkit for academic paper analysis, systematic reviews, corpus-scale evidence mapping, and review knowledge bases.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## Three tools, three jobs

PaperScope is one of three linked but distinct tools:

| Tool | Does | Input → Output |
|---|---|---|
| **PaperScope** (this repo) | **Analyzes** the literature — bibliography / DOI / retraction QA, forensic metascience, systematic reviews, embeddings. | papers → checked analysis |
| [LocalEvidence](https://github.com/todd866/LocalEvidence) | **Answers** a clinical question from a library you own, grounded and cited. | a question + your library → a cited evidence pack |
| [EvidenceViewer](https://github.com/todd866/EvidenceViewer-public) | **Presents** any source-backed artifact through one contract + viewer, every claim traceable to its source. | an EvidenceArtifact → a source-linked reading UI |

The pipeline: **PaperScope analyzes → LocalEvidence answers** (using PaperScope's fact-checking) **→ EvidenceViewer presents** either one's output.

## What This Does

PaperScope is a Python toolkit for working with academic papers at both manuscript and corpus scale. It supports pre-submission checks on your own work, critical reads of someone else's manuscript, and AI-assisted scoping reviews where a review corpus becomes a queryable evidence base rather than a spreadsheet dump.

The core premise is that paper-level evaluation and corpus-level evaluation are inseparable. A paper is only meaningful relative to the literature it claims to extend, cite, contradict, ignore, or compress. PaperScope therefore treats "evaluate this paper" as a local view into "evaluate this corpus": citation checks, novelty, method resolution, overclaiming, forensic flags, and review synthesis all depend on knowing what the surrounding corpus looks like.

- **Semantic analysis** — embeds a manuscript and its literature into a shared vector space to catch citation misalignment, unsupported claims, abstract gaps, and missing related work
- **Forensic statistics** — 19 data-integrity checks (GRIM, GRIMMER, SPRITE, correlation bounds, p-value recalculation, Carlisle test, and more) based on Heathers (2025) [*An Introduction to Forensic Metascience*](https://jamesheathers.curve.space/)
- **Critical read** — author profiling, method-resolution mismatch detection, overclaiming analysis
- **Bibliography pipeline** — citation extraction, DOI resolution, retraction detection, literature discovery
- **Systematic literature reviews** — JBI / PRISMA-ScR rails (harvest → screen → extract → validate → synthesise) for scoping reviews where **your AI assistant is the screening/extraction engine**. There is no bundled classifier: `screen` and `extract` are SDK-agnostic seams (interface + abstaining stub) designed to be driven by the assistant you already use — Claude Code, Codex — through the CLI and JSONL contracts; the pipeline supplies the rails, the append-only audit trail, the human-adjudication queue, and a static-HTML review site. Reviews are protocol-as-data: one YAML defines PCC, search query blocks, screening rubric, charting schema, and aggregation rules. The `validate` step turns AI screening/extraction decisions into a human work queue (the model self-flags its low-confidence calls; the human adjudicates only those; flips reconcile back append-only) — see [`docs/validate.md`](docs/validate.md). See also [`paperscope/systematic_review/`](paperscope/systematic_review/) and [`docs/systematic-review.md`](docs/systematic-review.md).
- **Review knowledge bases** — emerging tooling for turning large review corpora into paper cards, cluster pages, quality flags, private source-object links, and public summaries. See [`docs/corpus-knowledge-base.md`](docs/corpus-knowledge-base.md).

## Scaling to Large Reviews

PaperScope is built for large review corpora: thousands of records, working evidence bases of well over a thousand papers, AI-assisted charting, paper-card generation, quality flags, rich metadata, dual-rater comparison, and a searchable collaborator portal. Discipline-specific rubrics, claims, and synthesis outputs stay in the caller project; the generic machinery is pulled back into PaperScope.

For large reviews the useful product is not just "screen and aggregate" but a corpus knowledge base that lets a reader ask questions such as:

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

Heavier optional dependencies ship commented out in `requirements.txt` — e.g. `playwright` (only needed for `systematic_review browser-harvest`) and `pyarrow` (methodological-audit clustering). Uncomment what you use.

For better embeddings (optional but recommended):
```bash
pip install sentence-transformers
```

Without `sentence-transformers`, embedding-based tools fall back to TF-IDF (which requires `scikit-learn`, included in requirements).

### Integration with AI coding assistants

PaperScope works as a CLI that any AI assistant can call. Two tested workflows:

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

### Annotate a paper (teaching / referee markup)

```bash
# Build an annotated reading copy from a notes spec (JSON or YAML)
python3 -m paperscope annotate paper.pdf notes.json -o annotated.pdf
```

Turns a PDF + a list of notes — each pinning an `anchor` phrase on a page to a colour-coded `header` + `body` (TEACH / DEF / STRENGTH / CRIT) — into a reading copy with highlighted, numbered passages, interleaved "annotator's notes" commentary pages, a colour-key front page, and an optional one-screen summary + figure appendix. Substrate-free: all paper-specific content lives in the spec, so the same tool builds a teaching copy, a referee's markup, or a collaborator's. Anchors that don't bind are reported (the note is still emitted, badge-only). Spec format and a programmatic API (`build_annotated_pdf`) are documented in `paperscope/analysis/annotate.py`; see `examples/annotate/`.

### Forensic statistics (data integrity)

```python
# Import individual checks in Python
from paperscope.analysis.forensic_stats import grim, grim_percentage, correlation_bound
print(grim(mean="18.72", n=22))                       # GRIM test (fails at 2dp)
print(grim_percentage(percentage=53.2, n=25, dp=1))   # GRIM applied to percentages
print(correlation_bound(0.10, 0.30, 0.05))            # impossible r (|r| > 1)
```

The forensic module is a Python library, not a CLI command. You transcribe summary statistics from a paper's tables and feed them to the functions. The checks are automated; the data entry is manual.

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

### Native paper sites

```bash
python3 -m paperscope paper-site ./site \
  --title "Bayesian Descriptions Are Not Mechanisms"
```

Scaffolds a paper-library-backed Next.js paper reader with the shared MD3 visual
contract used across the author's paper sites: native web manuscript first,
downloadable PDFs second, inline citation/detail controls, side-panel reference
context, and paper-library source status. Reference records can carry
`role`/`what`/`why`/`caution`/`contexts` fields so the sidebar teaches the
reader what each source is doing instead of dumping raw citation snippets. When
those fields are absent, the scaffold falls back to conservative academic and
clinical source-type explanations. Sidebar prose resolves citation markers, cite
keys, and author-year labels back into the same reference panel; optional
`native_href` and `source_href` fields add panel actions without making citation
clicks launch a new tab directly.
LocalEvidence calls the same generator in medical mode rather than maintaining a
separate paper-reader fork.

### Permanent library (frequent users)

`ingest` writes into a transient per-project `literature/` folder and re-fetches
every project. If you use paperscope across many papers and reviews, stand up a
**permanent, machine-wide paper library** instead: one deduped catalog (by
DOI/MD5/PMID) with standing semantic search and a snapshot/restore safety net,
sitting on top of paperscope's acquisition and embeddings. A paper enters once and
is never re-fetched. See [`docs/permanent-library.md`](docs/permanent-library.md)
for the pattern and [`examples/permanent-library/`](examples/permanent-library/) for
a copy-and-adapt reference skeleton.

```bash
cp -r examples/permanent-library ~/paper-library && cd ~/paper-library
export PAPERSCOPE_HOME=/path/to/paperscope
python3 library.py pull 10.1016/j.biosystems.2025.105608 --title "..."
python3 library.py search "active inference free energy" -k 10
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
| `grim_percentage()` | Impossible percentages from discrete counts (GRIM applied to percentages; `debit()` remains as a deprecated alias) |
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

The [paper (PDF)](paper/paperscope.pdf) (March 2026) describes the embedding-analysis core; the forensic-statistics and systematic-review modules postdate it. For those, Heathers (2025) is the forensic reference and [`docs/systematic-review.md`](docs/systematic-review.md) is the design document.

## Examples

See [`examples/annotate/`](examples/annotate/) for a worked annotation spec and [`examples/permanent-library/`](examples/permanent-library/) for a reference paper-library integration.

## Development Workflow

PaperScope is developed using a multi-model feedback loop:

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
