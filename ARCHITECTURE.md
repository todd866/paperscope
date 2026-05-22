# Architecture

## System Overview

Paperscope is five layers:

1. **Bibliography** — citation extraction, DOI resolution, retraction detection
2. **Harvest + Ingest** — paper discovery, OA acquisition, text extraction
3. **Embed + Analysis** — claim/text embedding and the analysis suite that runs on top
4. **Systematic Reviews** — JBI/PRISMA-ScR pipeline for AI-accelerated scoping reviews
5. **Corpus Knowledge Bases** — paper cards, clusters, quality flags, source manifests, and review portals

These layers are deliberately connected. Single-paper commands are not a separate product from corpus review commands: they are local queries against the same literature map. Citation alignment, novelty, critical reading, and forensic flags become more meaningful when the surrounding corpus has been harvested, embedded, charted, and made navigable.

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
│  arXiv    ─┼──→ discover ──→ digest.md + DOIs                       │
│  bioRxiv  ─┘         │                                              │
│                      ▼                                              │
│              Unpaywall ──→ OA PDFs ──→ B2 cloud (optional)          │
│                      │       │                                      │
│              EZProxy queue   │                                      │
│              (paywalled)     ▼                                      │
│                       PyMuPDF ──→ extracted text ──→ git            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      EMBED + ANALYSIS LAYER                         │
│                                                                     │
│  extracted text  ──→ text/  (LaTeX cleaning, chunking)              │
│                       │                                             │
│                       ▼                                             │
│                  embed/  (sentence-transformers + TF-IDF fallback)  │
│                       │                                             │
│                       ▼                                             │
│                 analysis/  (15 modules: citation alignment,         │
│                  novelty, journal fit, critical read, forensic …)   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    SYSTEMATIC REVIEW LAYER                          │
│                                                                     │
│  YAML config ──→ search/medline ──→ records.jsonl                   │
│                      │                                              │
│  Ovid/EBSCO exports ─┘                                              │
│                                                                     │
│  records.jsonl ──→ screen/ (AI + audit) ──→ screening.jsonl         │
│  included.jsonl ──→ extract/ (AI + audit) ──→ extraction.jsonl      │
│                                                                     │
│  acquire/ ──→ OA PDFs + EZProxy queue + coverage report             │
│                                                                     │
│  synthesise/ ──→ synthesis-tables.json + prisma-flow.json           │
│  ui/ ──→ static HTML review site (Covidence-style record pages)     │
└─────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CORPUS KNOWLEDGE-BASE LAYER                      │
│                                                                     │
│  extraction.jsonl + text/ ──→ rich metadata ──→ paper-cards.jsonl   │
│                                                                     │
│  embeddings / caller taxonomy ──→ clusters.json + cluster pages     │
│                                                                     │
│  PDF/text cache ──→ source-manifest.jsonl ──→ private object store  │
│                                                                     │
│  rater outputs ──→ field-level disagreement reports                 │
│                                                                     │
│  export/ ──→ static site or app-ready knowledge-base package        │
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
5. **Depth-2** (`bib/depth2.py`): Optional — for each DOI in bibliography.json, query CrossRef for its `reference` field; add new references as depth-2 entries. Captures the extended intellectual neighborhood (~10–15k refs typically).

### Phase 2: Harvest + Ingest (implemented)

```
Input:  Research profile (keywords, authors, categories) OR a list of DOIs
Output: digest.md + downloaded PDFs + extracted text
```

1. **Discover** (`harvest/`): Queries OpenAlex, arXiv, bioRxiv for papers matching the research profile. Deduplicates, filters unseen papers, generates a markdown digest.
2. **Acquire** (`ingest/open_access.py`): For each DOI, asks Unpaywall for every candidate OA URL and tries them in priority order until one yields a PDF. Uses a browser-like User-Agent + `https://doi.org/{doi}` Referer to defeat publisher bot blocks. Magic-byte verifies every download.
3. **Extract** (`ingest/extract_text.py`): Uses PyMuPDF to pull plain text from PDFs. Outputs `.txt` files suitable for LLM consumption.
4. **Store** (`ingest/cloud_store.py`, optional): Uploads PDFs to Backblaze B2. Maintains `pdf_manifest.json` tracking what's stored. Text stays in git; PDFs stay in cloud.
5. **EZProxy queue** (`ingest/browser_queue.py`): For paywalled papers, generates `https://doi-org.<ezproxy_host>/<doi>` URLs that whatever browser-automation you use can walk through institutional auth.

