"""Acquisition orchestrator: included.jsonl → PDFs + text + EZProxy queue.

Workflow:
  1. Load the review's included.jsonl (or records.jsonl if explicitly chosen).
  2. Partition by DOI presence (no-DOI records can't be fetched automatically).
  3. Call Unpaywall via `ingest.acquire_oa_pdfs` for the DOI-bearing set.
  4. Write an EZProxy queue for the paywalled tail.
  5. Run text extraction on every PDF we now have.
  6. Optionally upload PDFs to B2 (paperscope's existing cloud_store).
  7. Report coverage.

The Chrome-driven paywalled fetch is a separate step (`acquire.browser`) — it
walks the EZProxy queue and downloads via USyd's institutional access. Kept
separate so the auto-pull stage stays fast and idempotent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

from paperscope.systematic_review.records import load_jsonl


@dataclass
class AcquireResult:
    """Coverage report from one acquire run."""

    review_name: str
    corpus_dir: str
    total_records: int = 0
    with_doi: int = 0
    no_doi: int = 0
    oa_found: int = 0
    oa_downloaded: int = 0
    already_cached: int = 0
    queued_for_ezproxy: int = 0
    text_extracted: int = 0
    text_already_present: int = 0
    failed: list[str] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        if not self.with_doi:
            return 0.0
        have = self.oa_downloaded + self.already_cached
        return 100.0 * have / self.with_doi

    def to_dict(self) -> dict:
        d = asdict(self)
        d["coverage_pct"] = round(self.coverage_pct, 1)
        return d

    def pretty(self) -> str:
        return (
            f"Acquire report — {self.review_name}\n"
            f"  Corpus dir:           {self.corpus_dir}\n"
            f"  Total records:        {self.total_records:,}\n"
            f"  With DOI:             {self.with_doi:,}\n"
            f"  No DOI (manual only): {self.no_doi:,}\n"
            f"  OA found (Unpaywall): {self.oa_found:,}\n"
            f"  OA downloaded:        {self.oa_downloaded:,}\n"
            f"  Already cached:       {self.already_cached:,}\n"
            f"  Queued for EZProxy:   {self.queued_for_ezproxy:,}\n"
            f"  Text extracted:       {self.text_extracted:,}\n"
            f"  Text already present: {self.text_already_present:,}\n"
            f"  Coverage (DOI set):   {self.coverage_pct:.1f}%"
        )


def record_to_ref(record: dict) -> dict:
    """Adapt an SR record into the shape paperscope.ingest expects.

    SR records key by `pmid`; paperscope's ingest keys by `cite_key`. We use
    PMID as the cite_key — it's the natural unique identifier for MEDLINE
    records, and PubMed accession numbers (when present) work the same way.
    """
    return {
        "cite_key": str(record.get("pmid") or record.get("cite_key") or "").strip(),
        "doi": (record.get("doi") or "").strip(),
        "title": record.get("title", ""),
    }


def acquire(
    *,
    review_name: str,
    corpus_dir: str | Path,
    records: list[dict] | None = None,
    records_path: str | Path | None = None,
    ezproxy_host: str = "ezproxy.library.usyd.edu.au",
    fetch_oa: bool = True,
    extract_text_pdfs: bool = True,
    upload_b2: bool = False,
    oa_limit: int = 0,
    verbose: bool = True,
) -> AcquireResult:
    """Run the acquisition pipeline against a set of SR records.

    Either pass `records` directly or `records_path` (default: corpus_dir /
    included.jsonl, falling back to corpus_dir / records.jsonl).
    """
    corpus_dir = Path(corpus_dir)
    pdf_dir = corpus_dir / "papers"
    text_dir = corpus_dir / "text"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    # Resolve records source
    if records is None:
        candidates = [
            Path(records_path) if records_path else None,
            corpus_dir / "included.jsonl",
            corpus_dir / "records.jsonl",
        ]
        for cand in candidates:
            if cand and cand.exists():
                records = load_jsonl(cand)
                if verbose:
                    print(f"Loaded {len(records)} records from {cand}")
                break
        if records is None:
            raise FileNotFoundError(
                f"No records source found. Pass records=, records_path=, or place "
                f"included.jsonl / records.jsonl under {corpus_dir}"
            )

    report = AcquireResult(review_name=review_name, corpus_dir=str(corpus_dir))
    report.total_records = len(records)

    with_doi = [r for r in records if (r.get("doi") or "").strip()]
    no_doi = [r for r in records if not (r.get("doi") or "").strip()]
    report.with_doi = len(with_doi)
    report.no_doi = len(no_doi)

    # Count what's already cached before doing anything.
    cached_keys = {p.stem for p in pdf_dir.glob("*.pdf")}
    report.already_cached = sum(1 for r in with_doi if str(r["pmid"]) in cached_keys)

    # --- Phase 1: Open-access acquisition via Unpaywall -----------------
    acquired_paths: dict[str, str] = {}
    if fetch_oa and with_doi:
        # Unpaywall requires a real email for its polite pool. Paperscope's
        # default fallback ("paperscope@example.com") is rejected upstream
        # and silently returns 0 OA hits — warn loudly so this doesn't look
        # like "this corpus has no OA papers" when it's actually a config bug.
        import os as _os

        mailto = _os.environ.get("PAPERSCOPE_EMAIL", "").strip()
        if not mailto or mailto.endswith("example.com"):
            print(
                "\n⚠️  PAPERSCOPE_EMAIL is not set (or is the fake default).\n"
                "    Unpaywall rejects requests without a real email; the OA stage\n"
                "    will return 0 hits. Set it before re-running:\n"
                "        export PAPERSCOPE_EMAIL=your@email.tld\n"
                "    The EZProxy queue will still be generated correctly.\n"
            )

        # Lazy import — only require `requests` if we're actually fetching.
        from paperscope.ingest.open_access import acquire_oa_pdfs

        refs_for_ingest = [record_to_ref(r) for r in with_doi]
        refs_for_ingest = [r for r in refs_for_ingest if r["cite_key"] and r["doi"]]
        if verbose:
            print(f"=== Unpaywall OA acquisition ({len(refs_for_ingest)} candidates) ===")
        oa_stats: dict[str, int] = {}
        acquired_paths = acquire_oa_pdfs(
            refs_for_ingest,
            pdf_dir,
            limit=oa_limit,
            verbose=verbose,
            stats=oa_stats,
        )
        # oa_found = DOIs Unpaywall gave us a URL for (may exceed downloads
        # when publishers bot-block the actual PDF — important distinction
        # for coverage reporting).
        report.oa_found = oa_stats.get("oa_found", 0)
        report.oa_downloaded = sum(
            1
            for k in acquired_paths
            if k not in cached_keys
        )

    # --- Phase 2: EZProxy queue for the paywalled tail ------------------
    have_pdf_keys = {p.stem for p in pdf_dir.glob("*.pdf")}
    paywalled = [
        r
        for r in with_doi
        if str(r["pmid"]) not in have_pdf_keys
    ]
    if paywalled:
        from paperscope.systematic_review.acquire.ezproxy import write_ezproxy_queue

        queue_path = corpus_dir / "ezproxy-queue.json"
        report.queued_for_ezproxy = write_ezproxy_queue(
            paywalled,
            queue_path,
            ezproxy_host=ezproxy_host,
        )
        if verbose:
            print(f"\nWrote {report.queued_for_ezproxy} paywalled items → {queue_path}")
            print("Run `python -m paperscope.systematic_review acquire <config> "
                  "--fetch-paywalled` to drive Chrome through it.")

    # --- Phase 3: Text extraction (every PDF we have) -------------------
    if extract_text_pdfs:
        # Lazy import — only require PyMuPDF if extracting.
        from paperscope.ingest.extract_text import extract_text

        if verbose:
            print(f"\n=== Text extraction ===")
        for pdf_path in sorted(pdf_dir.glob("*.pdf")):
            text_path = text_dir / f"{pdf_path.stem}.txt"
            if text_path.exists():
                report.text_already_present += 1
                continue
            try:
                extract_text(pdf_path, text_path)
                report.text_extracted += 1
            except Exception as e:
                report.failed.append(f"{pdf_path.name}: {type(e).__name__}: {e}")
        if verbose:
            print(f"  newly extracted: {report.text_extracted}")
            print(f"  already had text: {report.text_already_present}")
            if report.failed:
                print(f"  failed: {len(report.failed)}")

    # --- Phase 4: Optional B2 upload ------------------------------------
    if upload_b2 and acquired_paths:
        try:
            from paperscope.ingest.cloud_store import (
                get_b2_bucket,
                upload_pdf,
                update_manifest,
            )
            bucket = get_b2_bucket()
            manifest_path = corpus_dir / "pdf_manifest.json"
            uploaded = 0
            for cite_key, path in acquired_paths.items():
                try:
                    file_id = upload_pdf(Path(path), cite_key, bucket=bucket)
                    matching = next(
                        (r for r in with_doi if str(r["pmid"]) == cite_key), {}
                    )
                    update_manifest(
                        manifest_path,
                        cite_key,
                        file_id,
                        doi=matching.get("doi", ""),
                    )
                    uploaded += 1
                except Exception as e:
                    report.failed.append(f"B2 {cite_key}: {type(e).__name__}: {e}")
            if verbose:
                print(f"\n=== B2 upload === uploaded: {uploaded}")
        except Exception as e:
            if verbose:
                print(f"\n  B2 setup failed: {e}")
                print("  Set B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY env vars.")

    # --- Final report ---------------------------------------------------
    # Persist machine-readable report alongside the PDFs.
    report_path = corpus_dir / "acquire-report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if verbose:
        print(f"\n{report.pretty()}")
        print(f"\nMachine-readable report: {report_path}")
    return report


def load_ezproxy_queue(corpus_dir: str | Path) -> list[dict]:
    """Load the EZProxy queue (for the browser driver)."""
    path = Path(corpus_dir) / "ezproxy-queue.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def filter_queue_for_missing(queue: list[dict], corpus_dir: str | Path) -> list[dict]:
    """Drop queue entries whose PDF is now present (idempotent re-runs)."""
    pdf_dir = Path(corpus_dir) / "papers"
    have = {p.stem for p in pdf_dir.glob("*.pdf")}
    return [q for q in queue if q.get("cite_key") not in have]
