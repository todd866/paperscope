# `paperscope.systematic_review`

A generalised, AI-agent-native pipeline for JBI / PRISMA-ScR scoping reviews.

Extracted from a working scoping-review pipeline (May 2026) and generalised
so the same code serves any review whose protocol — PCC question, screening
rubric, charting schema, and aggregation rules — is supplied as data.

## Why this exists

Covidence and EndNote are good for **human** reviewers clicking through
records one by one. They're awkward for AI-accelerated screening, where the
"reviewer" is one or more agents working in parallel against a written rubric
and you need a clean structured layer + a human audit interface, not a UI.

This module is that layer:

- **Pipeline**: harvest → screen → extract → synthesise, all JSONL-based,
  fully reproducible, every decision logged with its reason.
- **Protocol-as-data**: a single YAML defines the review (PCC, search query
  blocks, rubric path, schema path, aggregation rules). Nothing about a
  particular review is hardcoded.
- **Human audit baked in**: AI agents do bulk screening; the static HTML
  review site renders the state for spot-check, override, and the "see this
  GitHub page" method artefact every reviewer asks for.

## Pipeline at a glance

```
                     ┌──────────────────────────┐
  records.jsonl ◄────┤  search/                 │
   (per database)    │    medline / ovid / cinahl
                     └──────────┬───────────────┘
                                ▼
                     ┌──────────────────────────┐
                     │  synthesise.dedup        │  cross-db: PMID → DOI → title
                     └──────────┬───────────────┘
                                ▼
                     ┌──────────────────────────┐
 screening.jsonl ◄───┤  screen/  (agent + audit)│  rubric → decision + reason
                     └──────────┬───────────────┘
                                ▼
                     ┌──────────────────────────┐
 extraction.jsonl ◄──┤  extract/ (agent + audit)│  schema → charted fields
                     └──────────┬───────────────┘
                                ▼
        ┌─────────────────────────────────────────────┐
        │  synthesise/                                 │
        │    aggregate   → synthesis-tables.json       │
        │    prisma_flow → prisma-flow.json            │
        │  ui/                                         │
        │    build_review_site → index.html + pages    │
        └─────────────────────────────────────────────┘
```

## Quickstart

```bash
# Show the composed full Boolean query (sanity check the strategy)
python -m paperscope.systematic_review search myreview.yaml --show-query

# Per-block counts before harvesting (find unexpected volume sources)
python -m paperscope.systematic_review search myreview.yaml --block-counts

# Harvest MEDLINE → records.jsonl
python -m paperscope.systematic_review search myreview.yaml

# After AI screening + charting have populated screening.jsonl + extraction.jsonl:
python -m paperscope.systematic_review aggregate myreview.yaml
python -m paperscope.systematic_review prisma --config myreview.yaml
python -m paperscope.systematic_review build-site --config myreview.yaml --out ./review-site

# Optional: walk the paywalled tail with a real browser profile
python -m paperscope.systematic_review browser-harvest \
  --config myreview.yaml \
  --user-data-dir "$HOME/Library/Application Support/Google/Chrome" \
  --profile-directory Default \
  --group-by-publisher \
  --inter-paper-delay 5
```

## Configuration

A review config is a single YAML — see `examples/mnd-pilot.yaml` for a full
worked example. The four sections:

```yaml
name: my-review
pcc:
  population: "..."
  concept: "..."
  context: "..."
search:
  databases: [medline, embase, cinahl]
  query_blocks:
    C1_population: '(MeSH/tiab strings)'
    C2_intervention: '(...)'
    C3_outcome: '(...)'
  filters: 'English[lang] AND humans[mesh] AND 2000:2026[pdat] NOT (editorial[pt])'
aggregation:
  list_counters: [...]      # frequency tables over list-of-string fields
  scalar_counters: [...]    # frequency tables over single-value fields
  text_collections: [...]   # collect non-empty texts with companion fields
  numeric_extractors: [...] # regex-extract numbers from free-text fields
```

The aggregation system is fully declarative. See `synthesise/aggregate.py` for
the spec schemas of each aggregation type.

## What's built (v0)

