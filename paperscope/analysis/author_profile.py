"""Author profiling and COI pattern detection via OpenAlex."""

from __future__ import annotations

import os
import time
from collections import Counter
from typing import Dict, List, Optional

import requests


OPENALEX_BASE = "https://api.openalex.org"
MAILTO = os.environ.get("PAPERSCOPE_EMAIL", "paperscope@example.com")
RATE_LIMIT_DELAY = 1.0  # 1 request per second for polite pool


# ---------------------------------------------------------------------------
# OpenAlex helpers
# ---------------------------------------------------------------------------

def _oa_get(endpoint: str, params: Optional[Dict] = None) -> Dict:
    """GET from OpenAlex with rate limiting and error handling."""
    params = dict(params or {})
    params.setdefault("mailto", MAILTO)
    time.sleep(RATE_LIMIT_DELAY)
    try:
        resp = requests.get(
            f"{OPENALEX_BASE}/{endpoint}",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        print(f"  [author_profile] OpenAlex request failed: {exc}")
        return {}


def _search_author(name: str) -> Optional[Dict]:
    """Search OpenAlex for an author by name. Return best match or None."""
    data = _oa_get("authors", {"search": name})
    results = data.get("results", [])
    if not results:
        return None
    # Return top result — OpenAlex relevance-ranks by default
    return results[0]


def _get_recent_works(
    author_id: str, n: int = 50
) -> List[Dict]:
    """Fetch an author's recent works from OpenAlex.

    Returns list of simplified work dicts.
    """
    data = _oa_get(
        "works",
        {
            "filter": f"author.id:{author_id}",
            "sort": "publication_year:desc",
            "per_page": min(n, 200),
        },
    )
    works = []
    for w in data.get("results", []):
        works.append({
            "openalex_id": w.get("id", ""),
            "title": w.get("title", ""),
            "year": w.get("publication_year"),
            "doi": w.get("doi", ""),
            "author_ids": [
                a.get("author", {}).get("id", "")
                for a in w.get("authorships", [])
            ],
            "abstract_snippet": _reconstruct_abstract(w)[:300],
        })
    return works


def _reconstruct_abstract(work: Dict) -> str:
    """Reconstruct abstract from OpenAlex inverted index."""
    inverted = work.get("abstract_inverted_index")
    if not inverted:
        return ""
    word_positions = []
    for word, positions in inverted.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def _extract_institution(author_data: Dict) -> str:
    """Extract current institution display name from author record."""
    affiliations = author_data.get("affiliations", [])
    if affiliations:
        for aff in affiliations:
            inst = aff.get("institution", {})
            if inst:
                return inst.get("display_name", "")
    # Fallback: last_known_institution (older API field)
    last = author_data.get("last_known_institution") or {}
    return last.get("display_name", "")


# ---------------------------------------------------------------------------
# COI detection logic
# ---------------------------------------------------------------------------

def _check_method_developer(
    works: List[Dict],
    paper_methods: List[str],
) -> bool:
    """Check if any of the author's works mention the paper's methods.

    Looks for method name substrings in titles and abstract snippets.
    """
    if not paper_methods:
        return False
    for method in paper_methods:
        method_lower = method.lower()
        for w in works:
            title = (w.get("title") or "").lower()
            abstract = (w.get("abstract_snippet") or "").lower()
            if method_lower in title or method_lower in abstract:
                return True
    return False


def _find_shared_prior_works(
    all_author_works: Dict[str, List[Dict]],
    author_names: List[str],
) -> List[Dict]:
    """Find works where 2+ of the listed authors are co-authors.

    Args:
        all_author_works: {author_name: [work_dicts]} mapping.
        author_names: Names of authors being profiled.

    Returns:
        List of shared work dicts with metadata.
    """
    # Build mapping: openalex_author_id -> author_name
    # (We need author OpenAlex IDs from each author's profile, stored separately)
    # Instead, index works by OpenAlex work ID and track which profiled authors appear
    work_index: Dict[str, Dict] = {}  # work_openalex_id -> work_dict
    work_authors: Dict[str, List[str]] = {}  # work_openalex_id -> [author_names]

    for author_name, works in all_author_works.items():
        for w in works:
            wid = w.get("openalex_id", "")
            if not wid:
                continue
            if wid not in work_index:
                work_index[wid] = w
                work_authors[wid] = []
            if author_name not in work_authors[wid]:
                work_authors[wid].append(author_name)

    shared = []
    for wid, authors in work_authors.items():
        if len(authors) >= 2:
            w = work_index[wid]
            shared.append({
                "title": w.get("title", ""),
                "year": w.get("year"),
                "doi": w.get("doi", ""),
                "shared_authors": authors,
            })

    # Sort by year descending
    shared.sort(key=lambda x: x.get("year") or 0, reverse=True)
    return shared


def _assess_institutional_concentration(
    author_profiles: List[Dict],
) -> str:
    """Assess how many authors share the same institution."""
    institutions = [
        p["institution"]
        for p in author_profiles
        if p.get("institution")
    ]
    if not institutions:
        return "unknown (no institution data)"
    counts = Counter(institutions)
    most_common_inst, most_common_count = counts.most_common(1)[0]
    total = len(author_profiles)
    return f"{most_common_count}/{total} from {most_common_inst}"


def _assess_self_validation_risk(
    author_profiles: List[Dict],
) -> str:
    """Assess whether any author developed a method used in the paper."""
    developers = [p["name"] for p in author_profiles if p.get("method_developer")]
    if not developers:
        return "low"
    if len(developers) >= 2:
        return "high"
    return "medium"


def _assess_position_entrenchment(
    all_author_works: Dict[str, List[Dict]],
    paper_topic: Optional[str],
) -> str:
    """Assess whether authors have extensive prior publication on the same topic.

    Checks how many of each author's recent works have title overlap
    with the paper's topic string.
    """
    if not paper_topic:
        return "unknown (no topic provided)"

    topic_words = set(paper_topic.lower().split())
    # Remove stop words
    stop = {"the", "a", "an", "of", "in", "on", "for", "and", "or", "to", "is", "with"}
    topic_words -= stop
    if not topic_words:
        return "unknown (topic too generic)"

    authors_with_prior = 0
    total_authors = len(all_author_works)

    for author_name, works in all_author_works.items():
        topic_hits = 0
        for w in works:
            title = (w.get("title") or "").lower()
            title_words = set(title.split())
            overlap = topic_words & title_words
            if len(overlap) >= 2:
                topic_hits += 1
        if topic_hits >= 3:
            authors_with_prior += 1

    if total_authors == 0:
        return "unknown"
    ratio = authors_with_prior / total_authors
    if ratio >= 0.5:
        return "high"
    elif ratio >= 0.25:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def profile_authors(
    author_names: List[str],
    paper_methods: Optional[List[str]] = None,
    paper_topic: Optional[str] = None,
) -> Dict:
    """Look up authors via OpenAlex and flag COI patterns.

    Args:
        author_names: Author names as extracted from the manuscript.
        paper_methods: Method names used in the paper (for self-validation check).
        paper_topic: Topic string (for position entrenchment check).

    Returns:
        Dict with ``authors`` list and ``team_assessment`` summary.
    """
    paper_methods = paper_methods or []
    author_profiles: List[Dict] = []
    all_author_works: Dict[str, List[Dict]] = {}

    for name in author_names:
        print(f"  Looking up: {name}")
        author_data = _search_author(name)

        if author_data is None:
            author_profiles.append({
                "name": name,
                "openalex_id": None,
                "institution": None,
                "works_count": 0,
                "cited_by_count": 0,
                "recent_works": [],
                "method_developer": False,
                "coi_flags": ["not_found_in_openalex"],
            })
            all_author_works[name] = []
            continue

        oa_id = author_data.get("id", "")
        institution = _extract_institution(author_data)
        works_count = author_data.get("works_count", 0)
        cited_by_count = author_data.get("cited_by_count", 0)

        # Fetch recent works
        recent_works = _get_recent_works(oa_id, n=50) if oa_id else []
        all_author_works[name] = recent_works

        # Check method developer status
        is_method_dev = _check_method_developer(recent_works, paper_methods)

        # Build COI flags for this author
        coi_flags: List[str] = []
        if is_method_dev:
            coi_flags.append("method_developer")

        # Trim recent_works for output (keep top 10)
        output_works = [
            {"title": w["title"], "year": w["year"], "doi": w["doi"]}
            for w in recent_works[:10]
        ]

        author_profiles.append({
            "name": name,
            "openalex_id": oa_id,
            "institution": institution,
            "works_count": works_count,
            "cited_by_count": cited_by_count,
            "recent_works": output_works,
            "method_developer": is_method_dev,
            "coi_flags": coi_flags,
        })

    # --- Team-level assessment ---

    # Institutional concentration
    institutional_concentration = _assess_institutional_concentration(author_profiles)

    # Self-validation risk
    self_validation_risk = _assess_self_validation_risk(author_profiles)

    # Shared prior works (co-authored papers among the author set)
    shared_prior_works = _find_shared_prior_works(all_author_works, author_names)

    # Position entrenchment
    position_entrenchment_risk = _assess_position_entrenchment(
        all_author_works, paper_topic
    )

    # Add team-level COI flags back to individual authors
    # Flag authors who share many prior co-publications
    coauthor_counts: Counter = Counter()
    for spw in shared_prior_works:
        for a in spw["shared_authors"]:
            coauthor_counts[a] += 1
    for profile in author_profiles:
        if coauthor_counts.get(profile["name"], 0) >= 5:
            profile["coi_flags"].append("extensive_coauthor_history")

    team_assessment = {
        "institutional_concentration": institutional_concentration,
        "self_validation_risk": self_validation_risk,
        "shared_prior_works": shared_prior_works[:20],  # cap output
        "position_entrenchment_risk": position_entrenchment_risk,
    }

    return {
        "authors": author_profiles,
        "team_assessment": team_assessment,
    }
