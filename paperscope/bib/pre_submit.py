"""
Pre-submission citation checklist.

Checks DOI coverage, broken references, duplicate citations, missing fields.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set


def pre_submit_main(tex_path: Path, bib_path: Optional[Path] = None) -> int:
    """Run pre-submission checks on a LaTeX manuscript."""
    if not tex_path.exists():
        print(f"Error: {tex_path} not found.")
        return 1

    # Find bibliography.json
    if bib_path is None:
        # Look in parent directories
        for parent in [tex_path.parent, tex_path.parent.parent]:
            candidate = parent / "literature" / "bibliography.json"
            if candidate.exists():
                bib_path = candidate
                break
        if bib_path is None:
            print("Error: No bibliography.json found. Provide with --bib.")
            return 1

    with open(bib_path) as f:
        bib_data = json.load(f)

    refs_by_key = {r["cite_key"]: r for r in bib_data["references"]}

    # Also build lookup by alternate keys
    for ref in bib_data["references"]:
        for alt_key in ref.get("alternate_keys", []):
            if alt_key not in refs_by_key:
                refs_by_key[alt_key] = ref

    # Extract cite keys from .tex file
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    cited_keys: Set[str] = set()
    for match in re.finditer(r"\\(?:cite[tp]?|nocite)\{([^}]+)\}", text):
        for key in match.group(1).split(","):
            key = key.strip()
            if key and key != "*":
                cited_keys.add(key)

    issues: List[str] = []
    warnings: List[str] = []

    # Check 1: Missing references (cited but not in bibliography)
    missing = cited_keys - set(refs_by_key.keys())
    if missing:
        issues.append(f"MISSING REFERENCES ({len(missing)}):")
        for key in sorted(missing):
            issues.append(f"  \\cite{{{key}}} — not found in bibliography")

    # Check 2: DOI coverage for cited references
    cited_refs = [refs_by_key[k] for k in cited_keys if k in refs_by_key]
    with_doi = sum(1 for r in cited_refs if r.get("doi"))
    without_doi = [r for r in cited_refs if not r.get("doi")]

    if without_doi:
        pct = 100 * with_doi // max(len(cited_refs), 1)
        warnings.append(f"DOI COVERAGE: {with_doi}/{len(cited_refs)} ({pct}%)")
        if pct < 80:
            issues.append(f"Low DOI coverage ({pct}%) — resolve before submission")
        for r in without_doi[:10]:
            warnings.append(f"  {r['cite_key']}: {r.get('title', '(no title)')[:60]}")
        if len(without_doi) > 10:
            warnings.append(f"  ... and {len(without_doi) - 10} more")

    # Check 3: Missing titles
    no_title = [r for r in cited_refs if not r.get("title")]
    if no_title:
        issues.append(f"MISSING TITLES ({len(no_title)}):")
        for r in no_title:
            issues.append(f"  {r['cite_key']}")

    # Check 4: Duplicate citations (same DOI cited with different keys)
    doi_to_keys: Dict[str, List[str]] = {}
    for r in cited_refs:
        if r.get("doi"):
            doi_to_keys.setdefault(r["doi"], []).append(r["cite_key"])
    duplicates = {doi: keys for doi, keys in doi_to_keys.items() if len(keys) > 1}
    if duplicates:
        warnings.append(f"DUPLICATE CITATIONS ({len(duplicates)}):")
        for doi, keys in duplicates.items():
            warnings.append(f"  {doi}: {', '.join(keys)}")

    # Print report
    print(f"\n{'='*60}")
    print(f"Pre-Submission Check: {tex_path.name}")
    print(f"{'='*60}")
    print(f"  Citations in manuscript: {len(cited_keys)}")
    print(f"  Found in bibliography:  {len(cited_refs)}")
    print(f"  With DOI:               {with_doi}")

    if issues:
        print(f"\n{'!'*60}")
        print("ISSUES (must fix before submission):")
        for issue in issues:
            print(f"  {issue}")

    if warnings:
        print(f"\n{'~'*60}")
        print("WARNINGS (review before submission):")
        for warning in warnings:
            print(f"  {warning}")

    if not issues and not warnings:
        print("\n  All checks passed.")

    print(f"{'='*60}")

    return 1 if issues else 0
