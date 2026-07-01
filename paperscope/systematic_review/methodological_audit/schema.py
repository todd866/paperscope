"""SQL schema and DB initialiser for the methodological-audit substrate.

Tables:
    papers              — corpus metadata (pmid, title, year, journal, source_db)
    clusters            — embedding clusters (named after L0 read)
    cluster_assignments — pmid → cluster_id with distance-to-centroid
    rubric_versions     — versioned rubric registry (v0.1, v0.2, …)
    audit_ratings       — the ratings themselves (pmid × dimension × version)
    sampling_runs       — per-level sampling sessions
    sampling_picks      — pmids picked in each session
    audit_exclusions    — pmids skipped by sample() (dupes, non-English, etc.)
    rescores            — self-disagreement spot-check ratings for drift analysis

Run `init_db(path, schema_sql)` to create or refresh; idempotent.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS papers (
    pmid           TEXT PRIMARY KEY,
    title          TEXT,
    year           INTEGER,
    journal        TEXT,
    n_text_chars   INTEGER,
    in_included    INTEGER,
    source_db      TEXT
);

CREATE TABLE IF NOT EXISTS clusters (
    cluster_run_id     TEXT,
    cluster_id         INTEGER,
    cluster_name       TEXT,
    cluster_description TEXT,
    n_papers           INTEGER,
    centroid_pmid      TEXT,
    PRIMARY KEY (cluster_run_id, cluster_id),
    FOREIGN KEY (centroid_pmid) REFERENCES papers(pmid)
);

CREATE TABLE IF NOT EXISTS cluster_assignments (
    cluster_run_id     TEXT,
    pmid               TEXT,
    cluster_id         INTEGER,
    distance_to_centroid REAL,
    PRIMARY KEY (cluster_run_id, pmid),
    FOREIGN KEY (pmid) REFERENCES papers(pmid),
    FOREIGN KEY (cluster_run_id, cluster_id) REFERENCES clusters(cluster_run_id, cluster_id)
);

CREATE INDEX IF NOT EXISTS idx_cluster_assign_cluster
    ON cluster_assignments(cluster_run_id, cluster_id);

CREATE TABLE IF NOT EXISTS rubric_versions (
    rubric_version     TEXT PRIMARY KEY,
    authored_at        TEXT,
    superseded_at      TEXT,
    changelog          TEXT,
    notes              TEXT
);

CREATE TABLE IF NOT EXISTS audit_ratings (
    pmid              TEXT NOT NULL,
    rubric_version    TEXT NOT NULL,
    dimension         TEXT NOT NULL,
    paper_type        TEXT,
    rating            TEXT NOT NULL,
    sub_ratings_json  TEXT,
    evidence_quote    TEXT,
    free_notes        TEXT,
    scored_at         TEXT NOT NULL,
    confidence        INTEGER,
    PRIMARY KEY (pmid, rubric_version, dimension),
    FOREIGN KEY (pmid) REFERENCES papers(pmid),
    FOREIGN KEY (rubric_version) REFERENCES rubric_versions(rubric_version)
);

CREATE INDEX IF NOT EXISTS idx_audit_dim ON audit_ratings(dimension, rating);
CREATE INDEX IF NOT EXISTS idx_audit_version ON audit_ratings(rubric_version);

CREATE TABLE IF NOT EXISTS sampling_runs (
    sampling_run_id    TEXT PRIMARY KEY,
    level              TEXT,
    cluster_run_id     TEXT,
    per_cluster_n      INTEGER,
    sampling_method    TEXT,
    created_at         TEXT,
    notes              TEXT
);

CREATE TABLE IF NOT EXISTS sampling_picks (
    sampling_run_id    TEXT,
    pmid               TEXT,
    cluster_id         INTEGER,
    rank_in_cluster    INTEGER,
    PRIMARY KEY (sampling_run_id, pmid),
    FOREIGN KEY (sampling_run_id) REFERENCES sampling_runs(sampling_run_id),
    FOREIGN KEY (pmid) REFERENCES papers(pmid)
);

CREATE TABLE IF NOT EXISTS audit_exclusions (
    pmid          TEXT PRIMARY KEY,
    reason        TEXT NOT NULL,
    details       TEXT,
    flagged_at    TEXT
);

CREATE TABLE IF NOT EXISTS rescores (
    pmid              TEXT,
    rubric_version    TEXT,
    dimension         TEXT,
    original_rating   TEXT,
    rescored_rating   TEXT,
    rescored_at       TEXT,
    agreement         INTEGER,
    notes             TEXT,
    PRIMARY KEY (pmid, rubric_version, dimension, rescored_at)
);
"""


def init_db(db_path: str | Path) -> None:
    """Create or refresh audit.sqlite at `db_path`. Idempotent — running twice
    is safe (CREATE TABLE IF NOT EXISTS). Does not seed any data; callers
    typically follow with their own seed pass (e.g., from a records.jsonl)."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA_SQL)
    con.commit()
    con.close()
