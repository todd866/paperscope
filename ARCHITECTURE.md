# Architecture

## System Overview

Paperscope is a pipeline with three layers: bibliography management, literature ingestion, and semantic analysis.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        BIBLIOGRAPHY LAYER                           │
│                                                                     │
│  .tex/.bib files ──→ extract.py ──→ bibliography.json               │
│                                          │                          │
│                                    resolve.py ──→ DOIs added        │
│                                          │                          │
│                                    verify.py ──→ metadata checked   │
│                                          │                          │
│                                    pre_submit.py ──→ ready?         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      HARVEST + INGEST LAYER                         │
│                                                                     │
│  OpenAlex ─┐                                                        │
│  arXiv    ─┼──→ discover ──→ digest.md + PDFs                       │
│  bioRxiv  ─┘         │                                              │
│                      ▼                                              │
│              Unpaywall ──→ OA PDFs ──→ B2 cloud storage             │
│                                │                                    │
│                          PyMuPDF ──→ extracted text ──→ git         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      READ + EMBED LAYER                             │
│                                                                     │
│  text ──→ read_paper.py ──→ structured summary (claims, methods)    │
│                                    │                                │
│                             embed_claims.py ──→ claim vectors       │
│                                    │                                │
│                             query.py ──→ neighbors, conflicts, gaps │
│                                    │                                │
│                             audit_usage.py ──→ citation audit       │
└─────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Phase 1: Bibliography (implemented)

```
Input:  Any LaTeX project tree (*.tex + *.bib files)
Output: bibliography.json — structured, deduplicated, DOI-resolved
```

1. **Extract** (`bib/extract.py`): Walks a directory tree, parses both `\bibitem{}` blocks and `.bib` files, deduplicates by cite key and fuzzy title match.

2. **Resolve** (`bib/resolve.py`): For each reference without a DOI, queries CrossRef API. Confidence scoring (title similarity + year match). Only accepts matches above 0.80 threshold.

3. **Verify** (`bib/verify.py`): Cross-checks resolved DOIs against CrossRef metadata. Detects title mismatches, year discrepancies, retracted papers.

4. **Pre-submit** (`bib/pre_submit.py`): Pre-submission checklist. Checks DOI coverage, broken references, duplicate citations, missing fields.

### Phase 2: Harvest + Ingest (harvest implemented, ingest in progress)

```
Input:  Research profile (keywords, authors, categories)
Output: digest.md + downloaded PDFs + extracted text
```

1. **Discover** (`harvest/`): Queries OpenAlex, arXiv, bioRxiv for papers matching the research profile. Deduplicates, filters unseen papers, generates markdown digest.

2. **Acquire** (`ingest/open_access.py`): For each DOI, checks Unpaywall for open-access PDF URLs. Downloads OA papers. Generates EZProxy queue for paywalled papers.

3. **Extract** (`ingest/extract_text.py`): Uses PyMuPDF to extract text from PDFs. Outputs clean `.txt` files suitable for LLM consumption.

4. **Store** (`ingest/cloud_store.py`): Uploads PDFs to Backblaze B2. Maintains `pdf_manifest.json` tracking what's stored. Text stays in git; PDFs stay in cloud.

### Phase 3: Read + Embed + Analyze (implemented)

```
Input:  Extracted text from papers + literature corpus
Output: Structured analysis (citation alignment, novelty, reviewer prep, etc.)
```

1. **Text Processing** (`text/`): LaTeX cleaning, text chunking, citation context extraction. Shared utilities used by all analysis tools.

2. **Embed** (`embed/`): Encodes text as vectors using sentence-transformers (all-MiniLM-L6-v2, 384-dim). Falls back to TF-IDF if model unavailable. Includes cosine similarity, batch encoding, and caching.

