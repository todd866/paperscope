"""Rubric loader.

A rubric is a markdown document with operational definitions for each
dimension + a paper-type dispatch table. This module loads the markdown and
exposes its metadata (version, dimensions, paper-types) as Python objects.

In practice the markdown IS the rubric — it's what AI sub-agents read when
applying the rubric to a paper. The loader exists for programmatic access to
the metadata only (e.g., to register the version in `rubric_versions`).

Usage:
    from paperscope.systematic_review.methodological_audit.rubric import (
        load_rubric_metadata, register_rubric,
    )
    meta = load_rubric_metadata("rubric-v0.1.md")
    register_rubric(con, meta)
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class RubricMetadata:
    version: str
    path: Path
    authored_at: str | None = None
    dimensions: list[str] | None = None
    paper_types: list[str] | None = None
    notes: str = ""


def load_rubric_metadata(rubric_md_path: str | Path) -> RubricMetadata:
    """Best-effort parse of a rubric markdown file. Extracts:
        - version from filename (rubric-v0.X.md → 'v0.X')
        - authored_at from a `**Authored:**` or first ISO date in the doc
        - dimensions from `## Dimension N — <name>` headings
        - paper-types from a `## Paper-type dispatch` table

    All fields are optional — if the rubric uses a different convention, the
    metadata fields will be None and the caller can fill them in."""
    path = Path(rubric_md_path)
    text = path.read_text() if path.exists() else ""
    m = re.search(r"rubric-(v\d+\.\d+)", path.name)
    version = m.group(1) if m else "unknown"
    auth = None
    am = re.search(r"\*\*Authored:?\*\*\s*([^\n]+)", text, re.IGNORECASE)
    if am:
        auth = am.group(1).strip()
    else:
        am = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        if am:
            auth = am.group(1)
    # Dimensions: lines like "## Dimension N — Name" or "## Construct adequacy"
    dims: list[str] = []
    for m in re.finditer(r"^## (?:Dimension \d+ — )?([A-Za-z][\w ]+?)\s*$", text, re.MULTILINE):
        name = m.group(1).strip().lower().replace(" ", "_")
        if name in {"the_four_point_scale", "paper_type_dispatch", "what_goes_in_the_database_per_paper",
                    "known_weaknesses_of_v01_to_revisit_at_l1", "migration_plan",
                    "what_v02_does_not_change", "open_questions_for_v03_anticipate_from_l3",
                    "other_operational_guidance_carried_from_v01", "changes_from_v01_numbered"}:
            continue
        dims.append(name)
    return RubricMetadata(
        version=version,
        path=path,
        authored_at=auth,
        dimensions=dims or None,
    )


def register_rubric(con: sqlite3.Connection, meta: RubricMetadata,
                    changelog: str = "", notes: str = "") -> None:
    """Insert (or replace) a rubric_versions row. Pair this with a
    `superseded_at` update on the prior version if this is a successor."""
    con.execute("""
        INSERT OR REPLACE INTO rubric_versions
            (rubric_version, authored_at, changelog, notes)
        VALUES (?, ?, ?, ?)
    """, (
        meta.version,
        meta.authored_at or datetime.now().strftime("%Y-%m-%d"),
        changelog,
        notes or f"See {meta.path.name} for operational definitions.",
    ))
    con.commit()
