"""Command-line interface for paper harvesting."""

import os
from pathlib import Path
from typing import List, Optional

from .config import Config
from .sources.base import Paper
from .sources.openalex import OpenAlexSource
from .sources.arxiv import ArxivSource
from .sources.biorxiv import BiorxivSource
from .output.digest import generate_digest, update_seen_papers, get_unseen_papers
from .download.open_access import download_papers


def discover(config_path: Optional[Path] = None) -> int:
    """Run paper discovery."""
    config = Config.load(config_path)
    config.ensure_directories()

    profile = config.research_profile
    output_dir = config.paths.output_path

    print("Paperscope - Paper Discovery")
    print("=" * 40)
    print(f"Keywords: {len(profile.keywords)}")
    print(f"Authors: {len(profile.authors)}")
    print(f"Output: {output_dir}")
    print()

    all_papers: List[Paper] = []

    # OpenAlex (primary)
    print("Searching OpenAlex...")
    openalex = OpenAlexSource(email=os.environ.get("PAPERSCOPE_EMAIL", "paperscope@example.com"))
    oa_papers = openalex.search(
        keywords=profile.keywords,
        authors=profile.authors,
        max_results=config.discovery.max_papers_per_run,
        lookback_days=config.discovery.lookback_days,
    )
    print(f"  Found {len(oa_papers)} papers")
    all_papers.extend(oa_papers)
    print()

    # arXiv
    print("Searching arXiv...")
    arxiv = ArxivSource()
    arxiv_papers = arxiv.search(
        keywords=profile.keywords[:5],
        authors=profile.authors,
        max_results=config.discovery.max_papers_per_run // 2,
        lookback_days=config.discovery.lookback_days,
        categories=profile.arxiv_categories,
    )
    print(f"  Found {len(arxiv_papers)} papers")
    all_papers.extend(arxiv_papers)
    print()

    # bioRxiv
    print("Searching bioRxiv...")
    biorxiv = BiorxivSource(server="biorxiv")
    biorxiv_papers = biorxiv.search(
        keywords=profile.keywords,
        authors=profile.authors,
        max_results=config.discovery.max_papers_per_run // 2,
        lookback_days=config.discovery.lookback_days,
    )
    print(f"  Found {len(biorxiv_papers)} papers")
    all_papers.extend(biorxiv_papers)
    print()

    # Deduplicate
    seen_ids = set()
    unique_papers = []
    for paper in all_papers:
        if paper.id not in seen_ids:
            seen_ids.add(paper.id)
            unique_papers.append(paper)

    print(f"Total unique papers: {len(unique_papers)}")

    # Filter unseen
    new_papers = get_unseen_papers(unique_papers, output_dir)
    print(f"New papers (not seen before): {len(new_papers)}")

    if not new_papers:
        print("\nNo new papers found.")
        return 0

    # Generate digest
    print("\nGenerating digest...")
    digest_path = generate_digest(new_papers, output_dir)
    print(f"  Wrote: {digest_path}")

    # Download OA PDFs
    oa_papers = [p for p in new_papers if p.pdf_url]
    if oa_papers:
        print(f"\nDownloading {len(oa_papers)} open access PDFs...")
        downloaded = download_papers(oa_papers, digest_path.parent)
        print(f"  Downloaded {len(downloaded)} PDFs")

    # Update seen
    update_seen_papers(new_papers, output_dir)

    print()
    print("=" * 40)
    print(f"Done! Review papers in:")
    print(f"  {digest_path}")

    return 0
