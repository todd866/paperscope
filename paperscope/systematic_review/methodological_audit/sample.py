"""Pick papers per cluster at each resolution level (L0-L4).

Five methods:
    L0 — centroid-nearest:   1 paper per cluster (closest to centroid)
    L1 — spread-stratified:  5 per cluster, k evenly-spaced quantiles
                              of distance-to-centroid
    L2 — stratified-random:  20 per cluster, seeded random
    L3 — stratified-random:  50 per cluster, seeded random
    L4 — all:                every auditable paper

All methods automatically filter out pmids in `audit_exclusions`. Picks are
written both to a JSONL (for sub-agent consumption) and to the
`sampling_picks` table (for reproducibility).

Usage:
    from paperscope.systematic_review.methodological_audit.sample import pick_papers
    picks_path = pick_papers(
        db_path="audit.sqlite",
        level="L1",
        cluster_run_id="kmeans-20-2026-05-16",  # or None to use latest
        out_path="audit/L1-picks.jsonl",
    )
"""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime
from pathlib import Path

LEVELS = {
    "L0": {"per_cluster": 1, "method": "centroid-nearest"},
    "L1": {"per_cluster": 5, "method": "spread-stratified"},
    "L2": {"per_cluster": 20, "method": "stratified-random"},
    "L3": {"per_cluster": 50, "method": "stratified-random"},
    "L4": {"per_cluster": None, "method": "all"},
}

_NOT_EXCLUDED = "AND ca.pmid NOT IN (SELECT pmid FROM audit_exclusions)"


def _resolve_cluster_run(con: sqlite3.Connection, cluster_run_id: str | None) -> str:
    if cluster_run_id:
        return cluster_run_id
    row = con.execute("""
        SELECT cluster_run_id FROM clusters
        GROUP BY cluster_run_id ORDER BY MAX(rowid) DESC LIMIT 1
    """).fetchone()
    if not row:
        raise RuntimeError("No clusters in DB. Run cluster_corpus() first.")
    return row[0]


def _cluster_ids(con: sqlite3.Connection, cluster_run_id: str) -> list[int]:
    return [r[0] for r in con.execute(
        "SELECT cluster_id FROM clusters WHERE cluster_run_id = ?",
        (cluster_run_id,),
    ).fetchall()]


def pick_centroid_nearest(con, cluster_run_id: str, k: int) -> list[dict]:
    picks = []
    for cid in _cluster_ids(con, cluster_run_id):
        rows = con.execute(f"""
            SELECT ca.pmid, ca.distance_to_centroid
            FROM cluster_assignments ca
            WHERE ca.cluster_run_id = ? AND ca.cluster_id = ?
                  {_NOT_EXCLUDED}
            ORDER BY ca.distance_to_centroid ASC
            LIMIT ?
        """, (cluster_run_id, cid, k)).fetchall()
        for rank, (pmid, dist) in enumerate(rows):
            picks.append({"pmid": pmid, "cluster_id": cid, "rank_in_cluster": rank,
                          "rationale": f"distance={dist:.4f}"})
    return picks


def pick_spread_stratified(con, cluster_run_id: str, k: int) -> list[dict]:
    picks = []
    for cid in _cluster_ids(con, cluster_run_id):
        rows = con.execute(f"""
            SELECT ca.pmid, ca.distance_to_centroid
            FROM cluster_assignments ca
            WHERE ca.cluster_run_id = ? AND ca.cluster_id = ?
                  {_NOT_EXCLUDED}
            ORDER BY ca.distance_to_centroid ASC
        """, (cluster_run_id, cid)).fetchall()
        if not rows:
            continue
        n = len(rows)
        chosen = list(range(n)) if k >= n else [int(i * n / k) for i in range(k)]
        for rank, idx in enumerate(chosen):
            pmid, dist = rows[idx]
            picks.append({"pmid": pmid, "cluster_id": cid, "rank_in_cluster": rank,
                          "rationale": f"idx={idx}/{n}, distance={dist:.4f}"})
    return picks


