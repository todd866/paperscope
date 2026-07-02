# Corpus Knowledge Bases

## Purpose

Paperscope's systematic-review layer should produce more than a PRISMA flow and synthesis tables. For large reviews, the practical product is a corpus knowledge base: a navigable evidence surface where paper records, extracted text, AI-generated summaries, quality flags, clusters, and source-object links stay connected.

This document records the roadmap exposed by a large systematic-review dogfood project. The domain-specific claims and rubrics belong in that project. The infrastructure patterns belong in paperscope.

The motivating principle is that "evaluate this paper" and "evaluate this corpus" are not separate jobs. A paper can only be evaluated relative to its surrounding literature: what it cites, what it misses, what methods are standard, what claims are already saturated, and what field-level biases or reporting patterns surround it. The corpus knowledge base is the substrate that makes individual paper critique honest.

## Target User Experience

A reviewer should be able to open a review portal and answer:

- What is this paper, and why is it in the review?
- How typical or unusual is this paper relative to its cluster?
- What cluster or topic does it belong to?
- Which papers support a particular synthesis claim?
- Which records are off-scope, mismatched, duplicated, or weakly supported?
- What extracted text or source PDF exists, and where is it stored?
- How did different rater families describe or disagree about this paper?

The public layer should be useful without source-paper access. The private layer should link authenticated users to source PDFs or full text when the review owner has lawful access.

## Data Model

The reusable model should separate five layers:

| Layer | Contents | Public by default |
|---|---|---|
| Record metadata | title, authors, year, DOI, PMID, journal, database source | yes |
| Paper card | short summary, relevance note, key claims, methods, populations, limitations, cluster context | yes, after review |
| Review metadata | screening decision, extraction fields, quality flags, cluster labels, rater family | usually yes |
| Source artefacts | PDF object key, extracted text path, checksum, acquisition route | no |
| Private access state | signed/proxied URLs, auth policy, object-store location | no |

The same review should be exportable as static HTML, a JSON data package, or a Next.js-compatible knowledge-base bundle.

## Core Modules To Build

### 1. Provider-Neutral Paper Store

Current Paperscope storage is Backblaze B2-oriented. The general layer should support S3-compatible stores such as Cloudflare R2 without changing the review code.

Manifest fields:

- `record_id`
- `doi` / `pmid` / external accession
- `object_key`
- `sha256`
- `bytes`
- `media_type`
- `source_status`
- `acquisition_route`
- `public_allowed`
- `private_access_policy`

### 2. Rich Metadata Extraction

Move per-paper markdown/YAML conventions into a reusable package. The framework should provide:

- schema versioning;
- prompt generation;
- output validation;
- parse repair;
- field-level provenance;
- batch manifests;
- resumable dispatch plans.

The caller supplies the domain schema. Paperscope supplies the mechanics.

### 3. Rater-Family Comparison

Large AI-assisted reviews need disagreement analysis that is richer than kappa. Paperscope should compare two or more rater families field-by-field:

- exact field agreement;
- directional disagreement;
- categorical disagreement;
- prose-distance / summary-distance;
- missingness;
- per-paper disagreement counts;
- cluster-level disagreement patterns.

Kappa remains useful for narrow categorical fields, but the knowledge-base use case needs structured disagreement as an output, not just a reliability penalty.

### 4. Cluster and Claim Navigation

The review portal should support:

- cluster pages;
- representative papers;
- cluster-level summaries;
- claim-to-paper links;
- paper-to-claim links;
- quality and off-scope flags;
- source access state.

Cluster labels may come from embeddings, caller-supplied taxonomies, or manual review.

### 5. Paper-in-Corpus Evaluation

The paper page should show the local paper and its corpus context together:

- nearest neighbours;
- cluster centroid / representative papers;
- claims this paper supports;
- claims this paper contradicts or complicates;
- methods used by nearby papers;
- missing comparator methods from the same corpus;
- whether the paper is typical, peripheral, or anomalous;
- whether quality or forensic flags are paper-specific or corpus-wide.

This is the practical bridge between the classic `critical-read` command and the systematic-review pipeline.

### 6. Knowledge-Base Export

Add a general exporter that writes:

```text
review-data/
  records.jsonl
  paper-cards.jsonl
  clusters.json
  claims.jsonl
  quality-flags.jsonl
  source-manifest.jsonl
  public-index.json
```

The existing static HTML builder can consume this package. A Next.js/Vercel portal can also consume it without depending on Paperscope at runtime.

For single-paper pages, use paperscope's native paper-site scaffold
(`python3 -m paperscope paper-site`): a generated Next app should consume paper
identity, TeX-derived manuscript text, figure assets, citation inventories,
local-paper-library harvest state, and a separate source-object manifest. A
dependency-free static HTML renderer can remain a lower-fidelity export, but the
high-fidelity paper surface is the native app with live citation panels and
per-reference pages.

## Boundary

Paperscope should stay generic. It should not encode:

- domain-specific rubrics;
- disease-specific cluster names;
- project-specific journal arguments;
- institution-specific access policies;
- hard-coded Cloudflare or Vercel assumptions.

Those belong in the caller project or in example configs.

## Roadmap

1. Generalise cloud storage from B2 to provider-neutral S3-compatible manifests.
2. Add `systematic_review.rich_metadata` for schema, prompts, validation, repair, and manifests.
3. Add `systematic_review.rater_compare` for structured field-level disagreement.
4. Add paper-in-corpus evaluation fields to paper cards.
5. Add `systematic_review.knowledge_base` exporter.
6. Extend static HTML output to consume paper cards and clusters.
7. Add the native single-paper app renderer (the `paper-site` scaffold).
8. Keep a static HTML fallback, but treat it as a secondary export rather than
   the canonical high-fidelity paper interface.
9. Document a Next.js/Vercel consumer pattern without making it the only supported UI.
10. Keep a large real-world review as regression dogfood for scale, messy metadata, rater disagreement, and private source access.
