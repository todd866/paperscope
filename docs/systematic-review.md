# `paperscope.systematic_review` — design

## What this is

A pipeline for running JBI / PRISMA-ScR scoping reviews where the "reviewer" is
one or more AI agents working in parallel, with a human audit layer for
override and sign-off.

This is a *generalised* version of a working MND scoping-review pipeline. The
MND review remains its first user and its regression dogfood; everything about
the MND question lives in `examples/mnd-pilot.yaml`, not in the code.

## Why not just use Covidence

Covidence is excellent for **human** reviewers clicking include/exclude in a
web UI. It's a poor fit for AI-accelerated screening for three reasons.

1. **The interaction shape is wrong.** Covidence's value is the click-loop —
   one record at a time, human in the seat. An AI agent that can screen
   thousands of records in parallel doesn't need the UI; what it needs is a
   structured input (a markdown rubric) and a structured output (a JSONL
   stream of decisions). The UI gets in the way.

2. **It locks methodology choices early.** A review run inside Covidence
   commits to Covidence's two-stage flow, its conflict-resolution model, its
   data model. With JSONL on disk plus a small Python library, the same
   protocol is replayable, diffable in git, and re-usable across reviews.

3. **It's opaque as a method artefact.** "We screened in Covidence" tells a
   reader nothing they can inspect. A public repo whose code, rubric, schema,
   and decision JSONL are all readable says "this is exactly what we did."
   That's the contribution this module is shaped around.

## The pipeline

Four layers, each consuming and producing JSONL files on disk.

```
search    → records.jsonl       (per database, then deduped)
screen    → screening.jsonl     (one decision per record)
extract   → extraction.jsonl    (one charted row per included study)
synthesise → synthesis-tables.json + prisma-flow.json + review-site/
```

Why JSONL everywhere: small, streamable, append-friendly, line-diffable in git,
trivially loadable in any language. The pipeline has no proprietary state —
inspect any layer's output with `head`, `jq`, or `pandas`.

## Protocol as data

A review is fully described by a single YAML config:

```yaml
name: my-review
pcc:        { population, concept, context }
search:     { databases, query_blocks, filters, date_range }
aggregation: { list_counters, scalar_counters, text_collections, numeric_extractors }
rubric_path: ./screening-rubric.md
schema_path: ./extraction-schema.md
corpus_dir:  ./corpus/
```

Nothing about the *particular* review lives in code. The MND configuration in
`examples/mnd-pilot.yaml` is one such review; the code that runs it is the same
code that would run a magnesium-supplementation review or a maternal-mortality
review.

## The two-stage method

Every layer that an AI agent touches has two stages:

```
agent first pass  →  human audit/override  →  the layer's output of record
```

This is the *only* defensible way to run AI screening at scale right now. The
agent reads thousands of records and writes its decision plus a reason; the
human spot-checks a sample, resolves the "maybe" pile, and signs off. The
written reason on every agent decision is what makes the audit tractable —
without it, the human has to re-derive the agent's logic from the title and
abstract alone.

This module deliberately leaves the agent orchestration out. `screen.ai_screen`
and `extract.ai_extract` define the interface (function shape, input/output
contract) and stub implementations; you wire in your agent SDK of choice. The
MND pilot ran this with parallel Claude agents — that orchestration lives in
the caller, not here.

## Aggregation as declarative spec

The synthesis layer is a pure function: charted JSONL + aggregation config →
synthesis tables. Four aggregation types cover what the MND review's
hand-written `build_synthesis.py` did, and they're declared in YAML:

- **`list_counters`** — Counter over list-of-strings fields (onset features,
  differentials, themes), with optional drop list (e.g. drop the index
  condition from a differentials list) and top-N