| Layer | Status | Notes |
|---|---|---|
| `config` | ✅ | YAML loader, dataclasses |
| `records` | ✅ | JSONL helpers |
| `search/medline` | ✅ | NCBI E-utilities; generic query composition |
| `search/ovid_import` | 🚧 | Interface fixed, parser staged |
| `search/ebsco_import` | 🚧 | Interface fixed, parser staged |
| `synthesise.aggregate` | ✅ | Generic, regression-verified |
| `synthesise.prisma_flow` | ✅ | Generic, regression-verified |
| `synthesise.dedup` | ✅ | PMID → DOI → normalised title |
| `screen.rubric` | ✅ | Markdown rubric parser |
| `screen.ai_screen` | 🪝 | Interface + stub; wire your agent SDK |
| `extract.schema` | ✅ | Markdown schema parser |
| `extract.ai_extract` | 🪝 | Interface + stub; wire your agent SDK |
| `acquire.pipeline` | ✅ | OA PDF pull (Unpaywall via `paperscope.ingest`) + opt-in last-resort ("shadow") Stage 3 (`enable_shadow_library=True`; not in the public build — bring your own provider, see `docs/ACQUISITION.md`) + EZProxy queue for the paywalled tail + coverage report. Idempotent re-runs. CLI: `acquire`. |
| `acquire.browser_driver` | ✅ | Playwright-driven institutional-access harvester for the paywalled tail. Supports real Chrome profiles, warmup DOI, publisher grouping, strategy cache, and inter-paper pacing. CLI: `browser-harvest`. |
| `ingest.shadow_library` | 🚧 | Last-resort ("shadow") acquisition is NOT included in the public build — the entry point is a stub that raises; bring your own provider (see `docs/ACQUISITION.md`). Off by default in the pipeline; the explicit `enable_shadow_library=True` flag opts in to whatever provider you wire in. Open-access acquisition (Unpaywall / publisher OA / EZProxy) is unaffected. |
| `ui.build_review_site` | ✅ | Static HTML with Covidence-style record pages. v0 is PubMed-shaped: keys records by `pmid` and writes filenames from it — fine for MEDLINE, needs a generic `record_id` for Embase/CINAHL accession strings. |
| `ui.serve` | 🚧 | Live-edit server, designed not built |
| `methodological_audit` | ✅ | Per-paper rubric-based audit pipeline (cluster, sample, score, exclusions). Extracted from a working scoping review's audit layer, with calibration validated by a blind recheck. See `methodological_audit/README.md`. |
| `forensic_scan` | ✅ | Corpus-scale forensic data-quality scan (p-curve, last-digit, positivity, industry-bias, salami). Uses `paperscope.analysis.forensic_stats` for per-paper verification. See `forensic_scan/README.md`. Documents known false-positive modes for medical literature (statcheck ~95% FP, GRIM ~100% FP on continuous data). |
| `knowledge_base` | 🧭 | Roadmap stage: paper cards, clusters, source manifests, public summaries, private source links, and rater-family disagreement reports. See `../../docs/corpus-knowledge-base.md`. |

## Companion modules: methodological audit + forensic scan

Beyond screening/charting/synthesising the records, paperscope ships two **audit layers** that grade the corpus itself:

| Module | Question it answers | Output |
|---|---|---|
| `methodological_audit` | Does each paper *ask the right question with the right construct*? | Per-paper rubric ratings in audit.sqlite; cluster-resolved prevalence tables; in-corpus thesis-voice catalogue |
| `forensic_scan` | Do each paper's *reported numbers behave like honestly-generated numbers*? | p-curve (Simonsohn); last-digit (Newcomb-Benford check); result-positivity (publication bias); industry × positivity; salami screen |

Both are corpus-scale; both use AI sub-agent reading where applicable; both are documented with their known failure modes so users don't repeat the false-positive overcounts the working review had to discover.

## Knowledge-base direction

The static HTML review site is the v0 audit surface. The next product layer is a corpus knowledge base: paper cards, cluster pages, quality flags, source-object manifests, and field-level rater disagreement. This keeps large AI-assisted reviews navigable for humans after the bulk extraction has finished.

The design is in `../../docs/corpus-knowledge-base.md`. The key boundary is that PaperScope supplies the mechanics; project-specific rubrics, labels, disease claims, and synthesis arguments stay in the caller repo.

## Regression test

`tests/test_systematic_review.py` dogfoods the module against a working scoping
review's corpus (a private caller's, not shipped with the repo).
It asserts **semantic equivalence with the existing `synthesis-tables.json`
across 15 assertions** — corpus size, every top-N counter, every text
collection, model-prediction roll-up, delay summary + detail rows, and the
PRISMA funnel numbers. Not byte-identical: the new output's key names are
deliberately cleaner (e.g. `model_prediction_by_category` instead of nested
`model_prediction.by_category`, `delay.min` instead of `delay.min_months`).
The test compares values, not serialisation. 15 / 15 pass.

```bash
python tests/test_systematic_review.py          # standalone runner
pytest tests/test_systematic_review.py -v       # under pytest
```

The review corpus path is read from the `PAPERSCOPE_SR_CORPUS` environment
variable (pointing at a directory with the review's `extraction.jsonl`,
`screening.jsonl`, `records.jsonl`, and `synthesis-tables.json`); if it's unset
or the inputs are missing, the test skips.

## Design

See `docs/systematic-review.md` for the architectural thinking — pipeline
shape, the JSONL contract between layers, the human-in-the-loop model, and
the roadmap.