3. **Analysis** (`analysis/`): 18 modules in three groups:

   *Embedding-powered (your own papers):*
   - `citation_alignment` — Do cited references match the citing sentence?
   - `novelty` — Which claims are furthest from existing literature?
   - `reviewer_probes` — Anticipate objections, map to evidence
   - `self_overlap` — Detect high-similarity passages with your other papers
   - `argument_flow` — Track argument trajectory, detect jumps and loops
   - `cross_paper` — Check consistency across your paper program
   - `abstract_alignment` — Does the abstract cover all major sections?
   - `journal_targeting` — Rank journals by semantic fit (via OpenAlex)
   - `strength_heatmap` — Per-paragraph citation support and continuity
   - `revision_diff` — Semantic diff between paper revisions
   - `argument_graph` — Cross-paper dependency graph
   - `related_radar` — Find missing related work (via OpenAlex)

   *Critical read (external papers):*
   - `critical_read` — Orchestrator combining the four checks below
   - `author_profile` — Author COI and self-validation detection
   - `method_resolution` — Method-conclusion resolution mismatch
   - `missing_methods` — Complementary methods from same ecosystem
   - `overclaiming` — Hedge erosion and scope expansion

   *Forensic statistics (data integrity):*
   - `forensic_stats` — 19 checks based on Heathers (2025): GRIM, GRIMMER, DEBIT, SPRITE, correlation bounds, t-test/ANOVA/chi-squared recalculation, Carlisle-Stouffer-Fisher, SD/SE confusion, Benford's law, variance ratios, effect size consistency, and more

4. **Read** (`read/`): Structured reading prompt generation for LLM-based paper analysis.

5. **Query** (`embed/query.py`): Nearest-neighbor search over claim vectors. Detects similar claims, contradictions, gaps.

## Storage Strategy

| Data type | Storage | Why |
|-----------|---------|-----|
| `bibliography.json` | Git | Small (~2MB), needs versioning |
| Extracted text (`.txt`) | Git | Small per paper, Claude-readable |
| Structured readings (`.json`) | Git | Small, needs versioning |
| Claim embeddings (`.npy`) | Git | ~50MB for 10k claims, acceptable |
| PDFs | Backblaze B2 | Large (~5GB for 1000 papers), not text |
| `pdf_manifest.json` | Git | Tracks what's in B2 |

### Why Not All in Git?

PDFs are binary blobs that don't diff well and bloat the repo. A research library of 1000+ papers would make the repo unusable. B2 costs $0.005/GB/month — effectively free for academic scale.

### Why Not All in Cloud?

Text, metadata, and embeddings should be version-controlled and accessible without network access. They're small enough that git handles them fine.

## Depth-2 Harvesting

The bibliography database enables a specific strategy: **depth-2 reference harvesting**.

```
Your papers (depth 0)
  └── Their references (depth 1) ← bibliography.json has these
        └── References of references (depth 2) ← harvested via CrossRef
```

For each reference with a DOI:
1. Query CrossRef `works/{doi}` for its `reference` field
2. Add new references to the bibliography as depth-2
3. Resolve DOIs for depth-2 references
4. Acquire and extract depth-2 papers

Expected scale: ~10,000-15,000 additional references at depth 2. This captures the extended intellectual neighborhood of the research program.

## Configuration

The harvest module uses a YAML research profile:

```yaml
research_profile:
  keywords:
    - intrinsic dimensionality
    - information geometry
    - neural manifold
    - participation ratio
    # ...

  authors:
    - Igamberdiev
    - Friston
    - Tononi
    # ...

  arxiv_categories:
    - q-bio.NC
    - cond-mat.stat-mech
    - cs.IT
```

## API Dependencies

| API | Rate limit | Auth | Used by |
|-----|-----------|------|---------|
| CrossRef | 50 req/s (polite pool) | mailto header | `resolve.py`, `verify.py` |
| OpenAlex | 10 req/s (polite pool) | email param | `harvest/sources/openalex.py` |
| arXiv | 1 req/3s | None | `harvest/sources/arxiv.py` |
| bioRxiv | ~1 req/s | None | `harvest/sources/biorxiv.py` |
| Unpaywall | 100k/day | email param | `ingest/open_access.py` |
| Backblaze B2 | Generous | API key | `ingest/cloud_store.py` |

All APIs are used in their free tiers with polite rate limiting.
