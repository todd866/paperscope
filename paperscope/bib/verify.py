"""
Verification of resolved DOIs against CrossRef metadata.

Checks for title mismatches, year discrepancies, and retracted papers.
"""

import json
import os
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List

try:
    import requests
except ImportError:
    raise ImportError("'requests' package required. Install with: pip install requests")

CROSSREF_API = "https://api.crossref.org/works"
MAILTO = os.environ.get("PAPERSCOPE_EMAIL", "paperscope@example.com")
RATE_LIMIT_DELAY = 0.15


def verify_doi(doi: str, ref: Dict, session: requests.Session) -> Dict:
    """Verify a single DOI against CrossRef metadata.

    Returns a verification result dict with:
        - status: "ok", "mismatch", "retracted", "not_found"
        - details: description of any issues
    """
    try:
        resp = session.get(
            f"{CROSSREF_API}/{doi}",
            params={"mailto": MAILTO},
            timeout=15,
        )
        if resp.status_code == 404:
            return {"status": "not_found", "details": f"DOI {doi} not found in CrossRef"}
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {"status": "error", "details": str(e)}

    item = data.get("message", {})
    issues = []

    # Check title match
    cr_title = " ".join(item.get("title", [""]))
    ref_title = ref.get("title", "")
    if ref_title and cr_title:
        clean_ref = re.sub(r"[{}\\$]", "", ref_title).lower().strip()
        clean_cr = cr_title.lower().strip()
        sim = SequenceMatcher(None, clean_ref, clean_cr).ratio()
        if sim < 0.70:
            issues.append(f"title mismatch (similarity={sim:.2f}): "
                         f"ours='{ref_title[:60]}' vs cr='{cr_title[:60]}'")

    # Check year match
    cr_year = str(
        item.get("published-print", item.get("published-online", {}))
        .get("date-parts", [[""]])[0][0]
    )
    ref_year = ref.get("year", "")
    if ref_year and cr_year and ref_year != cr_year:
        issues.append(f"year mismatch: ours={ref_year} vs cr={cr_year}")

    # Check for retraction
    if item.get("update-to"):
        for update in item["update-to"]:
            if update.get("type") == "retraction":
                issues.append("RETRACTED")

    if issues:
        # Retraction takes priority over other issues
        if any("RETRACTED" in i for i in issues):
            return {"status": "retracted", "details": "; ".join(issues)}
        return {"status": "mismatch", "details": "; ".join(issues)}
    return {"status": "ok", "details": "verified"}


def verify_main(bibliography_path: Path, limit: int = 0) -> int:
    """Main entry point for DOI verification."""
    if not bibliography_path.exists():
        print(f"Error: {bibliography_path} not found.")
        return 1

    with open(bibliography_path) as f:
        data = json.load(f)

    refs_with_doi = [r for r in data["references"] if r.get("doi")]
    if limit > 0:
        refs_with_doi = refs_with_doi[:limit]

    session = requests.Session()
    session.headers["User-Agent"] = f"paperscope/0.1.0 (mailto:{MAILTO})"

    results = {"ok": 0, "mismatch": 0, "retracted": 0, "not_found": 0, "error": 0}
    issues: List[Dict] = []

    print(f"Verifying {len(refs_with_doi)} DOIs against CrossRef...")

    for i, ref in enumerate(refs_with_doi):
        if (i + 1) % 25 == 0:
            print(f"  [{i+1}/{len(refs_with_doi)}] verified: {results['ok']}, "
                  f"issues: {results['mismatch']}")

        time.sleep(RATE_LIMIT_DELAY)

        result = verify_doi(ref["doi"], ref, session)
        status = result["status"]
        results[status] = results.get(status, 0) + 1

        if status != "ok":
            issues.append({
                "cite_key": ref["cite_key"],
                "doi": ref["doi"],
                **result,
            })

    print(f"\n{'='*60}")
    print("DOI Verification Report")
    print(f"{'='*60}")
    print(f"  Verified:    {results['ok']}")
    print(f"  Mismatch:    {results['mismatch']}")
    print(f"  Retracted:   {results['retracted']}")
    print(f"  Not found:   {results['not_found']}")
    print(f"  Errors:      {results['error']}")
    print(f"{'='*60}")

    if issues:
        print(f"\nIssues found:")
        for issue in issues:
            print(f"  {issue['cite_key']}: {issue['details']}")

    # Save issues report
    report_path = bibliography_path.parent / "verification_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"summary": results, "issues": issues}, f, indent=2)
    print(f"\nReport saved to {report_path}")

    return 0
