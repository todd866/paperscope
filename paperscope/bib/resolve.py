"""
DOI resolver for bibliography databases.

Queries CrossRef API to find DOIs for references that don't have them.
Rate-limited to the "polite pool" (50 req/sec with mailto header).
"""

import json
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    raise ImportError("'requests' package required. Install with: pip install requests")

CROSSREF_API = "https://api.crossref.org/works"
MAILTO = os.environ.get("PAPERSCOPE_EMAIL", "paperscope@example.com")
RATE_LIMIT_DELAY = 0.1  # 10 req/sec


def clean_for_query(text: str) -> str:
    """Clean a string for use in CrossRef API queries."""
    text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)
    text = re.sub(r"[{}$\\]", "", text)
    text = re.sub(r"--", "-", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def query_crossref(
    title: str,
    authors: str = "",
    year: str = "",
    session: Optional[requests.Session] = None,
) -> Optional[Dict]:
    """Query CrossRef for a reference and return the best match.

    Returns dict with: doi, cr_title, cr_year, score, cr_authors, or None.
    """
    s = session or requests.Session()

    clean_title = clean_for_query(title)
    if not clean_title:
        return None

    params = {
        "query.bibliographic": clean_title,
        "rows": 3,
        "mailto": MAILTO,
    }

    if authors:
        clean_auth = clean_for_query(authors)
        surname = ""
        if "," in clean_auth:
            surname = clean_auth.split(",")[0].strip()
        elif re.match(r"[A-Z]\.\s", clean_auth):
            parts = clean_auth.split()
            for p in parts:
                if not re.match(r"^[A-Z]\.$", p) and len(p) > 2:
                    surname = p
                    break
        else:
            surname = clean_auth.split()[0] if clean_auth else ""

        if surname and len(surname) > 2:
            params["query.author"] = surname

    try:
        resp = s.get(CROSSREF_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError):
        return None

    items = data.get("message", {}).get("items", [])
    if not items:
        return None

    best = None
    best_score = 0.0

    for item in items[:3]:
        cr_title = " ".join(item.get("title", [""]))
        cr_year = str(
            item.get("published-print", item.get("published-online", {}))
            .get("date-parts", [[""]])[0][0]
        )
        cr_doi = item.get("DOI", "")

        title_sim = SequenceMatcher(
            None, clean_title.lower(), cr_title.lower()
        ).ratio()

        year_bonus = 0.15 if year and cr_year == year else 0.0
        score = title_sim + year_bonus

        if score > best_score:
            best_score = score
            best = {
                "doi": cr_doi,
                "cr_title": cr_title,
                "cr_year": cr_year,
                "score": round(score, 3),
                "cr_authors": _extract_cr_authors(item),
            }

    if best and best["score"] >= 0.80:
        return best

    return None


def _extract_cr_authors(item: Dict) -> str:
    """Extract author string from CrossRef item."""
    authors = item.get("author", [])
    if not authors:
        return ""
    parts = []
    for a in authors[:5]:
        family = a.get("family", "")
        given = a.get("given", "")
        if family:
            parts.append(f"{family}, {given}" if given else family)
    result = "; ".join(parts)
    if len(authors) > 5:
        result += " et al."
    return result


def resolve_batch(
    refs: List[Dict],
    session: requests.Session,
    limit: int = 0,
    verbose: bool = True,
) -> Tuple[Dict, Dict]:
    """Resolve DOIs for a batch of references.

    Returns:
        (resolved_keys, stats) where resolved_keys maps cite_key -> {doi, confidence, score}
    """
    stats = {
        "attempted": 0,
        "resolved": 0,
        "ambiguous": 0,
        "not_found": 0,
        "already_had_doi": 0,
        "skipped_no_title": 0,
    }

    to_resolve = []
    for ref in refs:
        if ref.get("doi"):
            stats["already_had_doi"] += 1
            continue
        if not ref.get("title"):
            stats["skipped_no_title"] += 1
            continue
        to_resolve.append(ref)

    if limit > 0:
        to_resolve = to_resolve[:limit]

    total = len(to_resolve)
    if verbose:
        print(f"Resolving DOIs for {total} references...")
        print(f"  (skipped: {stats['already_had_doi']} already have DOI, "
              f"{stats['skipped_no_title']} have no title)")

    resolved_keys = {}

    for i, ref in enumerate(to_resolve):
        stats["attempted"] += 1

        if verbose and (i + 1) % 25 == 0:
            print(f"  [{i+1}/{total}] resolved: {stats['resolved']}, "
                  f"not found: {stats['not_found']}")

        time.sleep(RATE_LIMIT_DELAY)

        result = query_crossref(
            title=ref["title"],
            authors=ref.get("authors", ""),
            year=ref.get("year", ""),
            session=session,
        )

        if result is None:
            stats["not_found"] += 1
            continue

        if result["score"] >= 0.90:
            resolved_keys[ref["cite_key"]] = {
                "doi": result["doi"],
                "confidence": "high",
                "score": result["score"],
            }
            stats["resolved"] += 1
        elif result["score"] >= 0.80:
            resolved_keys[ref["cite_key"]] = {
                "doi": result["doi"],
                "confidence": "medium",
                "score": result["score"],
            }
            stats["resolved"] += 1
            stats["ambiguous"] += 1
        else:
            stats["not_found"] += 1

    return resolved_keys, stats


def resolve_main(
    bibliography_path: Path,
    dry_run: bool = False,
    limit: int = 0,
    verbose: bool = True,
) -> int:
    """Main entry point for DOI resolution."""
    if not bibliography_path.exists():
        print(f"Error: {bibliography_path} not found. Run extract first.")
        return 1

    with open(bibliography_path) as f:
        data = json.load(f)

    refs = data["references"]

    session = requests.Session()
    session.headers["User-Agent"] = f"paperscope/0.1.0 (mailto:{MAILTO})"

    resolved_keys, stats = resolve_batch(
        refs, session, limit=limit, verbose=verbose
    )

    # Apply resolved DOIs
    updated = 0
    for ref in refs:
        key = ref["cite_key"]
        if key in resolved_keys:
            ref["doi"] = resolved_keys[key]["doi"]
            updated += 1

    data["metadata"]["with_doi"] = sum(1 for r in refs if r.get("doi"))
    data["metadata"]["doi_resolution"] = {
        "attempted": stats["attempted"],
        "resolved": stats["resolved"],
        "ambiguous": stats["ambiguous"],
        "not_found": stats["not_found"],
    }

    if verbose:
        total = len(refs)
        with_doi = data["metadata"]["with_doi"]
        print(f"\n{'='*60}")
        print("DOI Resolution Report")
        print(f"{'='*60}")
        print(f"  Attempted:     {stats['attempted']}")
        print(f"  Resolved:      {stats['resolved']} "
              f"({stats['resolved'] - stats['ambiguous']} high, "
              f"{stats['ambiguous']} medium confidence)")
        print(f"  Not found:     {stats['not_found']}")
        print(f"  Already had:   {stats['already_had_doi']}")
        print(f"  Total DOI now: {with_doi}/{total} ({100*with_doi//total}%)")
        print(f"{'='*60}")

    if dry_run:
        print("\n[DRY RUN] No changes saved.")
        for key, info in list(resolved_keys.items())[:20]:
            print(f"  {key}: {info['doi']} (score={info['score']})")
        if len(resolved_keys) > 20:
            print(f"  ... and {len(resolved_keys) - 20} more")
        return 0

    with open(bibliography_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nUpdated {updated} references in {bibliography_path}")

    log_path = bibliography_path.parent / "doi_resolution_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(resolved_keys, f, indent=2, ensure_ascii=False)
    print(f"Resolution log saved to {log_path}")

    missing_path = bibliography_path.parent / "missing_dois.json"
    missing = [
        {"cite_key": r["cite_key"], "title": r["title"],
         "authors": r.get("authors", ""), "year": r.get("year", "")}
        for r in refs
        if not r.get("doi") and r.get("title")
    ]
    with open(missing_path, "w", encoding="utf-8") as f:
        json.dump(missing, f, indent=2, ensure_ascii=False)
    print(f"Updated {missing_path} ({len(missing)} refs still need DOIs)")

    return 0
