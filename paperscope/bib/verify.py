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
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    raise ImportError("'requests' package required. Install with: pip install requests")

CROSSREF_API = "https://api.crossref.org/works"
MAILTO = os.environ.get("PAPERSCOPE_EMAIL", "paperscope@example.com")
RATE_LIMIT_DELAY = 0.15

# Crossref records corrections/retractions in the "update-to" field. We classify
# beyond the plain "retraction" type the original code matched, since withdrawals,
# removals, expressions of concern, and corrections all matter to a reviewer
# checking whether a cited reference still stands.
_RETRACT_TYPES = {"retraction", "partial_retraction", "withdrawal", "removal"}
_CONCERN_TYPES = {"expression_of_concern", "expression-of-concern"}
_CORRECTION_TYPES = {"correction", "corrigendum", "erratum", "addendum", "clarification"}


def load_retraction_watch(csv_path: Optional[str] = None) -> Optional[Dict[str, str]]:
    """Load the Retraction Watch database CSV into a ``{doi_lower: nature}`` index.

    Crossref's ``update-to`` field is incomplete; the Retraction Watch dataset
    (free, distributed via Crossref since 2023) catches retractions and
    expressions of concern that Crossref misses. Opt-in: pass a path or set the
    ``RETRACTION_WATCH_CSV`` env var. Returns ``None`` when no CSV is
    configured/found, so callers degrade gracefully to the Crossref-only check.
    """
    path = csv_path or os.environ.get("RETRACTION_WATCH_CSV")
    if not path or not Path(path).is_file():
        return None
    import csv as _csv

    index: Dict[str, str] = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        for row in _csv.DictReader(fh):
            doi = (row.get("OriginalPaperDOI") or "").strip().lower()
            nature = (row.get("RetractionNature") or "").strip()
            if doi and doi != "unavailable":
                index[doi] = nature
    return index


def check_retraction(item: Dict, rw_index: Optional[Dict[str, str]] = None):
    """Classify a Crossref item's correction/retraction status.

    Checks the ``update-to`` types (broadened beyond plain "retraction") and,
    when a Retraction Watch index is supplied, cross-checks it by DOI.

    Returns ``(status, detail)`` with status in {"retracted", "concern",
    "corrected"}, or ``None`` if the item is clean.
    """
    found: Dict[str, str] = {}
    for update in item.get("update-to") or []:
        t = (update.get("type") or "").strip().lower()
        if t in _RETRACT_TYPES:
            found["retracted"] = t
        elif t in _CONCERN_TYPES:
            found.setdefault("concern", t)
        elif t in _CORRECTION_TYPES:
            found.setdefault("corrected", t)

    if rw_index is not None:
        nature = rw_index.get((item.get("DOI") or "").strip().lower())
        if nature:
            n = nature.lower()
            if "retraction" in n:
                found["retracted"] = f"RetractionWatch: {nature}"
            elif "concern" in n:
                found.setdefault("concern", f"RetractionWatch: {nature}")
            elif "correction" in n or "erratum" in n:
                found.setdefault("corrected", f"RetractionWatch: {nature}")

    if "retracted" in found:
        return ("retracted", f"RETRACTED ({found['retracted']})")
    if "concern" in found:
        return ("concern", f"EXPRESSION OF CONCERN ({found['concern']})")
    if "corrected" in found:
        return ("corrected", f"correction/erratum ({found['corrected']})")
    return None


def verify_doi(
    doi: str,
    ref: Dict,
    session: requests.Session,
    rw_index: Optional[Dict[str, str]] = None,
) -> Dict:
    """Verify a single DOI against CrossRef metadata.

    Returns a verification result dict with:
        - status: "ok", "mismatch", "retracted", "concern", "corrected",
          "not_found", or "error"
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

    # Check correction / retraction status (Crossref update-to, broadened, plus
    # the optional Retraction Watch cross-check).
    retr = check_retraction(item, rw_index)
    if retr is not None:
        rstatus, rdetail = retr
        if rstatus in ("retracted", "concern"):
            # A retraction or expression of concern dominates any title/year issue.
            return {"status": rstatus, "details": "; ".join([rdetail] + issues)}
        # A correction/erratum is worth surfacing but is not itself a fault.
        return {"status": "corrected", "details": "; ".join([rdetail] + issues)}

    if issues:
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

    rw_index = load_retraction_watch()
    if rw_index is not None:
        print(f"Retraction Watch index loaded ({len(rw_index)} DOIs).")

    results = {"ok": 0, "mismatch": 0, "retracted": 0, "concern": 0,
               "corrected": 0, "not_found": 0, "error": 0}
    issues: List[Dict] = []

    print(f"Verifying {len(refs_with_doi)} DOIs against CrossRef...")

    for i, ref in enumerate(refs_with_doi):
        if (i + 1) % 25 == 0:
            print(f"  [{i+1}/{len(refs_with_doi)}] verified: {results['ok']}, "
                  f"issues: {results['mismatch']}")

        time.sleep(RATE_LIMIT_DELAY)

        result = verify_doi(ref["doi"], ref, session, rw_index)
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
    print(f"  Concern:     {results['concern']}")
    print(f"  Corrected:   {results['corrected']}")
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
