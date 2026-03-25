"""Ingest pipeline: OA acquisition + text extraction + optional B2 upload."""

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional


def _load_bibliography(data_dir: Path) -> list:
    """Load references from bibliography.json."""
    bib_path = data_dir / "bibliography.json"
    if not bib_path.exists():
        raise FileNotFoundError(f"No bibliography.json found at {bib_path}")
    with open(bib_path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("references", [])
    return data


def _filter_by_paper(refs: list, paper_filter: str) -> list:
    """Filter references to those from a specific paper folder."""
    filtered = []
    for r in refs:
        sources = r.get("source_files", [])
        if not sources:
            sf = r.get("source_file", "")
            if sf:
                sources = [sf]
        for sf in sources:
            if paper_filter in sf:
                filtered.append(r)
                break
    return filtered


def _paper_folder(ref: dict) -> str:
    """Extract paper folder from a reference's source file path."""
    sources = ref.get("source_files", [])
    if not sources:
        sf = ref.get("source_file", "")
        if sf:
            sources = [sf]
    for sf in sources:
        parts = sf.split("/")
        # Return the last two meaningful path components (domain/paper)
        if len(parts) >= 2:
            return parts[-2] + "/" + parts[-1]
        elif len(parts) == 1:
            return parts[0]
    return "unknown"


def ingest_main(
    data_dir: Path,
    limit: int = 0,
    paper_filter: Optional[str] = None,
    skip_download: bool = False,
    upload_b2: bool = False,
) -> int:
    """Run the ingest pipeline: acquire OA PDFs and extract text.

    Args:
        data_dir: Path to literature-data directory
        limit: Max references to process (0 = all)
        paper_filter: Only process refs from this paper folder
        skip_download: Skip OA download, only extract text from existing PDFs
        upload_b2: Upload acquired PDFs to B2 after download
    """
    refs = _load_bibliography(data_dir)
    total = len(refs)

    # Filter by paper if requested
    if paper_filter:
        refs = _filter_by_paper(refs, paper_filter)
        print(f"Filtered to {len(refs)} refs from '{paper_filter}' (of {total} total)")
    else:
        print(f"Processing all {total} references")

    # Filter to refs with DOIs
    with_doi = [r for r in refs if r.get("doi")]
    print(f"  With DOIs: {len(with_doi)}")

    if limit > 0:
        with_doi = with_doi[:limit]
        print(f"  Limited to: {limit}")

    pdf_dir = data_dir / "pdfs"
    text_dir = data_dir / "text"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: OA acquisition
    acquired = {}
    if not skip_download:
        from .open_access import acquire_oa_pdfs
        print(f"\n{'='*60}")
        print("Phase 1: Open Access PDF Acquisition")
        print(f"{'='*60}")
        acquired = acquire_oa_pdfs(with_doi, pdf_dir, limit=0, verbose=True)
    else:
        # Count existing PDFs
        for r in with_doi:
            pdf_path = pdf_dir / f"{r['cite_key']}.pdf"
            if pdf_path.exists():
                acquired[r["cite_key"]] = str(pdf_path)
        print(f"\nSkipping download. Found {len(acquired)} existing PDFs.")

    # Phase 2: Text extraction
    print(f"\n{'='*60}")
    print("Phase 2: Text Extraction")
    print(f"{'='*60}")

    extracted = 0
    skipped = 0
    failed = 0

    # Determine which PDFs to extract text from
    if paper_filter:
        # Only extract PDFs for refs matching the filter
        filtered_keys = {r["cite_key"] for r in with_doi}
        pdf_candidates = sorted(
            p for p in pdf_dir.glob("*.pdf") if p.stem in filtered_keys
        )
    else:
        pdf_candidates = sorted(pdf_dir.glob("*.pdf"))

    for pdf_path in pdf_candidates:
        text_path = text_dir / f"{pdf_path.stem}.txt"
        if text_path.exists():
            skipped += 1
            continue
        try:
            from .extract_text import extract_text
            extract_text(pdf_path, text_path)
            extracted += 1
            if extracted % 10 == 0:
                print(f"  Extracted: {extracted}")
        except Exception as e:
            failed += 1
            print(f"  Failed: {pdf_path.name}: {e}")

    print(f"\n  Newly extracted: {extracted}")
    print(f"  Already had text: {skipped}")
    if failed:
        print(f"  Failed: {failed}")

    # Phase 3: B2 upload (optional)
    if upload_b2 and acquired:
        print(f"\n{'='*60}")
        print("Phase 3: B2 Upload")
        print(f"{'='*60}")
        try:
            from .cloud_store import get_b2_bucket, upload_pdf, update_manifest
            bucket = get_b2_bucket()
            manifest_path = data_dir / "pdf_manifest.json"
            uploaded = 0
            for cite_key, pdf_path in acquired.items():
                try:
                    file_id = upload_pdf(Path(pdf_path), cite_key, bucket=bucket)
                    ref = next((r for r in refs if r["cite_key"] == cite_key), {})
                    update_manifest(manifest_path, cite_key, file_id, doi=ref.get("doi", ""))
                    uploaded += 1
                except Exception as e:
                    print(f"  B2 upload failed for {cite_key}: {e}")
            print(f"  Uploaded to B2: {uploaded}")
        except Exception as e:
            print(f"  B2 setup failed: {e}")
            print("  Set B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY env vars.")

    # Summary
    total_pdfs = len(list(pdf_dir.glob("*.pdf")))
    total_text = len(list(text_dir.glob("*.txt")))
    print(f"\n{'='*60}")
    print("Ingest Summary")
    print(f"{'='*60}")
    print(f"  Total references:     {total}")
    print(f"  With DOIs:            {len([r for r in _load_bibliography(data_dir) if r.get('doi')])}")
    print(f"  PDFs acquired:        {total_pdfs}")
    print(f"  Text files:           {total_text}")
    print(f"{'='*60}")

    return 0


def status_main(data_dir: Path, by_paper: bool = False) -> int:
    """Show pipeline status."""
    refs = _load_bibliography(data_dir)

    depth1 = [r for r in refs if r.get("depth", 1) == 1]
    depth2 = [r for r in refs if r.get("depth") == 2]

    with_doi = [r for r in refs if r.get("doi")]
    d1_doi = [r for r in depth1 if r.get("doi")]
    d2_doi = [r for r in depth2 if r.get("doi")]

    pdf_dir = data_dir / "pdfs"
    text_dir = data_dir / "text"
    readings_dir = data_dir / "readings"
    embed_dir = data_dir / "embeddings"

    total_pdfs = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0
    total_text = len(list(text_dir.glob("*.txt"))) if text_dir.exists() else 0
    total_readings = len(list(readings_dir.glob("*.json"))) if readings_dir.exists() else 0

    has_embeddings = (embed_dir / "claims.npy").exists() if embed_dir.exists() else False

    print(f"\n{'='*60}")
    print("Paperscope — Pipeline Status")
    print(f"{'='*60}")

    print(f"\n  Depth-1 references:   {len(depth1)}")
    print(f"    With DOIs:          {len(d1_doi)} ({100*len(d1_doi)//max(len(depth1),1)}%)")
    if depth2:
        print(f"  Depth-2 references:   {len(depth2)}")
        print(f"    With DOIs:          {len(d2_doi)} ({100*len(d2_doi)//max(len(depth2),1)}%)")
    print(f"  Total references:     {len(refs)}")
    print(f"  Total with DOIs:      {len(with_doi)}")
    print()
    print(f"  PDFs acquired:        {total_pdfs}")
    print(f"  Text extracted:       {total_text}")
    print(f"  Readings generated:   {total_readings}")
    print(f"  Embeddings:           {'yes' if has_embeddings else 'no'}")

    # Coverage percentages
    if len(with_doi) > 0:
        print(f"\n  PDF coverage:         {total_pdfs}/{len(with_doi)} DOI refs ({100*total_pdfs//len(with_doi)}%)")
    if total_pdfs > 0:
        print(f"  Text coverage:        {total_text}/{total_pdfs} PDFs ({100*total_text//max(total_pdfs,1)}%)")

    if by_paper:
        print(f"\n{'='*60}")
        print("Breakdown by Paper (depth-1 only)")
        print(f"{'='*60}")

        paper_stats = defaultdict(lambda: {"total": 0, "doi": 0, "pdf": 0, "text": 0})

        pdf_keys = set()
        if pdf_dir.exists():
            pdf_keys = {p.stem for p in pdf_dir.glob("*.pdf")}
        text_keys = set()
        if text_dir.exists():
            text_keys = {p.stem for p in text_dir.glob("*.txt")}

        for r in depth1:
            folder = _paper_folder(r)
            paper_stats[folder]["total"] += 1
            if r.get("doi"):
                paper_stats[folder]["doi"] += 1
            if r["cite_key"] in pdf_keys:
                paper_stats[folder]["pdf"] += 1
            if r["cite_key"] in text_keys:
                paper_stats[folder]["text"] += 1

        # Filter out _archive papers and sort by total refs descending
        active_papers = {k: v for k, v in paper_stats.items() if not k.startswith("_archive")}

        print(f"\n  {'Paper':<45} {'Refs':>5} {'DOI':>5} {'PDF':>5} {'Text':>5}")
        print(f"  {'-'*45} {'-'*5} {'-'*5} {'-'*5} {'-'*5}")
        for folder in sorted(active_papers, key=lambda k: active_papers[k]["total"], reverse=True):
            s = active_papers[folder]
            print(f"  {folder:<45} {s['total']:>5} {s['doi']:>5} {s['pdf']:>5} {s['text']:>5}")

        if paper_stats.keys() - active_papers.keys():
            archive_total = sum(v["total"] for k, v in paper_stats.items() if k.startswith("_archive"))
            print(f"\n  (+ {archive_total} refs from archived papers)")

    print()
    return 0
