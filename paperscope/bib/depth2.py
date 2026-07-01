"""Depth-2 reference harvesting via CrossRef.

For each reference with a DOI, queries CrossRef works/{doi} to get
its cited references. Adds new refs to the bibliography as depth-2 entries.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import requests
except ImportError:
    raise ImportError("'requests' package required. Install with: pip install requests")

CROSSREF_API = "https://api.crossref.org/works"
MAILTO = os.environ.get("PAPERSCOPE_EMAIL", "paperscope@example.com")
RATE_LIMIT_DELAY = 0.12  # ~8 req/sec, stay in polite pool


def _make_cite_key(ref: dict) -> str:
    """Generate a cite key from a CrossRef reference entry."""
    author = ref.get("author", "")
    year = ref.get("year", "")

    # Extract first surname
    surname = ""
    if author:
        # "Family, Given" or "Family"
        surname = author.split(",")[0].strip().split()[-1].lower()
        surname = re.sub(r"[^a-z]", "", surname)

    if not surname:
        # Try from unstructured field
        unstructured = ref.get("unstructured", "")
        if unstructured:
            words = unstructured.split()
            for w in words:
                clean = re.sub(r"[^a-zA-Z]", "", w)
                if clean and clean[0].isupper() and len(clean) > 2:
                    surname = clean.lower()
                    break

    if not surname:
        surname = "unknown"

    # Extract year
    if not year:
        year_match = re.search(r"\b(19|20)\d{2}\b", ref.get("unstructured", ""))
        if year_match:
            year = year_match.group()

    return f"d2_{surname}{year}" if year else f"d2_{surname}"


def _parse_crossref_reference(ref: dict) -> dict:
    """Parse a single CrossRef reference entry into our format."""
    doi = ref.get("DOI", "")
    title = ref.get("article-title", "") or ref.get("volume-title", "")
    author = ref.get("author", "")
    year = ref.get("year", "")
    journal = ref.get("journal-title", "")

    # If no structured fields, try to parse from unstructured
    unstructured = ref.get("unstructured", "")
    if unstructured and not title:
        # Common patterns: "Author (year) Title. Journal..."
        # or "Author. Title. Journal vol:pages, year."
        # Just store the raw text — we can parse later
        title = unstructured[:200]

    if not year:
        year_match = re.search(r"\b(19|20)\d{2}\b", unstructured)
        if year_match:
            year = year_match.group()

    cite_key = _make_cite_key(ref)

    return {
        "cite_key": cite_key,
        "title": title,
        "authors": author,
        "year": year,
        "journal": journal,
        "volume": "",
        "number": "",
        "pages": "",
        "doi": doi,
        "publisher": "",
        "entry_type": "",
        "source_file": "",
        "source_format": "crossref_depth2",
        "raw_text": unstructured,
        "url": "",
        "arxiv_id": "",
        "alternate_keys": [],
        "source_files": [],
        "depth": 2,
    }


def fetch_cited_references(
    doi: str,
    session: Optional[requests.Session] = None,
) -> List[dict]:
    """Fetch references cited by a paper via CrossRef.

    Returns list of parsed reference dicts.
    """
    s = session or requests.Session()

    try:
        resp = s.get(
            f"{CROSSREF_API}/{doi}",
            params={"mailto": MAILTO},
            timeout=15,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError):
        return []

    item = data.get("message", {})
    raw_refs = item.get("reference", [])

    parsed = []
    for ref in raw_refs:
        parsed.append(_parse_crossref_reference(ref))

    return parsed


def harvest_depth2(
    data_dir: Path,
    limit: int = 0,
    verbose: bool = True,
) -> int:
    """Harvest depth-2 references for all DOI-resolved refs.

    Args:
        data_dir: Path to literature-data directory
        limit: Max depth-1 refs to process (0 = all)
        verbose: Print progress
    """
    bib_path = data_dir / "bibliography.json"
    with open(bib_path) as f:
        data = json.load(f)

    refs = data["references"]
    depth1_with_doi = [r for r in refs if r.get("doi") and r.get("depth", 1) == 1]

    # Track which depth-1 refs we've already harvested
    harvest_log_path = data_dir / "depth2_harvest_log.json"
    if harvest_log_path.exists():
        with open(harvest_log_path) as f:
            harvest_log = json.load(f)
    else:
        harvest_log = {"harvested_dois": [], "stats": {}}

    already_harvested = set(harvest_log["harvested_dois"])
    to_harvest = [r for r in depth1_with_doi if r["doi"] not in already_harvested]

    if limit > 0:
        to_harvest = to_harvest[:limit]

    if verbose:
        print(f"\n{'='*60}")
        print("Depth-2 Reference Harvesting")
        print(f"{'='*60}")
        print(f"  Depth-1 refs with DOI:   {len(depth1_with_doi)}")
        print(f"  Already harvested:       {len(already_harvested)}")
        print(f"  To harvest this run:     {len(to_harvest)}")

    # Build set of existing DOIs for dedup
    existing_dois = {r["doi"].lower() for r in refs if r.get("doi")}
    existing_titles = {r.get("title", "").lower()[:50] for r in refs if r.get("title")}

    session = requests.Session()
    session.headers["User-Agent"] = f"paperscope/0.1.0 (mailto:{MAILTO})"

    new_refs = []
    total_raw = 0
    dupes_skipped = 0

    for i, ref in enumerate(to_harvest):
        if verbose and (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(to_harvest)}] new refs: {len(new_refs)}, "
                  f"dupes skipped: {dupes_skipped}")

        time.sleep(RATE_LIMIT_DELAY)

        cited = fetch_cited_references(ref["doi"], session=session)
        total_raw += len(cited)

        for c in cited:
            # Skip if already in bibliography
            if c.get("doi") and c["doi"].lower() in existing_dois:
                dupes_skipped += 1
                continue
            if c.get("title") and c["title"].lower()[:50] in existing_titles:
                dupes_skipped += 1
                continue

            # Make cite key unique
            base_key = c["cite_key"]
            counter = 1
            while any(r["cite_key"] == c["cite_key"] for r in refs + new_refs):
                c["cite_key"] = f"{base_key}_{counter}"
                counter += 1

            # Track the parent ref
            c["cited_by"] = ref["cite_key"]

            new_refs.append(c)

            # Update tracking sets
            if c.get("doi"):
                existing_dois.add(c["doi"].lower())
            if c.get("title"):
                existing_titles.add(c["title"].lower()[:50])

        harvest_log["harvested_dois"].append(ref["doi"])

    if verbose:
        print(f"\n  Total raw references found:    {total_raw}")
        print(f"  Duplicates skipped:            {dupes_skipped}")
        print(f"  New depth-2 refs added:        {len(new_refs)}")
        print(f"  With DOIs:                     {sum(1 for r in new_refs if r.get('doi'))}")

    # Add new refs to bibliography
    # Mark existing refs as depth 1 if not already marked
    for r in refs:
        if "depth" not in r:
            r["depth"] = 1

    refs.extend(new_refs)
    data["references"] = refs
    data["metadata"]["total_references"] = len(refs)
    data["metadata"]["depth2_references"] = sum(1 for r in refs if r.get("depth") == 2)

    # Save
    with open(bib_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    harvest_log["stats"] = {
        "total_harvested": len(harvest_log["harvested_dois"]),
        "total_raw_refs": total_raw,
        "total_new_refs": len(new_refs),
        "dupes_skipped": dupes_skipped,
    }
    with open(harvest_log_path, "w", encoding="utf-8") as f:
        json.dump(harvest_log, f, indent=2, ensure_ascii=False)

    if verbose:
        print(f"\n  Bibliography now has {len(refs)} total references")
        print(f"  Saved to {bib_path}")
        print(f"  Harvest log at {harvest_log_path}")

    return 0
