"""Open access PDF acquisition via Unpaywall and arXiv."""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

try:
    import requests
except ImportError:
    raise ImportError("'requests' package required. Install with: pip install requests")

UNPAYWALL_API = "https://api.unpaywall.org/v2"
MAILTO = os.environ.get("PAPERSCOPE_EMAIL", "paperscope@example.com")
RATE_LIMIT_DELAY = 0.2  # 5 req/sec


def check_unpaywall(doi: str, session: Optional[requests.Session] = None) -> Optional[str]:
    """Check Unpaywall for an open access PDF URL.

    Returns the best OA direct PDF URL, or None.
    Only returns url_for_pdf (not landing pages, which can't be downloaded).
    """
    s = session or requests.Session()

    try:
        resp = s.get(
            f"{UNPAYWALL_API}/{doi}",
            params={"email": MAILTO},
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError):
        return None

    # Collect all PDF URLs from all OA locations
    pdf_urls = []

    best = data.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        pdf_urls.append(best["url_for_pdf"])

    for loc in data.get("oa_locations", []):
        url = loc.get("url_for_pdf")
        if url and url not in pdf_urls:
            pdf_urls.append(url)

    # Prefer URLs that look like direct PDF links
    for url in pdf_urls:
        if url.endswith(".pdf") or "/pdf/" in url:
            return url

    # Fall back to any PDF URL
    return pdf_urls[0] if pdf_urls else None


def acquire_oa_pdfs(
    refs: List[Dict],
    output_dir: Path,
    session: Optional[requests.Session] = None,
    limit: int = 0,
    verbose: bool = True,
) -> Dict[str, str]:
    """Acquire open access PDFs for references with DOIs.

    Args:
        refs: List of reference dicts with 'doi' and 'cite_key' fields
        output_dir: Directory to save PDFs
        session: requests Session
        limit: Max to process (0 = all)
        verbose: Print progress

    Returns:
        Dict mapping cite_key -> local PDF path
    """
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", f"paperscope/0.1.0 (mailto:{MAILTO})")

    output_dir.mkdir(parents=True, exist_ok=True)

    with_doi = [r for r in refs if r.get("doi")]
    if limit > 0:
        with_doi = with_doi[:limit]

    if verbose:
        print(f"Checking Unpaywall for {len(with_doi)} references...")

    acquired = {}
    checked = 0
    found = 0

    for ref in with_doi:
        checked += 1
        if verbose and checked % 25 == 0:
            print(f"  [{checked}/{len(with_doi)}] found: {found}")

        time.sleep(RATE_LIMIT_DELAY)

        pdf_url = check_unpaywall(ref["doi"], session=s)
        if not pdf_url:
            continue

        found += 1
        cite_key = ref["cite_key"]

        # Download the PDF
        pdf_path = output_dir / f"{cite_key}.pdf"
        if pdf_path.exists():
            acquired[cite_key] = str(pdf_path)
            continue

        try:
            resp = s.get(pdf_url, timeout=60, stream=True, allow_redirects=True)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            # Accept if content-type says PDF, URL ends in .pdf, or URL has /pdf/
            is_pdf = (
                "pdf" in content_type.lower()
                or pdf_url.endswith(".pdf")
                or "/pdf/" in pdf_url
                or resp.url.endswith(".pdf")  # check after redirects
            )
            if not is_pdf:
                continue

            with open(pdf_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Verify we got a real PDF (check magic bytes)
            with open(pdf_path, "rb") as f:
                header = f.read(5)
            if header != b"%PDF-":
                pdf_path.unlink()
                continue

            acquired[cite_key] = str(pdf_path)

        except requests.RequestException:
            continue

    if verbose:
        print(f"\n  Checked: {checked}")
        print(f"  OA found: {found}")
        print(f"  Downloaded: {len(acquired)}")

    return acquired
