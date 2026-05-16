"""Shadow-library PDF acquisition via Anna's Archive (Stage 3 / opt-in).

The legitimate acquisition path (Stage 1 = Unpaywall in `open_access.py`,
Stage 2 = institutional EZProxy in `systematic_review/acquire/browser_driver`)
covers somewhere between 30% and 70% of any real systematic review's included
set. The long tail is paywalled-with-no-institutional-access, or technically
OA but blocked by publisher bot-detection (Wiley, BMJ, Oxford, MDPI, etc.
routinely 403 even Mozilla user agents on direct PDF requests).

For research purposes — when an author of an unwritten systematic review
needs to actually read the literature she is reviewing — Anna's Archive is
the de facto sustainable solution. This module is the boundary-crossing
layer paperscope users explicitly opt into.

DESIGN PRINCIPLE: explicit, opt-in, isolated. The module is not imported
by any other paperscope code by default. Users must:

    from paperscope.ingest.shadow_library import acquire_shadow_pdfs

…to use it. The systematic-review pipeline accepts an
`enable_shadow_library=True` flag (default False) that wires it in as
the post-OA, post-EZProxy stage.

LEGAL POSTURE: Anna's Archive aggregates documents the publishing
industry restricts access to. Whether using it is "legal" depends on
jurisdiction and use-case; for an individual researcher reading the
literature she is reviewing, the answer in most jurisdictions is "yes,
for personal scholarly use" — but this isn't legal advice. Operators
of paperscope deployments that host PDFs for others should be more
cautious; that's why this is opt-in and intentionally kept off the
default pipeline path.

ARCHITECTURE: two free functions plus an orchestrator analogous to
`open_access.acquire_oa_pdfs`. Anna's Archive offers two endpoints we
use:

  1. `https://annas-archive.org/scidb/<DOI>` — resolves a DOI to an
     MD5 hash. The HTML response contains `/md5/<32-hex>` somewhere;
     we scrape it out.
  2. `https://annas-archive.gl/md5/<MD5>/get` — direct PDF download.

Mirror domains (.gl, .org, .se, .li) rotate availability and rate
limits; we try them in order on failure.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    raise ImportError(
        "'requests' package required. Install with: pip install requests"
    )

# Mirror rotation — Anna's Archive uses several domains; if the primary
# is rate-limited or temporarily down, fall through to the others.
SCIDB_BASES = [
    "https://annas-archive.gl/scidb",
    "https://annas-archive.org/scidb",
    "https://annas-archive.se/scidb",
    "https://annas-archive.li/scidb",
]
MD5_BASES = [
    "https://annas-archive.gl/md5",
    "https://annas-archive.org/md5",
    "https://annas-archive.se/md5",
]

# Browser-like UA. Anna's Archive doesn't bot-detect aggressively, but
# matches the rest of paperscope's fetchers.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en-US;q=0.9,en;q=0.8",
}

# Per-request pacing. Anna's Archive is generous but not infinitely so.
RATE_LIMIT_DELAY = float(os.environ.get("PAPERSCOPE_SHADOW_PACE_S", "2.0"))


@dataclass
class ShadowAttempt:
    """Single-record outcome for the audit log."""

    record_id: str               # caller-defined: pmid, cite_key, ebsco_an
    doi: str
    md5: str = ""                # resolved or empty
    outcome: str = "unknown"     # "fetched" / "no_md5" / "no_pdf" / "error"
    note: str = ""
    pdf_path: str = ""           # path written, if any
    pdf_bytes: int = 0           # size of the PDF, if fetched


@dataclass
class ShadowReport:
    """Aggregate results across a batch."""

    attempts: list[ShadowAttempt] = field(default_factory=list)
    fetched: int = 0
    no_md5: int = 0
    no_pdf: int = 0
    error: int = 0
    already_have: int = 0


def resolve_doi_to_md5(
    doi: str,
    session: Optional[requests.Session] = None,
    timeout: float = 15.0,
) -> Optional[str]:
    """Resolve a DOI to an Anna's Archive MD5 hash via SciDB.

    Walks the mirror domains in `SCIDB_BASES`; returns the first MD5
    found, or None if the DOI isn't in the archive (or all mirrors
    fail).

    The SciDB landing page embeds zero or more `/md5/<32-hex>` links;
    we grab the first one. (In practice each DOI maps to exactly one
    MD5; multiples would appear only for re-uploads or edition variants
    and the first is almost always the right one.)
    """
    if not doi:
        return None
    s = session or requests.Session()
    if "User-Agent" not in s.headers:
        s.headers.update(_HEADERS)
    for base in SCIDB_BASES:
        try:
            r = s.get(f"{base}/{doi}", timeout=timeout)
            if r.status_code != 200:
                continue
            m = re.search(r"/md5/([a-f0-9]{32})", r.text)
            if m:
                return m.group(1)
        except requests.RequestException:
            continue
    return None


def _extract_libgen_id(html: str) -> Optional[str]:
    """Find a libgen.li file ID on an Anna's Archive MD5 landing page."""
    m = re.search(r"libgen\.li/file\.php\?id=(\d+)", html)
    return m.group(1) if m else None


