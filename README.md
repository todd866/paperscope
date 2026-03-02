# Paperscope

**Embedding-powered analysis tools for academic papers. Built for use with [Claude Code](https://claude.ai/claude-code) and [Codex](https://openai.com/codex).**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## What This Does

Paperscope manages the full lifecycle of academic paper writing:

1. **Bibliography management** -- extract citations from LaTeX, resolve DOIs, verify references
2. **Literature ingestion** -- discover papers from OpenAlex/arXiv/bioRxiv, download PDFs, extract text
3. **Embedding analysis** -- semantic analysis of your paper against its literature corpus

The embedding layer is the main event. It answers questions like:
- Do your citations actually support what you claim they support?
- Which claims are most novel (furthest from existing literature)?
- What would a reviewer likely object to, and where's your evidence?
- Is your abstract covering all major sections?
- Which journals are the best semantic fit for this paper?
- What related work might you be missing?

## Quick Start

```bash
git clone https://github.com/todd866/paperscope.git
cd paperscope
pip install -r requirements.txt

# Set your email for API polite pools (CrossRef, OpenAlex, Unpaywall)
export PAPERSCOPE_EMAIL="you@university.edu"
```

### Run analysis on a paper

```bash
# Full analysis suite: citation alignment, novelty, strength heatmap
python3 -m paperscope analyze paper.tex --literature literature/text/

# Check if your abstract covers all sections
python3 -m paperscope abstract-check paper.tex

# Rank journals by semantic fit
python3 -m paperscope journal-fit paper.tex -j "BioSystems" "Biological Cybernetics" "PLOS ONE"

# Semantic diff between revisions
python3 -m paperscope revision-diff old_version.tex new_version.tex

# Find missing related work via OpenAlex
python3 -m paperscope related paper.tex

# Cross-paper argument dependency graph
python3 -m paperscope argument-graph /path/to/research/program/
```

### Bibliography pipeline

```bash
# Extract citations from LaTeX
python3 -m paperscope extract /path/to/paper/

# Resolve missing DOIs
python3 -m paperscope resolve bibliography.json

# Verify DOIs against CrossRef metadata
python3 -m paperscope verify bibliography.json

# Discover new papers
python3 -m paperscope harvest --config config.yaml

# Download open-access PDFs and extract text
python3 -m paperscope ingest /path/to/literature/
```

## Using with Claude Code

Paperscope is designed to work alongside AI coding assistants. The typical workflow:

1. **You write the paper** (with AI assistance)
2. **Run `analyze`** to check citation alignment, novelty, and argument strength
3. **Run `abstract-check`** before submission to ensure coverage
4. **Run `journal-fit`** to choose where to submit
5. **After revision, run `revision-diff`** to verify changes addressed reviewer concerns

Claude Code or Codex can interpret the JSON output, suggest fixes, and iterate. The tools produce structured data that AI assistants can reason about.

## Commands

### Analysis (embedding-powered)

| Command | What it does |
|---------|-------------|
| `analyze` | Full analysis suite: citation alignment, novelty detection, strength heatmap |
| `abstract-check` | Check if abstract covers all major sections |
| `journal-fit` | Rank journals by semantic similarity to your paper |
| `revision-diff` | Semantic diff between two versions of a paper |
| `related` | Find potentially missing related work via OpenAlex |
| `argument-graph` | Build cross-paper dependency graph for a research program |

### Bibliography

| Command | What it does |
|---------|-------------|
| `extract` | Extract citations from a LaTeX project tree |
| `resolve` | Resolve missing DOIs via CrossRef |
| `verify` | Verify DOIs against CrossRef metadata |
| `pre-submit` | Pre-submission citation check |

### Literature

| Command | What it does |
|---------|-------------|
| `harvest` | Discover new papers (OpenAlex, arXiv, bioRxiv) |
| `ingest` | Download open-access PDFs and extract text |
| `depth2` | Harvest depth-2 references (references of references) |
| `status` | Show pipeline status |

## Architecture

Three layers, each usable independently:

```
paperscope/
├── text/          # Shared text processing (LaTeX cleaning, chunking, parsing)
├── embed/         # Embedding infrastructure (sentence-transformers + TF-IDF fallback)
├── analysis/      # 12 analysis tools (citation alignment, novelty, reviewer probes, ...)
├── bib/           # Bibliography management (extract, resolve, verify)
├── harvest/       # Paper discovery (OpenAlex, arXiv, bioRxiv)
├── ingest/        # PDF acquisition + text extraction
└── read/          # Structured reading prompts
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full system design.

## How the Analysis Works

The core insight: **embed your paper and its literature into the same vector space, then measure distances.**

1. **Text processing** -- LaTeX is cleaned to plain text, split into ~200-word chunks
2. **Embedding** -- Chunks are encoded using `sentence-transformers` (all-MiniLM-L6-v2, 384 dimensions). Falls back to TF-IDF if the model isn't installed.
3. **Similarity** -- Cosine similarity matrices reveal which parts of your paper are close to which parts of the literature

This enables:
- **Citation alignment**: For each sentence with a `\cite{}`, are the cited papers actually the closest matches?
- **Novelty detection**: Claims with low max similarity to any literature are flagged as novel
- **Strength heatmap**: Per-paragraph scores showing citation support and argument continuity
- **Reviewer probes**: Embed hypothetical reviewer questions, find the best literature to respond with
- **Self-overlap**: Detect high-similarity passages with your other papers (before reviewers do)
- **Abstract coverage**: Embed each section and the abstract, check the coverage matrix

## Configuration

Copy `config.yaml` and customize:

```yaml
research_profile:
  keywords:
    - "your research topic"
  authors:
    - "Researchers you track"
  arxiv_categories:
    - "relevant.category"
```

Set your email for API rate-limit courtesy:

```bash
export PAPERSCOPE_EMAIL="you@university.edu"
```

## Requirements

- Python 3.8+
- `numpy` -- array operations
- `requests` -- API calls (CrossRef, OpenAlex, Unpaywall)
- `sentence-transformers` -- text embedding (optional: TF-IDF fallback available)
- `PyMuPDF` -- PDF text extraction
- `pyyaml`, `pydantic`, `httpx` -- configuration and HTTP

Optional:
- `matplotlib` -- visualizations (argument flow, strength heatmap)
- `scikit-learn` -- PCA for visualizations, TF-IDF fallback
- `networkx` -- argument graph visualization

## Origin

This toolchain was built for [Coherence Dynamics](https://coherencedynamics.com), a research program producing 30+ papers across neuroscience, biology, physics, and mathematics. It manages ~1,500 references across 175 .tex files.

## Citation

```bibtex
@software{todd2026paperscope,
  author = {Todd, Ian},
  title = {Paperscope: Embedding-Powered Analysis Tools for Academic Papers},
  year = {2026},
  url = {https://github.com/todd866/paperscope}
}
```

## License

MIT -- see [LICENSE](LICENSE).
