"""Generate structured summaries of papers.

This module is designed to be used with an LLM to generate structured
readings of papers from extracted text. The output format captures:
- Key claims and findings
- Methods used
- Main results
- Limitations stated by authors
- Relevance to the research program
"""

import json
from pathlib import Path
from typing import Dict, List, Optional


def create_reading_prompt(text: str, context: str = "") -> str:
    """Create a prompt for structured reading of a paper.

    Args:
        text: Extracted text from the paper
        context: Optional context about why we're reading this paper

    Returns:
        Prompt string for LLM processing
    """
    prompt = f"""Read the following paper and extract a structured summary.

{f"Context: {context}" if context else ""}

Output JSON with the following fields:
- title: Paper title
- key_claims: List of main claims (each as a short sentence)
- methods: List of methods/techniques used
- results: List of main results/findings
- limitations: Limitations stated by the authors
- relevance: How this relates to high-dimensional dynamics / information geometry / coherence
- citation_notes: Specific claims that could be cited, with page/section references

Paper text:
{text[:50000]}"""

    return prompt


def save_reading(reading: Dict, output_path: Path) -> None:
    """Save a structured reading to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(reading, f, indent=2, ensure_ascii=False)


def load_reading(reading_path: Path) -> Optional[Dict]:
    """Load a structured reading from JSON."""
    if not reading_path.exists():
        return None
    with open(reading_path) as f:
        return json.load(f)
