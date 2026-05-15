"""PRISMA-ScR flow counts from raw records + screening decisions.

Produces the standard funnel numbers a scoping review must report:

    Identified                — total records harvested (across databases)
    Duplicates removed        — by PMID / DOI / normalised title
    Title/abstract screened   — identified - duplicates
    Excluded at title/abstract
    Included for charting     — screened - excluded - maybe
    Flagged "maybe" (full-text needed)
    Included after full-text  — (if a full-text screen has been done)

For a multi-database review, pass per-database records lists and let this
module dedup; for a single-database review, pass one list.
"""

from __future__ import annotations

import re
from typing import Iterable


def _norm_title(t: str) -> str:
    """Aggressive normalisation for cross-database title matching."""
    if not t:
        return ""
    t = re.sub(r"[^a-z0-9 ]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


def dedup(records_per_database: dict[str, list[dict]]) -> tuple[list[dict], dict]:
    """Cross-database dedup of records.

    Match priority: PMID → DOI (lowercased) → normalised title. Returns
    (deduped_records, stats) where stats counts duplicates per database.
    """
    seen_pmid: set[str] = set()
    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    out: list[dict] = []
    stats = {
        "by_database": {},
        "duplicates_removed": 0,
    }
    for db, records in records_per_database.items():
        kept = 0
        dups = 0
        for r in records:
            pmid = (r.get("pmid") or "").strip()
            doi = (r.get("doi") or "").strip().lower()
            ntitle = _norm_title(r.get("title", ""))
            if pmid and pmid in seen_pmid:
                dups += 1
                continue
            if doi and doi in seen_doi:
                dups += 1
                continue
            if ntitle and ntitle in seen_title:
                dups += 1
                continue
            if pmid:
                seen_pmid.add(pmid)
            if doi:
                seen_doi.add(doi)
            if ntitle:
                seen_title.add(ntitle)
            r = dict(r)
            r.setdefault("_source_db", db)
            out.append(r)
            kept += 1
        stats["by_database"][db] = {"records": len(records), "kept": kept, "dup": dups}
        stats["duplicates_removed"] += dups
    return out, stats


def prisma_flow(
    *,
    records_per_database: dict[str, list[dict]] | None = None,
    records: list[dict] | None = None,
    screening: Iterable[dict] | None = None,
    full_text_screening: Iterable[dict] | None = None,
) -> dict:
    """Compute the PRISMA-ScR funnel.

    Inputs:
      - `records_per_database`: per-database raw records (for dedup), OR
      - `records`: already-deduplicated records (single-database review)
      - `screening`: title/abstract decisions, each row with `decision` in
        {include, exclude, maybe} and optionally `reason`
      - `full_text_screening`: optional full-text-stage decisions

    Output keys mirror the PRISMA-ScR diagram nodes.
    """
    flow: dict = {}
    if records_per_database is not None:
        deduped, dedup_stats = dedup(records_per_database)
        flow["identified_per_database"] = {
            db: len(rs) for db, rs in records_per_database.items()
        }
        flow["identified_total"] = sum(len(rs) for rs in records_per_database.values())
        flow["duplicates_removed"] = dedup_stats["duplicates_removed"]
        flow["dedup_detail"] = dedup_stats["by_database"]
        flow["screened"] = len(deduped)
    elif records is not None:
        flow["identified_total"] = len(records)
        flow["duplicates_removed"] = 0
        flow["screened"] = len(records)
    else:
        flow["screened"] = 0

    if screening is not None:
        decisions = list(screening)
        included = sum(1 for d in decisions if d.get("decision") == "include")
        excluded = sum(1 for d in decisions if d.get("decision") == "exclude")
        maybe = sum(1 for d in decisions if d.get("decision") == "maybe")
        flow["screened_decisions"] = len(decisions)
        flow["included_for_charting"] = included
        flow["excluded_at_title_abstract"] = excluded
        flow["maybe_full_text_needed"] = maybe
        # Top exclusion reasons (free-text, normalised lightly)
        from collections import Counter

        reasons = Counter(
            re.sub(r"\s+", " ", (d.get("reason") or "").strip().lower())
            for d in decisions
            if d.get("decision") == "exclude"
        )
        flow["top_exclusion_reasons"] = reasons.most_common(20)

    if full_text_screening is not None:
        ft = list(full_text_screening)
        ft_included = sum(1 for d in ft if d.get("decision") == "include")
        ft_excluded = sum(1 for d in ft if d.get("decision") == "exclude")
        flow["full_text_assessed"] = len(ft)
        flow["included_after_full_text"] = ft_included
        flow["excluded_at_full_text"] = ft_excluded

    return flow