def _follow_libgen_chain(s: "requests.Session", libgen_id: str,
                         timeout: float = 60.0) -> Optional[bytes]:
    """libgen.li file.php → ads.php → get.php → PDF bytes.

    Anna's Archive's `/fast_download/` requires membership for anonymous
    clients (redirects to `/fast_download_not_member`). The libgen.li chain
    is the public no-account path: each step embeds the URL to the next as
    an href, and the final get.php returns application/octet-stream PDF.

    Single-IP concurrency: libgen.li throttles aggressively; keep
    fetchers at 1-2 concurrent workers and 2-3s pacing for stable hits.
    """
    try:
        url1 = f"https://libgen.li/file.php?id={libgen_id}"
        r1 = s.get(url1, timeout=30)
        if r1.status_code != 200:
            return None
        m = re.search(r'href="(/ads\.php\?[^"]+)"', r1.text)
        if not m:
            return None
        url2 = "https://libgen.li" + m.group(1).replace("&amp;", "&")
        r2 = s.get(url2, timeout=30, headers={"Referer": url1})
        if r2.status_code != 200:
            return None
        m2 = re.search(r'href="(get\.php\?[^"]+|/get\.php\?[^"]+)"', r2.text)
        if not m2:
            return None
        get_path = m2.group(1).replace("&amp;", "&")
        if not get_path.startswith("/"):
            get_path = "/" + get_path
        url3 = "https://libgen.li" + get_path
        r3 = s.get(url3, timeout=timeout, headers={"Referer": url2})
        if r3.status_code == 200 and r3.content[:5] == b"%PDF-":
            return r3.content
    except requests.RequestException:
        pass
    return None


def fetch_pdf_by_md5(
    md5: str,
    dest: Path,
    session: Optional[requests.Session] = None,
    timeout: float = 60.0,
) -> tuple[bool, str]:
    """Download the PDF for the given MD5 to `dest`. Returns (ok, note).

    Walks `MD5_BASES`. Per mirror:
      1. Get the Anna's Archive `/md5/<hash>` landing page.
      2. Extract a libgen.li file ID, then walk the libgen chain
         (file.php → ads.php → get.php → PDF).
      3. Fall back to scraping the landing page for any direct `.pdf` href.

    Anna's `/md5/<hash>/get` returns 404 on .gl as of 2026-05; the libgen
    chain is the working public path. `/fast_download/` requires
    membership; covered as an explicit alternative if you have credentials.
    """
    if not md5:
        return False, "no md5"
    s = session or requests.Session()
    if "User-Agent" not in s.headers:
        s.headers.update(_HEADERS)
    for base in MD5_BASES:
        try:
            page = s.get(f"{base}/{md5}", timeout=timeout)
            if page.status_code != 200:
                continue
            libgen_id = _extract_libgen_id(page.text)
            if libgen_id:
                pdf_bytes = _follow_libgen_chain(s, libgen_id, timeout=timeout)
                if pdf_bytes:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(pdf_bytes)
                    return True, f"{len(pdf_bytes):,}B via libgen.li/{libgen_id}"
            # Fallback to a direct .pdf href on the MD5 page (rare path)
            m = re.search(r'href="(/[^"]+\.pdf[^"]*)"', page.text)
            if not m:
                continue
            dl_url = base.rsplit("/md5", 1)[0] + m.group(1)
            r2 = s.get(dl_url, timeout=timeout)
            if r2.status_code == 200 and r2.content[:5] == b"%PDF-":
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r2.content)
                return True, f"{len(r2.content):,}B via scraped"
        except requests.RequestException:
            continue
    return False, "all mirrors failed or no PDF returned"