> **Acquisition hardening:** shadow-library and Sci-Hub paths silently return the *wrong* paper often enough to poison a corpus. See `docs/acquisition-lessons.md` for the observed failure modes (SciDB collisions, unguarded Sci-Hub, scanned/watermark-only PDFs) and the verification-gated cascade to port from the reference implementation in `~/PaperLibrary/library.py`.

### Phase 3: Embed + Analysis (implemented)

```
Input:  Extracted text from papers + a literature corpus
Output: Structured JSON analysis per command + console summary
```

1. **Text Processing** (`text/`): LaTeX cleaning, paragraph chunking, citation-context extraction. Shared utilities used by all analysis tools.
2. **Embed** (`embed/`): Encodes text as vectors using sentence-transformers (all-MiniLM-L6-v2, 384-dim). Falls back to TF-IDF if the model isn't installed.
3. **Analysis** (`analysis/`), 15 modules in three groups. These modules can run on one manuscript or one external paper, but their strongest form uses a corpus as context:

   *Embedding-powered (your own papers)*
   - `citation_alignment` — do cited references match the citing sentence?
   - `novelty` — which claims are furthest from existing literature?
   - `reviewer_probes` — anticipate reviewer objections, map to evidence
   - `abstract_alignment` — does the abstract cover all major sections?
   - `journal_targeting` — rank journals by semantic fit (via OpenAlex)
   - `strength_heatmap` — per-paragraph citation support and continuity
   - `revision_diff` — semantic diff between paper revisions
   - `argument_graph` — cross-paper dependency graph
   - `related_radar` — find missing related work (via OpenAlex)

   *Critical read (external papers)*
   - `critical_read` — orchestrator combining the four checks below
   - `author_profile` — author COI and self-validation detection
   - `method_resolution` — method/conclusion resolution mismatch
   - `missing_methods` — complementary methods from same ecosystem
   - `overclaiming` — hedge erosion and scope expansion

   *Forensic statistics (data integrity)*
   - `forensic_stats` — 19 checks based on Heathers (2025): GRIM, GRIMMER, DEBIT, SPRITE, correlation bounds, t-test/ANOVA/chi-squared recalculation, Carlisle-Stouffer-Fisher, SD/SE confusion, Benford's law, variance ratios, effect size consistency, and more.

### Phase 4: Systematic Reviews (implemented)

```
Input:  A review YAML (PCC, query blocks, rubric path, schema path, aggregation config)
Output: records.jsonl, screening.jsonl, extraction.jsonl,
        synthesis-tables.json, prisma-flow.json, static HTML review site
```

`paperscope/systematic_review/` is a generalised JBI/PRISMA-ScR pipeline for AI-accelerated scoping reviews. Reviews are protocol-as-data: a single YAML defines the question, search strategy, screening rubric, charting schema, and aggregation rules; the same code serves any review.

1. **Search** (`search/`): MEDLINE via E-utilities is fully automated; Ovid (Embase) and EBSCO (CINAHL) ingest external RIS exports.
2. **Screen** (`screen/`): Markdown rubric loader + SDK-agnostic AI-screen interface. The reviewer is an AI agent (or several in parallel) executing the rubric; the human audits a sample and resolves "maybe"s.
3. **Extract** (`extract/`): Charting schema loader + SDK-agnostic AI-extract interface. Same two-stage shape as screening.
4. **Acquire** (`acquire/`): For the included set, pulls OA PDFs via `ingest/open_access`, writes an EZProxy queue for the paywalled tail, and can optionally walk that tail through a Playwright browser driver using an authenticated local profile. Paywalled access remains an operator-controlled boundary because institutional authentication and licensing constraints vary by deployment.
5. **Synthesise** (`synthesise/`): Declarative aggregator (`aggregate.py`) + PRISMA-ScR flow (`prisma.py`) + cross-database dedup. Regression-verified against a working MND review.
6. **UI** (`ui/`): Static HTML review site with Covidence-style record pages. No JS dependency — publishable as a `gh-pages` artefact.

