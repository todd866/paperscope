# Paperscope — Claude Code Instructions

## What This Is

Paperscope is a Python toolkit for embedding-powered analysis of academic papers. It manages citations, discovers literature, and runs semantic analysis to catch citation issues, detect novelty, and prepare for peer review.

## Quick Commands

### Analysis (the main tools)

```bash
# Full analysis suite on a paper
python3 -m paperscope analyze paper.tex --literature literature/text/

# Check abstract coverage
python3 -m paperscope abstract-check paper.tex

# Rank journals by semantic fit
python3 -m paperscope journal-fit paper.tex -j "Journal Name 1" "Journal Name 2"

# Semantic diff between revisions
python3 -m paperscope revision-diff old.tex new.tex --literature literature/text/

# Find missing related work
python3 -m paperscope related paper.tex

# Cross-paper argument graph
python3 -m paperscope argument-graph /path/to/research/program/
```

### Critical read (external papers)

```bash
# Critical read of an external paper (PDF)
python3 -m paperscope critical-read paper.pdf

# With explicit method and resolution hints
python3 -m paperscope critical-read paper.pdf --methods RELAX --question-resolution site_specific

# With author names (skips auto-extraction)
python3 -m paperscope critical-read paper.pdf --authors "Alice Smith" "Bob Jones"

# Offline mode (skip OpenAlex author lookup)
python3 -m paperscope critical-read paper.pdf --skip-author-lookup
```

Runs four analyses: author/COI profiling, method-resolution mismatch detection, missing complementary methods, and overclaiming detection. Outputs structured JSON + console summary.

### Bibliography pipeline

```bash
# Extract citations from LaTeX
python3 -m paperscope extract /path/to/paper/

# Resolve missing DOIs
python3 -m paperscope resolve bibliography.json

# Verify DOIs against CrossRef
python3 -m paperscope verify bibliography.json

# Discover new papers
python3 -m paperscope harvest --config config.yaml

# Pre-submission citation check
python3 -m paperscope pre-submit paper.tex --bib bibliography.json

# Download open-access PDFs + extract text
python3 -m paperscope ingest /path/to/literature/

# Depth-2 reference harvesting
python3 -m paperscope depth2 /path/to/literature/
```

## Architecture

```
paperscope/
├── text/       # Shared text processing (LaTeX cleaning, chunking, parsing)
├── embed/      # Embedding infrastructure (sentence-transformers + TF-IDF fallback)
├── analysis/   # 17 analysis tools
│   ├── citation_alignment.py    # Do citations match the citing sentence?
│   ├── novelty.py               # Which claims are furthest from literature?
│   ├── reviewer_probes.py       # Anticipate reviewer objections
│   ├── self_overlap.py          # Detect overlap with your other papers
│   ├── argument_flow.py         # Track argument trajectory, detect jumps/loops
│   ├── cross_paper.py           # Check consistency across papers
│   ├── abstract_alignment.py    # Does the abstract cover all sections?
│   ├── journal_targeting.py     # Which journal fits best? (via OpenAlex)
│   ├── strength_heatmap.py      # Per-paragraph citation support strength
│   ├── revision_diff.py         # Semantic diff between revisions
│   ├── argument_graph.py        # Cross-paper dependency graph
│   ├── related_radar.py         # Find missing related work (via OpenAlex)
│   ├── critical_read.py         # Orchestrator for external paper critique
│   ├── author_profile.py       # Author COI and self-validation detection
│   ├── method_resolution.py    # Method-conclusion resolution mismatch
│   ├── missing_methods.py      # Complementary methods from same ecosystem
│   ├── overclaiming.py         # Hedge erosion and scope expansion
│   └── forensic_stats.py       # GRIM, DEBIT, SPRITE, correlation bounds,
│                                # p-value recalc, Benford's, variance ratios
├── bib/        # Bibliography management (extract, resolve, verify)
├── harvest/    # Paper discovery (OpenAlex, arXiv, bioRxiv)
├── ingest/     # PDF acquisition + text extraction
└── read/       # Structured reading prompts
```

## Key Design Decisions

- **TF-IDF fallback**: If sentence-transformers isn't installed, embedding functions fall back to TF-IDF. This lets the tools run anywhere.
- **Lazy imports**: CLI subcommands import modules lazily, keeping startup fast.
- **JSON output**: All analysis commands write structured JSON alongside human-readable console output.
- **No API keys required**: CrossRef, OpenAlex, and Unpaywall use polite-pool email headers, not API keys. Set `PAPERSCOPE_EMAIL` env var.

## Per-Paper Library Structure

```
paper_folder/literature/
├── bibliography.json          # Extracted refs with DOIs
├── pdfs/                      # cite_key.pdf files
└── text/                      # Extracted plain text (cite_key.txt)
```

## Development

```bash
pip install -r requirements.txt
python3 -m paperscope <command> [args]
```

The `text/` and `embed/` modules are the shared library. The `analysis/` module contains all 12 tools. Each tool is a standalone module with a main function that takes embeddings and returns structured results.

### Bug fix workflow

When a bug is reported, don't start by trying to fix it. Write a test that reproduces the bug first. Then fix the bug and prove it with a passing test. Use subagents for the fix attempt when the bug is non-trivial.

## API Dependencies

| API | Auth | Used by |
|-----|------|---------|
| CrossRef | mailto header | `bib/resolve.py`, `bib/verify.py`, `bib/depth2.py` |
| OpenAlex | email param | `harvest/`, `analysis/journal_targeting.py`, `analysis/related_radar.py` |
| Unpaywall | email param | `ingest/open_access.py` |
| Backblaze B2 | API key (env vars) | `ingest/cloud_store.py` |

All APIs are used in their free tiers with polite rate limiting.