def pick_stratified_random(con, cluster_run_id: str, k: int, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    picks = []
    for cid in _cluster_ids(con, cluster_run_id):
        rows = con.execute(f"""
            SELECT ca.pmid, ca.distance_to_centroid
            FROM cluster_assignments ca
            WHERE ca.cluster_run_id = ? AND ca.cluster_id = ?
                  {_NOT_EXCLUDED}
        """, (cluster_run_id, cid)).fetchall()
        chosen = rng.sample(rows, min(k, len(rows)))
        for rank, (pmid, dist) in enumerate(chosen):
            picks.append({"pmid": pmid, "cluster_id": cid, "rank_in_cluster": rank,
                          "rationale": f"random seed={seed}, distance={dist:.4f}"})
    return picks


def pick_all(con, cluster_run_id: str) -> list[dict]:
    rows = con.execute(f"""
        SELECT ca.pmid, ca.cluster_id, ca.distance_to_centroid
        FROM cluster_assignments ca
        WHERE ca.cluster_run_id = ?
              {_NOT_EXCLUDED}
        ORDER BY ca.cluster_id, ca.distance_to_centroid
    """, (cluster_run_id,)).fetchall()
    picks = []
    by_cluster: dict[int, int] = {}
    for pmid, cid, dist in rows:
        rank = by_cluster.get(cid, 0)
        by_cluster[cid] = rank + 1
        picks.append({"pmid": pmid, "cluster_id": cid, "rank_in_cluster": rank,
                      "rationale": f"all-L4, distance={dist:.4f}"})
    return picks


def pick_papers(
    *,
    db_path: str | Path,
    level: str,
    cluster_run_id: str | None = None,
    out_path: str | Path | None = None,
    seed: int = 42,
) -> Path:
    """Pick papers per cluster at the given level; write JSONL + record in
    sampling_runs/sampling_picks. Returns the output JSONL path.

    Enriches each pick row with title/year/journal from the papers table so
    sub-agents can scan picks before reading full text."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {list(LEVELS.keys())}")
    spec = LEVELS[level]
    db_path = Path(db_path)
    con = sqlite3.connect(db_path)
    cluster_run_id = _resolve_cluster_run(con, cluster_run_id)

    k = spec["per_cluster"]
    method = spec["method"]
    if method == "centroid-nearest":
        picks = pick_centroid_nearest(con, cluster_run_id, k)
    elif method == "spread-stratified":
        picks = pick_spread_stratified(con, cluster_run_id, k)
    elif method == "stratified-random":
        picks = pick_stratified_random(con, cluster_run_id, k, seed=seed)
    elif method == "all":
        picks = pick_all(con, cluster_run_id)
    else:
        raise ValueError(method)

    # Record sampling_run
    sampling_run_id = f"{level}-{datetime.now().strftime('%Y-%m-%dT%H%M%S')}"
    con.execute("""
        INSERT INTO sampling_runs (sampling_run_id, level, cluster_run_id,
                                   per_cluster_n, sampling_method, created_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (sampling_run_id, level, cluster_run_id, k, method,
          datetime.now().isoformat(timespec="seconds"),
          f"seed={seed}" if method == "stratified-random" else ""))
    for p in picks:
        con.execute("""
            INSERT OR REPLACE INTO sampling_picks
                (sampling_run_id, pmid, cluster_id, rank_in_cluster)
            VALUES (?, ?, ?, ?)
        """, (sampling_run_id, p["pmid"], p["cluster_id"], p["rank_in_cluster"]))
    con.commit()

    # Enrich picks with title/year/journal
    pmids = [p["pmid"] for p in picks]
    meta: dict[str, tuple] = {}
    if pmids:
        placeholders = ",".join("?" for _ in pmids)
        rows = con.execute(
            f"SELECT pmid, title, year, journal FROM papers WHERE pmid IN ({placeholders})",
            pmids,
        ).fetchall()
        meta = {r[0]: (r[1], r[2], r[3]) for r in rows}

    if out_path is None:
        out_path = db_path.parent / f"{level}-picks.jsonl"
    out_path = Path(out_path)
    with out_path.open("w") as f:
        for p in picks:
            title, year, journal = meta.get(p["pmid"], (None, None, None))
            f.write(json.dumps({
                **p,
                "sampling_run_id": sampling_run_id,
                "title": title, "year": year, "journal": journal,
            }) + "\n")

    con.close()
    return out_path
