"""Audit citation usage: compare what a paper is cited for vs what it actually says."""

import json
from pathlib import Path
from typing import Dict, List, Optional


def audit_citation(
    cite_key: str,
    claimed_use: str,
    paper_text: str,
) -> Dict:
    """Create an audit prompt for a single citation.

    Args:
        cite_key: The citation key
        claimed_use: How the paper is cited in the manuscript
        paper_text: Extracted text from the cited paper

    Returns:
        Audit result dict
    """
    prompt = f"""Citation audit for {cite_key}.

The manuscript cites this paper as follows:
"{claimed_use}"

Does the paper actually support this claim? Read the paper text below and assess:
1. Does the paper make this specific claim?
2. Is the citation accurate, misleading, or wrong?
3. What does the paper actually say about this topic?

Paper text:
{paper_text[:30000]}"""

    return {
        "cite_key": cite_key,
        "claimed_use": claimed_use,
        "audit_prompt": prompt,
        "status": "pending",
    }


def save_audit_report(audits: List[Dict], output_path: Path) -> None:
    """Save audit results."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(audits, f, indent=2, ensure_ascii=False)