See `docs/systematic-review.md` for the design + roadmap and `paperscope/systematic_review/README.md` for the quickstart.

### Phase 5: Corpus Knowledge Bases (roadmap)

```
Input:  Review outputs + extracted text + source manifests + optional rater outputs
Output: paper-cards.jsonl, clusters.json, source-manifest.jsonl,
        disagreement reports, static/app-ready knowledge-base package
```

The knowledge-base layer is the natural product for large reviews and the missing context for serious single-paper evaluation. A user should be able to browse a corpus by paper, claim, cluster, evidence quality, source availability, and rater disagreement without reading raw JSONL. A paper card is therefore not just a summary of one paper; it is a node in the corpus map.

Planned modules:

1. **Paper cards**: Stable per-paper summaries with relevance, methods, populations, limitations, and claim links.
2. **Source manifests**: Provider-neutral object metadata for PDFs and extracted text, with checksums and public/private access flags.
3. **Cluster maps**: Embedding- or caller-supplied clusters, representative papers, and cluster-level summaries.
4. **Rater comparison**: Field-level agreement/disagreement across AI and human rater families.
5. **Export**: Static HTML and app-ready JSON packages for richer review portals.

See `docs/corpus-knowledge-base.md` for the detailed roadmap.

## Storage Strategy

| Data type | Storage | Why |
|-----------|---------|-----|
| `bibliography.json` | Git | Small (~2MB), needs versioning |
| Extracted text (`.txt`) | Git | Small per paper, Claude-readable |
| Claim embeddings (`.npy`) | Git | ~50MB for 10k claims, acceptable |
| PDFs | S3-compatible object store, Backblaze B2, or local | Large (~5GB for 1000 papers), not text |
| `pdf_manifest.json` / `source-manifest.jsonl` | Git | Tracks source objects, checksums, access status |
| SR `records.jsonl` / `screening.jsonl` / `extraction.jsonl` | Per-review corpus dir | One JSON object per line; git-diff-friendly |
| Paper cards / clusters / quality flags | Per-review export dir | Small enough for git; useful public review surface |

PDFs are binary blobs that don't diff well and bloat the repo. Object storage or a local cache keeps them out of git. Text, metadata, paper cards, and many embeddings are small enough that git handles them fine.

## Configuration

The harvest module uses a YAML research profile:

```yaml
research_profile:
  keywords:
    - intrinsic dimensionality
    - information geometry
    - neural manifold
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

The systematic_review module uses a different YAML format (PCC + query_blocks + aggregation). See `paperscope/systematic_review/examples/mnd-pilot.yaml` for a worked example.

## API Dependencies

| API | Rate limit | Auth | Used by |
|-----|-----------|------|---------|
| CrossRef | 50 req/s (polite pool) | mailto header | `bib/resolve.py`, `bib/verify.py`, `bib/depth2.py` |
| OpenAlex | 10 req/s (polite pool) | email param | `harvest/sources/openalex.py`, `analysis/journal_targeting.py`, `analysis/related_radar.py` |
| arXiv | 1 req/3s | None | `harvest/sources/arxiv.py` |
| bioRxiv | ~1 req/s | None | `harvest/sources/biorxiv.py` |
| Unpaywall | 100k/day | email param (`PAPERSCOPE_EMAIL`) | `ingest/open_access.py` |
| NCBI E-utilities (PubMed) | 3 req/s anonymous | None | `systematic_review/search/medline.py` |
| Backblaze B2 | Generous | API key (`B2_APPLICATION_KEY*`) | `ingest/cloud_store.py` (optional) |

All APIs are used in their free tiers with polite rate limiting. `PAPERSCOPE_EMAIL` must be set to a real address — Unpaywall rejects the polite-pool with an empty/placeholder email.
