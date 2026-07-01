"""Rating ingestion for the methodological audit.

Two modes:

  1. JSONL ingest (`ingest_jsonl`) — bulk-load a sub-agent's rating output.
  2. Python API (`rate_paper`) — write a single rating in-process.

Both enforce:
  - dimension must be in `VALID_DIMENSIONS`
  - rating must be in `VALID_RATINGS`
  - `evidence_quote` required for ratings of `suspect` or `missing`
  - INSERT OR REPLACE by (pmid, rubric_version, dimension); re-rating
    overwrites the prior rating for the same version/dimension tuple.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

# v0.1 + v0.2 dimensions (callers can extend by editing VALID_DIMENSIONS)
VALID_DIMENSIONS = {
    "statistical_hygiene",
    "transparency",
    "construct_validity",
    "reproducibility",
    "novelty",
    "construct_adequacy",
    # v0.2 additions
    "screening_fit",
    "transparency_basic_disclosure",
    "transparency_review_process",
}

VALID_RATINGS = {"good", "acceptable", "suspect", "missing", "n/a", "unclear"}


def rate_paper(con: sqlite3.Connection, *,
               pmid: str,
               rubric_version: str,
               dimension: str,
               rating: str,
               paper_type: str | None = None,
               evidence_quote: str = "",
               free_notes: str = "",
               sub_ratings: dict | None = None,
               confidence: int | None = None) -> None:
    """Write a single rating. Overwrites any prior rating for the same
    (pmid, rubric_version, dimension) tuple. Caller is responsible for
    committing."""
    if dimension not in VALID_DIMENSIONS:
        raise ValueError(f"dimension '{dimension}' not in {VALID_DIMENSIONS}")
    if rating not in VALID_RATINGS:
        raise ValueError(f"rating '{rating}' not in {VALID_RATINGS}")
    if not evidence_quote.strip() and rating in {"suspect", "missing"}:
        raise ValueError(
            f"evidence_quote required for rating='{rating}' on {pmid} {dimension}"
        )
    con.execute("""
        INSERT OR REPLACE INTO audit_ratings
            (pmid, rubric_version, dimension, paper_type, rating,
             sub_ratings_json, evidence_quote, free_notes, scored_at, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pmid, rubric_version, dimension, paper_type, rating,
        json.dumps(sub_ratings) if sub_ratings else None,
        evidence_quote, free_notes,
        datetime.now().isoformat(timespec="seconds"),
        confidence,
    ))


def ingest_jsonl(con: sqlite3.Connection, path: str | Path) -> tuple[int, list[str]]:
    """Load a JSONL of ratings (one rating per line). Returns (n_ingested, errors).

    JSONL row format:
        {
          "pmid": "12710512",
          "rubric_version": "v0.1",
          "dimension": "construct_validity",
          "paper_type": "original_research_quantitative",
          "rating": "suspect",
          "evidence_quote": "…",
          "free_notes": "",
          "confidence": 8
        }

    Caller is responsible for committing."""
    path = Path(path)
    n = 0
    errors: list[str] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                rate_paper(
                    con,
                    pmid=d["pmid"],
                    rubric_version=d["rubric_version"],
                    dimension=d["dimension"],
                    rating=d["rating"],
                    paper_type=d.get("paper_type"),
                    evidence_quote=d.get("evidence_quote", ""),
                    free_notes=d.get("free_notes", ""),
                    sub_ratings=d.get("sub_ratings"),
                    confidence=d.get("confidence"),
                )
                n += 1
            except Exception as e:
                errors.append(f"{type(e).__name__}: {e} (line: {line[:120]!r})")
    return n, errors
