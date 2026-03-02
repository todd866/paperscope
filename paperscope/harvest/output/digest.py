"""Generate markdown digest of discovered papers."""

import json
from datetime import datetime
from pathlib import Path
from typing import List

from ..sources.base import Paper


def generate_digest(papers: List[Paper], output_dir: Path) -> Path:
    """Generate a markdown digest of papers."""
    today = datetime.now().strftime("%Y-%m-%d")
    day_dir = output_dir / "inbox" / today
    day_dir.mkdir(parents=True, exist_ok=True)

    digest_path = day_dir / "digest.md"

    lines = [
        f"# Paper Digest: {today}",
        "",
        f"Found **{len(papers)} papers** matching your research profile.",
        "",
        "---",
        "",
    ]

    for i, paper in enumerate(papers, 1):
        lines.extend([
            f"## {i}. {paper.title}",
            f"**Authors:** {paper.first_author}",
            f"**Source:** {paper.display_id}",
        ])

        if paper.published_date:
            lines.append(f"**Published:** {paper.published_date.strftime('%Y-%m-%d')}")

        if paper.pdf_url:
            lines.append(f"**PDF:** [Link]({paper.pdf_url})")

        lines.append("")

        if paper.abstract:
            lines.append("**Abstract:**")
            lines.append(paper.abstract[:1000] + ("..." if len(paper.abstract) > 1000 else ""))
            lines.append("")

        if paper.matched_keywords:
            lines.append(f"**Matched keywords:** {', '.join(paper.matched_keywords)}")

        if paper.matched_authors:
            lines.append(f"**Matched authors:** {', '.join(paper.matched_authors)}")

        lines.extend(["", "---", ""])

    with open(digest_path, "w") as f:
        f.write("\n".join(lines))

    return digest_path


def update_seen_papers(papers: List[Paper], output_dir: Path) -> None:
    """Update seen.json with newly discovered papers."""
    seen_path = output_dir / "seen.json"

    if seen_path.exists():
        with open(seen_path) as f:
            data = json.load(f)
    else:
        data = {"papers": {}}

    today = datetime.now().strftime("%Y-%m-%d")

    for paper in papers:
        if paper.id not in data["papers"]:
            data["papers"][paper.id] = {
                "first_seen": today,
                "title": paper.title,
                "status": "inbox",
            }

    with open(seen_path, "w") as f:
        json.dump(data, f, indent=2)


def get_unseen_papers(papers: List[Paper], output_dir: Path) -> List[Paper]:
    """Filter papers to only those we haven't seen before."""
    seen_path = output_dir / "seen.json"

    if not seen_path.exists():
        return papers

    with open(seen_path) as f:
        data = json.load(f)

    seen_ids = set(data.get("papers", {}).keys())
    return [p for p in papers if p.id not in seen_ids]
