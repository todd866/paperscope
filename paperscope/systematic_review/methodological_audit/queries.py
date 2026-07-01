"""Analytical queries over audit.sqlite — prevalence, by-cluster, drift, coverage.

Designed for quick checks during an audit run; analysis notebooks should pull
directly from sqlite via pandas / polars / DuckDB. Each function takes a
sqlite3.Connection and returns either a list of tuples or a formatted string.

Usage:
    import sqlite3
    from paperscope.systematic_review.methodological_audit.queries import (
        prevalence, by_cluster, drift, rated_papers, coverage,
    )
    con = sqlite3.connect("audit.sqlite")
    print(prevalence(con))
    print(by_cluster(con, dimension="construct_adequacy"))
    print(drift(con, "v0.1", "v0.2"))
"""

from __future__ import annotations

import sqlite3


def _fmt(rows: list[tuple], headers: list[str]) -> str:
    if not rows:
        return f"(no rows for headers: {headers})"
    widths = [
        max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]
    sep = "  "
    out = sep.join(h.ljust(w) for h, w in zip(headers, widths))
    out += "\n" + sep.join("-" * w for w in widths)
    for r in rows:
        out += "\n" + sep.join(str(r[i]).ljust(w) for i, w in enumerate(widths))
    return out


def prevalence(con: sqlite3.Connection, rubric_version: str | None = None,
               post_exclusion: bool = True) -> str:
    """Counts per (dimension, rating). Filters audit_exclusions by default."""
    filter_clause = (
        "AND pmid NOT IN (SELECT pmid FROM audit_exclusions)"
        if post_exclusion else ""
    )
    q = f"""
        SELECT dimension, rating, COUNT(DISTINCT pmid) AS n
        FROM audit_ratings
        WHERE (? IS NULL OR rubric_version = ?)
              {filter_clause}
        GROUP BY dimension, rating
        ORDER BY dimension,
                 CASE rating
                     WHEN 'good' THEN 1
                     WHEN 'acceptable' THEN 2
                     WHEN 'suspect' THEN 3
                     WHEN 'missing' THEN 4
                     WHEN 'unclear' THEN 5
                     WHEN 'n/a' THEN 6
                 END
    """
    rows = con.execute(q, (rubric_version, rubric_version)).fetchall()
    return _fmt(rows, ["dimension", "rating", "n"])


def by_cluster(con: sqlite3.Connection, dimension: str = "construct_adequacy",
               cluster_run_id: str | None = None, post_exclusion: bool = True) -> str:
    """For a chosen dimension, show rating distribution per cluster."""
    if cluster_run_id is None:
        row = con.execute("""
            SELECT cluster_run_id FROM cluster_assignments
            GROUP BY cluster_run_id ORDER BY MAX(rowid) DESC LIMIT 1
        """).fetchone()
        if not row:
            return "(no cluster runs in DB)"
        cluster_run_id = row[0]
    filter_clause = (
        "AND ar.pmid NOT IN (SELECT pmid FROM audit_exclusions)"
        if post_exclusion else ""
    )
    q = f"""
        SELECT c.cluster_name, ar.rating, COUNT(DISTINCT ar.pmid) AS n
        FROM audit_ratings ar
        JOIN cluster_assignments ca
            ON ca.pmid = ar.pmid AND ca.cluster_run_id = ?
        JOIN clusters c
            ON c.cluster_run_id = ca.cluster_run_id AND c.cluster_id = ca.cluster_id
        WHERE ar.dimension = ?
              {filter_clause}
        GROUP BY c.cluster_name, ar.rating
        ORDER BY c.cluster_name, ar.rating
    """
    rows = con.execute(q, (cluster_run_id, dimension)).fetchall()
    return f"# {dimension}, cluster_run={cluster_run_id}\n" + _fmt(
        rows, ["cluster_name", "rating", "n"])


def drift(con: sqlite3.Connection, v_old: str, v_new: str) -> str:
    """How many papers got a different rating between two rubric versions?"""
    q = """
        SELECT a.dimension, COUNT(*) AS n_papers,
               SUM(CASE WHEN a.rating <> b.rating THEN 1 ELSE 0 END) AS n_changed
        FROM audit_ratings a
        JOIN audit_ratings b
            ON a.pmid = b.pmid AND a.dimension = b.dimension
        WHERE a.rubric_version = ? AND b.rubric_version = ?
        GROUP BY a.dimension
        ORDER BY a.dimension
    """
    rows = con.execute(q, (v_old, v_new)).fetchall()
    return f"# drift between {v_old} and {v_new}\n" + _fmt(
        rows, ["dimension", "n_papers", "n_changed"])


def rated_papers(con: sqlite3.Connection) -> str:
    """How many distinct papers have ≥1 rating?"""
    total = con.execute("SELECT COUNT(DISTINCT pmid) FROM audit_ratings").fetchone()[0]
    rows = con.execute("""
        SELECT rubric_version, COUNT(DISTINCT pmid)
        FROM audit_ratings GROUP BY rubric_version
    """).fetchall()
    return f"papers with ≥1 rating: {total}\n" + _fmt(rows, ["rubric_version", "n_papers"])


def coverage(con: sqlite3.Connection) -> str:
    """How complete is each paper's audit (out of N dimensions)?"""
    rows = con.execute("""
        SELECT n_dims, COUNT(*) AS n_papers
        FROM (
            SELECT pmid, COUNT(DISTINCT dimension) AS n_dims
            FROM audit_ratings
            GROUP BY pmid
        )
        GROUP BY n_dims
        ORDER BY n_dims DESC
    """).fetchall()
    return _fmt(rows, ["dims_rated", "n_papers"])
