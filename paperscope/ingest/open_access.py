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

# Browser-like default User-Agent. Publishers (BMJ, SciELO, Wiley) commonly
# 403 the polite-pool UA on direct PDF downloads even when Unpaywall has
# correctly flagged the paper as OA. Mimicking a real browser gets us past
# most of those filters.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)


def _get_oa_pdf_urls(
    doi: str, session: Optional[requests.Session] = None
) -> List[str]:
    """Return every candidate PDF URL Unpaywall knows for a DOI.

    Ordered by download-likelihood: direct `.pdf` URLs first, then `/pdf/` or
    `format=pdf` paths, then everything else. `best_oa_location` is tried
    before alternate `oa_locations`. Deduplicated.
    """
    s = session or requests.Session()
    try:
        resp = s.get(
            f"{UNPAYWALL_API}/{doi}",
            params={"email": MAILTO},
            timeout=15,
        )
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError):
        return []

    urls: List[str] = []
    seen: set = set()

    best = data.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        urls.append(best["url_for_pdf"])
        seen.add(best["url_for_pdf"])

    for loc in data.get("oa_locations", []) or []:
        url = loc.get("url_for_pdf")
        if url and url not in seen:
            urls.append(url)
            seen.add(url)

    def _priority(u: str) -> int:
        if u.endswith(".pdf"):
            return 0
        if "/pdf/" in u or "format=pdf" in u:
            return 1
        return 2

    urls.sort(key=_priority)
    return urls


def check_unpaywall(
    doi: str, session: Optional[requests.Session] = None
) -> Optional[str]:
    """Single best OA PDF URL for a DOI, or None.

    Kept for backward compatibility — new code should call `_get_oa_pdf_urls`
    directly so it can try every candidate when the publisher bot-blocks the
    first one.
    """
    urls = _get_oa_pdf_urls(doi, session)
    return urls[0] if urls else None


def acquire_oa_pdfs(
    refs: List[Dict],
    output_dir: Path,
    session: Optional[requests.Session] = None,
    limit: int = 0,
    verbose: bool = True,
) -> Dict[str, str]:
    """Acquire open access PDFs for references with DOIs.

    For each DOI, asks Unpaywall for every candidate OA URL and tries them in
    order until one yields a valid PDF. Uses a browser-like User-Agent and a
    `https://doi.org/{doi}` Referer to defeat publisher bot blocks on
    paper-fetcher UAs. Falls through silently when no URL works — the paper
    just stays in the EZProxy queue for institutional-auth retrieval.

    Args:
        refs: list of reference dicts with `doi` and `cite_key` fields
        output_dir: directory to save PDFs (as `<cite_key>.pdf`)
        session: optional `requests.Session`
        limit: max refs to process (0 = all)
        verbose: print progress

    Returns:
        Dict mapping cite_key -> local PDF path (only successfully downloaded).
    """
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", _BROWSER_UA)
    s.headers.setdefault(
        "Accept", "application/pdf,application/octet-stream,*/*;q=0.8"
    )
    s.headers.setdefault("Accept-Language", "en-US,en;q=0.5")

    output_dir.mkdir(parents=True, exist_ok=True)

    with_doi = [r for r in refs if r.get("doi")]
    if limit > 0:
        with_doi = with_doi[:limit]

    if verbose:
        print(f"Checking Unpaywall for {len(with_doi)} references...")

    acquired: Dict[str, str] = {}
    checked = 0
    found_oa = 0

    for ref in with_doi:
        checked += 1
        if verbose and checked % 25 == 0:
            print(f"  [{checked}/{len(with_doi)}] found: {found_oa}  downloaded: {len(acquired)}")

        time.sleep(RATE_LIMIT_DELAY)

        candidate_urls = _get_oa_pdf_urls(ref["doi"], session=s)
        if not candidate_urls:
            continue

        found_oa += 1
        cite_key = ref["cite_key"]
        pdf_path = output_dir / f"{cite_key}.pdf"
        if pdf_path.exists():
            acquired[cite_key] = str(pdf_path)
            continue

        # Try each candidate URL in priority order until one yields a PDF.
        for pdf_url in candidate_urls:
            try:
                referer = f"https://doi.org/{ref['doi']}"
                resp = s.get(
                    pdf_url,
                    timeout=60,
                    stream=True,
                    allow_redirects=True,
                    headers={"Referer": referer},
                )
                if resp.status_code != 200:
                    continue

                content_type = resp.headers.get("content-type", "").lower()
                # Treat as a PDF candidate if content-type, URL, or final URL
                # smells like one. We still magic-byte check below.
                is_pdf_like = (
                    "pdf" in content_type
                    or pdf_url.endswith(".pdf")
                    or "/pdf/" in pdf_url
                    or "format=pdf" in pdf_url
                    or resp.url.endswith(".pdf")
                )
                if not is_pdf_like:
                    continue

                with open(pdf_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Magic-byte verify — content-type lies sometimes.
                with open(pdf_path, "rb") as f:
                    header = f.read(5)
                if header != b"%PDF-":
                    pdf_path.unlink(missing_ok=True)
                    continue

                acquired[cite_key] = str(pdf_path)
                break  # got one; move to next ref

            except requests.RequestException:
                continue

    if verbose:
        print(f"\n  Checked: {checked}")
        print(f"  OA found: {found_oa}")
        print(f"  Downloaded: {len(acquired)}")

    return acquired
