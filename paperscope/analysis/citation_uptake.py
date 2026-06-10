"""Citation-uptake / independent-replication checker via OpenAlex.

Answers one question a referee otherwise has to answer by hand: *has anyone
who is **not** an author actually built on this result?* A keystone claim with
many citations that are all self-citations has, in practice, zero independent
uptake. The decisive finding in one review was exactly this — a headline result
with zero independent citations two years after publication, found by hand.
This makes it a one-command check.

"Independent" = cited by a work whose author set is disjoint from the original
paper's author set. Self-citations (any shared author id) do not count as uptake.

Network: reuses ``author_profile._oa_get`` (polite-pool ``mailto``, rate limit,
error handling). One work fetch + one page of citing works.

CLI: ``python3 -m paperscope.analysis.citation_uptake <doi>``
"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional

from . import author_profile


# A page of citing works to classify. OpenAlex caps per_page at 200; one page
# is enough to decide independent-vs-self uptake for the low-citation regime
# this check is built for (and to sample titles in any regime).
CITING_PAGE_SIZE = 200

# Below this many independent citations we flag "low_uptake" (zero is flagged
# separately as the stronger "zero_independent_uptake").
LOW_UPTAKE_THRESHOLD = 3


def _normalize_doi(doi: str) -> str:
    """Strip a doi.org URL prefix and surrounding whitespace; lowercase."""
    d = (doi or "").strip()
    for prefix in ("https://doi.org/", "http://doi.org/",
                   "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if d.lower().startswith(prefix):
            d = d[len(prefix):]
            break
    return d.strip().lower()


def _work_author_ids(work: Dict) -> List[str]:
    """Extract the OpenAlex author ids from a work's authorships (null-safe)."""
    ids: List[str] = []
    for a in work.get("authorships") or []:
        author = (a or {}).get("author") or {}
        aid = author.get("id")
        if aid:
            ids.append(aid)
    return ids


def _fetch_work_by_doi(doi: str) -> Optional[Dict]:
    """Resolve an OpenAlex work by DOI. Returns the work dict or None."""
    doi_norm = _normalize_doi(doi)
    if not doi_norm:
        return None
    # The doi: path form is the documented way to look up a work by DOI.
    data = author_profile._oa_get(f"works/doi:{doi_norm}")
    # A successful lookup is a single work object (has an "id"); a failed/empty
    # call returns {} (see _oa_get's error path).
    if data.get("id"):
        return data
    return None


def _fetch_citing_works(work_id: str) -> List[Dict]:
    """Fetch one page of works that cite ``work_id`` (the OpenAlex id)."""
    if not work_id:
        return []
    data = author_profile._oa_get(
        "works",
        {
            "filter": f"cites:{work_id}",
            "per_page": CITING_PAGE_SIZE,
        },
    )
    return data.get("results", []) or []


def check_uptake(
    doi: str,
    original_author_ids: Optional[List[str]] = None,
    client=None,
) -> Dict:
    """Check independent citation uptake of a published work.

    Args:
        doi: DOI of the original paper (bare or doi.org URL).
        original_author_ids: OpenAlex author ids of the original paper's
            authors. If ``None``, derived from the resolved work's authorships.
        client: Unused placeholder for API symmetry with other analysis
            entry points; HTTP goes through ``author_profile._oa_get``.

    Returns:
        Dict with the resolved work, citation counts split into independent
        vs self, a small sample of citing works, and ``flags``.
    """
    result: Dict = {
        "doi": doi,
        "work_id": None,
        "title": None,
        "year": None,
        "cited_by_count": 0,
        "independent_cited_by_count": 0,
        "self_cited_by_count": 0,
        "sample_citing": [],
        "flags": [],
    }

    work = _fetch_work_by_doi(doi)
    if work is None:
        result["flags"].append("work_not_found")
        return result

    result["work_id"] = work.get("id")
    result["title"] = work.get("title")
    result["year"] = work.get("publication_year")
    result["cited_by_count"] = work.get("cited_by_count", 0) or 0

    # Original author set: provided, else derived from the resolved work.
    if original_author_ids is None:
        original_author_ids = _work_author_ids(work)
    original_set = {a for a in original_author_ids if a}

    # cited_by_count == 0: no need to page citing works.
    if result["cited_by_count"] == 0:
        result["flags"].append("zero_independent_uptake")
        return result

    citing = _fetch_citing_works(result["work_id"])

    independent = 0
    self_cites = 0
    sample: List[Dict] = []
    for cw in citing:
        cw_authors = set(_work_author_ids(cw))
        is_self = bool(original_set) and bool(cw_authors & original_set)
        if is_self:
            self_cites += 1
        else:
            independent += 1
        if len(sample) < 5:
            sample.append({
                "id": cw.get("id"),
                "title": cw.get("title"),
                "year": cw.get("publication_year"),
                "independent": not is_self,
            })

    result["independent_cited_by_count"] = independent
    result["self_cited_by_count"] = self_cites
    result["sample_citing"] = sample

    # Flags. If no original author set could be established, we cannot classify
    # self vs independent — say so rather than imply independence.
    if not original_set:
        result["flags"].append("no_author_set_unable_to_classify")
    elif independent == 0:
        result["flags"].append("zero_independent_uptake")
    elif independent < LOW_UPTAKE_THRESHOLD:
        result["flags"].append("low_uptake")

    return result


def _print_report(report: Dict) -> None:
    print(f"\n{'='*60}")
    print("Citation Uptake Report")
    print(f"{'='*60}")
    print(f"  DOI:                 {report['doi']}")
    print(f"  Work:                {report.get('title') or '(not resolved)'}")
    print(f"  OpenAlex id:         {report.get('work_id') or '-'}")
    print(f"  Year:                {report.get('year') or '-'}")
    print(f"  cited_by_count:      {report['cited_by_count']}")
    print(f"  independent cites:   {report['independent_cited_by_count']}")
    print(f"  self cites:          {report['self_cited_by_count']}")
    if report["sample_citing"]:
        print("  sample citing works:")
        for c in report["sample_citing"]:
            tag = "indep" if c["independent"] else "self "
            print(f"    [{tag}] ({c.get('year') or '----'}) {c.get('title') or c.get('id')}")
    flags = report["flags"]
    print(f"  flags:               {', '.join(flags) if flags else '(none)'}")
    print(f"{'='*60}")


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in {"-h", "--help"}:
        print("usage: python3 -m paperscope.analysis.citation_uptake <doi>")
        return 0 if argv else 1
    report = check_uptake(argv[0])
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
