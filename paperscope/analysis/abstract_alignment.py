"""Abstract alignment: check whether the abstract covers all major sections."""

from __future__ import annotations

from typing import Dict

import numpy as np

from ..text.parsing import extract_abstract, extract_sections
from ..embed import embed_texts
from ..embed.similarity import cosine_sim


def abstract_alignment(
    tex_text: str,
    model=None,
) -> Dict:
    """Check how well the abstract covers each section of the paper.

    Returns a coverage matrix: for each section, its similarity to the
    abstract, plus an overall coverage score.

    Args:
        tex_text: Raw LaTeX source.
        model: Pre-loaded embedding model.

    Returns:
        Dict with ``abstract_text``, ``sections`` (with coverage scores),
        ``overall_coverage``, ``underrepresented`` (sections below threshold).
    """
    abstract = extract_abstract(tex_text, clean=True)
    if not abstract:
        return {"error": "No abstract found"}

    sections = extract_sections(tex_text, min_words=20)
    if not sections:
        return {"error": "No sections found"}

    # Embed abstract as one chunk, each section as one chunk
    texts = [abstract] + [s["text"][:2000] for s in sections]
    emb, backend = embed_texts(texts, model=model, show_progress=False)

    abstract_emb = emb[0:1]
    section_emb = emb[1:]

    sims = cosine_sim(abstract_emb, section_emb)[0]

    section_results: List[Dict] = []
    for i, sec in enumerate(sections):
        section_results.append({
            "title": sec["title"],
            "word_count": len(sec["text"].split()),
            "abstract_similarity": float(sims[i]),
        })

    # Sort by coverage (best represented first)
    section_results.sort(key=lambda x: x["abstract_similarity"], reverse=True)

    # Flag underrepresented sections (below median similarity)
    sim_values = [s["abstract_similarity"] for s in section_results]
    median_sim = float(np.median(sim_values)) if sim_values else 0.0
    underrepresented = [
        s for s in section_results
        if s["abstract_similarity"] < median_sim - 0.05
    ]

    return {
        "abstract_text": abstract[:500],
        "abstract_word_count": len(abstract.split()),
        "sections": section_results,
        "overall_coverage": float(np.mean(sim_values)) if sim_values else 0.0,
        "median_coverage": median_sim,
        "underrepresented": underrepresented,
        "backend": backend,
    }