def acquire_shadow_pdfs(
    records: list[dict],
    output_dir: str | Path,
    *,
    id_key: str = "pmid",
    pace_s: float = RATE_LIMIT_DELAY,
    log_path: Optional[str | Path] = None,
    skip_existing: bool = True,
) -> ShadowReport:
    """Walk a record list, resolve DOI → MD5 → PDF, write to disk.

    Mirror of `open_access.acquire_oa_pdfs`'s shape so callers can swap
    it in as a Stage 3 after Unpaywall (Stage 1) and EZProxy (Stage 2).

    Args:
        records: iterable of dicts. Each needs `doi` and `id_key`
            (default `pmid`). Records without DOI are skipped (logged
            as `no_doi`).
        output_dir: where PDFs go. Files written as
            `<output_dir>/<record[id_key]>.pdf`.
        id_key: which field of the record is the stable identifier
            (matches paperscope SR's `pmid`-keyed convention).
        pace_s: seconds between requests (per process). Anna's Archive
            doesn't throttle aggressively but be polite.
        log_path: append every attempt as JSONL here. None → no log.
        skip_existing: if the target PDF already exists, skip.

    Returns:
        ShadowReport with per-record attempts and aggregate counters.
    """
    output_dir = Path(output_dir)
    report = ShadowReport()
    sess = requests.Session()
    sess.headers.update(_HEADERS)
    log_fh = open(log_path, "a") if log_path else None
    try:
        for rec in records:
            rid = str(rec.get(id_key, ""))
            doi = (rec.get("doi") or "").strip()
            dest = output_dir / f"{rid}.pdf"

            if skip_existing and dest.exists():
                report.already_have += 1
                continue
            if not doi:
                report.error += 1
                _log(log_fh, rid, doi, "", "no_doi", "")
                continue

            md5 = resolve_doi_to_md5(doi, session=sess)
            time.sleep(pace_s)
            if not md5:
                report.no_md5 += 1
                report.attempts.append(ShadowAttempt(
                    record_id=rid, doi=doi, outcome="no_md5",
                    note="DOI not in Anna's Archive SciDB",
                ))
                _log(log_fh, rid, doi, "", "no_md5", "")
                continue

            ok, note = fetch_pdf_by_md5(md5, dest, session=sess)
            time.sleep(pace_s)
            attempt = ShadowAttempt(
                record_id=rid, doi=doi, md5=md5,
                outcome="fetched" if ok else "no_pdf",
                note=note,
                pdf_path=str(dest) if ok else "",
                pdf_bytes=(dest.stat().st_size if ok and dest.exists() else 0),
            )
            report.attempts.append(attempt)
            if ok:
                report.fetched += 1
            else:
                report.no_pdf += 1
            _log(log_fh, rid, doi, md5, attempt.outcome, note)
    finally:
        if log_fh:
            log_fh.close()
    return report


def _log(fh, rid: str, doi: str, md5: str, outcome: str, note: str) -> None:
    if not fh:
        return
    entry = {
        "record_id": rid, "doi": doi, "md5": md5,
        "outcome": outcome, "note": note,
        "route": "annas_archive",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    fh.flush()
