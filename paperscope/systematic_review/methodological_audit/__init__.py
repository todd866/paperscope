"""Per-paper methodological audit at corpus scale.

Where `screen/` decides which papers are *in scope* for a review, this module
decides *how methodologically defensible* each in-scope paper is. The output
is a queryable sqlite database of per-paper ratings against a versioned rubric,
with cluster-resolved sampling so analyses can scale from one-paper-per-cluster
(L0) all the way to every-paper-in-corpus (L4).

The pipeline:

    cluster (k-means on embeddings)
      └── sample (centroid-nearest / spread-stratified / stratified-random / all)
            └── read (human or AI agent applies rubric to each paper)
                  └── score (ingest ratings JSONL into audit.sqlite)
                        └── query (prevalence by dimension, by cluster, drift)

Plus a parallel exclusions track that filters papers unfit for audit
(duplicates, non-English, boilerplate-only extractions, content-vs-metadata
mismatches) so the same picks file can be regenerated cleanly at any level.

See `paperscope/systematic_review/methodological_audit/README.md` for the full
design and a worked scoping-review demonstration.

Submodules:
    schema       — SQL schema for audit.sqlite
    rubric       — operational definitions and YAML/JSON loader
    cluster      — k-means clustering on embedding vectors
    sample       — picker functions for the five resolution levels (L0-L4)
    score        — rating ingestion with required-evidence-quote enforcement
    exclusions   — multi-heuristic exclusion detection (dupes, non-English,
                   boilerplate, title-vs-text mismatch, domain-keyword absence)
    queries      — analytical queries (prevalence by dimension / by cluster, drift)
"""

from paperscope.systematic_review.methodological_audit.schema import init_db
from paperscope.systematic_review.methodological_audit.score import (
    rate_paper,
    ingest_jsonl,
    VALID_RATINGS,
)
from paperscope.systematic_review.methodological_audit.paper_metadata import (
    generate_metadata_corpus,
    write_index,
)
from paperscope.systematic_review.methodological_audit.browser import build_browser

__all__ = [
    "init_db", "rate_paper", "ingest_jsonl", "VALID_RATINGS",
    "generate_metadata_corpus", "write_index", "build_browser",
]