- **`scalar_counters`** — Counter over single-value fields (study design,
  country, relevance tier), with optional defaults (`uncharted` for an enum
  field that's absent on most rows) and normalisation
- **`text_collections`** — collect non-empty string values with companion
  fields (PMID, country, tier) — for texts the synthesis narrator will weave
  through
- **`numeric_extractors`** — regex-pull numbers (with unit conversion) from a
  free-text field, summarise — for things like "studies report a 14-month
  median delay" where the figure is in prose

The regression test proves this declarative form reproduces the MND review's
hand-coded aggregation outputs exactly. Any new review writes a new YAML; the
code doesn't change.

## PRISMA-ScR flow

`synthesise.prisma_flow` takes the records + screening JSONL (+ optionally a
full-text screening JSONL) and emits the standard PRISMA-ScR funnel numbers:
identified per database, duplicates removed (PMID → DOI → normalised title),
screened, excluded at title/abstract, maybe-for-full-text, and included.

For multi-database reviews, pass `records_per_database={"medline": [...],
"embase": [...]}` and the function deduplicates first.

## Human-in-the-loop UI

The static HTML site (`ui.build_review_site`) renders the current state of
the review: the funnel, the decisions broken down by include/exclude/maybe,
top exclusion reasons, and one page per record with title + abstract +
agent decision + reason + themes hit.

V0 is read-only — it's the "see this GitHub page" method artefact and the
audit surface. The designed-but-not-built `ui.serve` companion adds the
override loop: the same pages, but with include/exclude buttons that POST
back into the JSONL. That's the Covidence-feel layer for working on the
review; the static site stays the public-facing one.

The static site has no JS dependency and a single inline stylesheet, so
shipping it as a `gh-pages` artefact is trivial.

Known v0 limitation: the site is PubMed-shaped — it keys records by `pmid`
and writes filenames straight from PMID. Robust for MEDLINE; not robust for
Embase/CINAHL accession strings (which may contain slashes, dots, or
non-filesystem-safe characters). Generalising to a `record_id` field that
each search adapter normalises into is a follow-up.

## What's not built yet

- **`search/ovid_import` and `search/ebsco_import`** — Embase via Ovid and
  CINAHL via EBSCO are paywalled and don't have clean APIs. The interface is
  fixed (`import_ris(path) → list[dict]`), the parsers wait for someone to
  have an export file in hand.
- **`screen.ai_screen` / `extract.ai_extract` full implementations** —
  intentionally left for the caller's SDK choice. Wiring against Anthropic's
  SDK is straightforward; documenting that recipe is a future README task.
- **`ui.serve`** — the live-edit companion to the static site. Designed but
  not built; first-cut would be ~80 lines of `http.server`.
- **Full-text screening stage** — the JSONL contract is the same as
  title/abstract screening, just a second pass on the "maybe" pile. The
  `prisma_flow` function already accepts `full_text_screening=`; the agent
  glue is the only missing piece.

## What the regression test proves

Running the MND review through this generic pipeline reproduces md-project's
`synthesis-tables.json` across **15 semantic assertions** — every counter,
every text collection, the PRISMA funnel. Not byte-identical: the new
output's key names are deliberately cleaner (e.g. the nested
`model_prediction.{by_category,charted,validation_texts}` is flattened into
`model_prediction_by_category` + `model_validation_texts` + a derivable
boolean; `delay.min_months` becomes `delay.min`). The test compares values,
not serialisation. That's the test of faithfulness — the generalisation
didn't lose anything that mattered.

Specifically, 15 assertions pass:

- corpus size matches (1,464 charted rows)
- onset-features top-40, differentials top-40 (with index-label drops),
  themes, designs, tiers, countries top-15 — all identical
- delay summary (n studies, n values, min/max, median, 8–20-month band count)
  and per-study delay detail rows — all identical
- model-prediction by-category counter, derived "charted" boolean, and
  validation-text rows — all identical
- region breakdowns and weight-loss text collections — identical
- PRISMA-ScR funnel numbers — 6,721 identified, 1,464 included, 4,438 excluded,
  819 maybe

## Relationship to the rest of paperscope

- **`bib/`, `harvest/`, `ingest/`** — paperscope already manages per-paper
  bibliographies and PDF acquisition; the SR module's `search.medline`
  intentionally doesn't duplicate that. For PDF ingestion of an SR's included
  set, call `paperscope.ingest`.
- **`embed/`, `analysis/`** — paperscope's claim-embedding and forensic tools
  apply to individual papers in an SR's included set; a future bridge could
  surface their results in the static review site (e.g. flag included papers
  with forensic issues, or rank them by topical fit).
- **`text/`** — shared text utilities; the SR module uses none of these
  directly today but `chunking` and `latex` would matter for a future
  full-text-driven extraction stage.

## Versioning

Module version is paperscope's. Breaking changes to the YAML config schema
will bump paperscope's minor version and be flagged in the changelog.

## License

Same as paperscope (MIT for code; CC-BY-4.0 for `docs/`).
