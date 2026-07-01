# `paperscope.systematic_review.methodological_audit`

A corpus-scale per-paper methodological audit pipeline. Apply a versioned rubric to every paper in a scoping/systematic review corpus, record ratings + evidence quotes in a queryable sqlite database, and report prevalence-by-cluster, prevalence-by-dimension, and inter-version drift.

**Status:** v1, extracted from a working scoping review (2026-05-16) that audited its corpus via parallel AI sub-agent reads, with calibration validated by a blind recheck.

## Why this exists

Standard scoping-review charting captures *what* papers report. It does not capture *how methodologically defensible* the reports are. A scoping review can correctly enumerate 600 biomarker papers without noticing that 60% of them use a criterion-defined cohort to validate features of the criterion they were diagnosed against — a thesis-relevant pattern only detectable by reading each paper against a rubric.

Doing this by hand at corpus scale (≥1,000 papers) is infeasible. Doing it by AI agent against a written rubric is feasible — provided:

1. The rubric is operationally specific enough that independent agents converge on the same ratings (calibrate first; measure drift).
2. The sampling is structured so claims tighten predictably with effort (L0 → L1 → L2 → L3 → L4 = 1 / 5 / 20 / 50 / all per cluster).
3. The exclusion track separates "paper can't be audited" from "audit found problems."
4. The database keeps every rating tagged with its rubric version, so v0.1 → v0.2 refinements don't destroy the old data.

This module is that infrastructure.

## Pipeline at a glance

```
                              ┌────────────────┐
   corpus text/<pmid>.txt ────┤  exclusions    │  detect dupes / non-English / boilerplate
                              │                │  / content-vs-metadata mismatch
                              └───────┬────────┘
                                      ▼
   embeddings/<pmid>.vec     ┌────────────────┐
   (any embedder; e.g. ──────┤  cluster       │  k-means k=20 default
   Gemini Embedding 2)       │                │  cluster_run_id = 'kmeans-20-2026-05-16'
                              └───────┬────────┘
                                      ▼
                              ┌────────────────┐
                              │  sample        │  L0 (1/cluster) → L4 (all)
                              │                │  filtered by audit_exclusions
                              └───────┬────────┘
                                      ▼
                              ┌────────────────┐
   rubric-v0.1.md  ──────────►│  read (agent)  │  apply rubric per paper;
                              │                │  emit ratings JSONL
                              └───────┬────────┘
                                      ▼
                              ┌────────────────┐
                              │  score         │  ingest into audit.sqlite
                              │                │  (one row per pmid × dimension)
                              └───────┬────────┘
                                      ▼
                              ┌────────────────┐
                              │  queries       │  prevalence / by-cluster / drift /
                              │                │  coverage / picks
                              └────────────────┘
```

## When to use this

- You have a corpus of ≥100 text-extracted papers (PyMuPDF, tika, etc.)
- You want to make claims about *patterns of methodological practice* in that corpus
- You have a written rubric (or are willing to draft one)
- You have access to AI sub-agents (or human readers willing to apply the rubric)

If you only need full-text screening (in/out for the review), use `paperscope.systematic_review.screen` instead.

## Pipeline modules

| Module | What it does | Failure modes to know about |
|---|---|---|
| `schema` | SQL schema for `audit.sqlite` (papers, clusters, cluster_assignments, audit_ratings, sampling_runs, sampling_picks, rubric_versions, rescores, audit_exclusions) + `init_db()` | None known. Schema is idempotent. |
| `rubric` | Load operational rubric from markdown + structured YAML/JSON section | The rubric is the audit's substrate. If it's vague, ratings will drift between agents. Calibrate on 10 papers before scaling. |
| `cluster` | k-means clustering on embedding vectors (default k=20). L2-normalises vectors so Euclidean ≈ cosine. | Cluster 7-style "wrong-content artefact clusters" form when byte-identical papers exist in the corpus — exclude before clustering. |
| `sample` | L0 (centroid-nearest), L1 (spread-stratified), L2/L3 (stratified-random), L4 (all). Filters out `audit_exclusions` at pick time. | A cluster with all-excluded members will yield no picks (catch this; consider re-clustering). |
| `score` | JSONL ingest with required-evidence-quote enforcement on `suspect`/`missing` ratings. Idempotent INSERT OR REPLACE by `(pmid, rubric_version, dimension)`. | Re-rating overwrites the prior rating for the same version+dimension. For drift detection, use `rubric_version="v0.1-recheck"` on the second pass. |
| `exclusions` | Multi-heuristic detection: byte-identical de-dup, non-English stopword check, corrupted text symbol-runs, title-in-text-vs-metadata-title fuzzy match, boilerplate-only line-uniqueness, domain-keyword absence (or any keyword set). | Title fuzzy-match needs threshold tuning per corpus (0.30 strict / 0.50 lax worked for the demo review). |
| `queries` | Prevalence by (dimension, rating), by cluster × dimension, drift between rubric versions, coverage, picks-detail. | None known. |

## The pass-depth ladder

| Level | Per-cluster sample | What it gives you |
|---|---:|---|
| L0 | 1 (centroid-nearest) | First read of every cluster; rubric stress test; cluster taxonomy |
| L1 | 5 (spread-stratified) | First cluster profiles; rubric refinement to v0.2 if needed |
| L2 | 20 (stratified-random) | First statistical claims with usable CIs per cluster |
| L3 | 50 (powered) | Tight CIs on every dimension flag |
| L4 | all | Complete catalogue; full dataset releasable |

In practice, each level can be done by parallel AI sub-agents (one per cluster or cluster group) reading against the same rubric + earlier-level ratings as calibration anchors. The demo review dispatched parallel sub-agents across L1+L2+L3+L4 and aggregated its ratings in a single afternoon-evening session.

## Calibration discipline (important)

Before scaling, calibrate. The demo review did this implicitly by reading L0 manually then dispatching L1 sub-agents with the L0 ratings as anchors. The drift check (a blind recheck after L4 complete) showed:

- **high within-one-grade agreement** — the rubric is reliable at the resolution we report claims at
- **lower exact-match agreement** — borderline calls (acceptable↔suspect, good↔acceptable) drift more than category-decisive ones
- Per-dimension agreement varies; the most-concrete sub-checks rate most reliably

**Bake calibration into the workflow.** After each level, sample 20 papers from the prior level, re-rate blindly (no access to prior ratings), compute per-dimension exact + within-one-grade agreement. If exact agreement drops below ~60% on the thesis-relevant dimension, the rubric needs a revision.

## Known limitations

- The rubric is the audit. Vague rubric → drifted ratings. Operationally-specific sub-checks (e.g., "exact p-values reported" vs "transparent statistics") reliably get >75% exact-match agreement; subjective overall ratings (e.g., "is this paper good?") drift heavily.
- Off-the-shelf clustering (k-means on document embeddings) creates "quality-control sink" clusters when the embedding space picks up low-quality content (short fragments, abbreviation collisions, wrong-content acquisition errors). Plan to exclude these (`exclusions` catches most) and to recognise the cluster's dissolution as itself a finding.
- Expect a discoverable wrong-content rate in the acquisition pipeline even after byte-identical de-dup — content mismatch is caught only by reading the actual files. Budget for a discoverable acquisition-error rate of 5-15% and document the exclusion findings as part of the methods paper.
- Construct adequacy means different things for different paper-type / research-question combinations. The rubric's `dimensionality_lens_applicable` tag (v0.2) lets you stratify reports by lens applicability so claims are made at the right granularity.

## See also

- `paperscope.systematic_review.forensic_scan` — companion corpus-scale forensic data-quality scan (p-curve, positivity, last-digit, funding-COI, salami) using `paperscope.analysis.forensic_stats` for per-paper checks
- `paperscope.analysis.forensic_stats` — individual forensic tests (GRIM, GRIMMER, DEBIT, SPRITE, Carlisle, Benford, statcheck-style p-value verification)
- `paperscope.systematic_review.screen` — the in/out screening step that runs *before* the methodological audit
