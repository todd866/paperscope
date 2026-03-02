"""Revision diff: semantic comparison between two versions of a paper."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ..text import clean_latex
from ..text.parsing import extract_paragraphs
from ..embed import embed_texts
from ..embed.similarity import cosine_sim
from ._common import load_reference_texts, prepare_reference_chunks


def _extract_sections_with_text(tex_text: str) -> List[Dict]:
    """Split into sections with title and cleaned body text."""
    body = re.split(
        r"\\bibliography\{|\\begin\{thebibliography\}", tex_text, maxsplit=1
    )[0]
    parts = re.split(r"\\(?:section|subsection)\*?\{([^}]+)\}", body)
    sections: List[Dict] = []
    for i in range(1, len(parts) - 1, 2):
        title = clean_latex(parts[i])
        text = clean_latex(parts[i + 1])
        if len(text.split()) >= 10:
            sections.append({"title": title, "text": text})
    return sections


def revision_diff(
    old_tex: str,
    new_tex: str,
    literature_dir: Optional[Path] = None,
    model=None,
) -> Dict:
    """Compute semantic differences between two revisions of a paper.

    Measures:
    - Per-section shift magnitude (how much each section moved in embedding space)
    - Overall revision magnitude
    - Direction of movement relative to literature (if provided)

    Args:
        old_tex: Raw LaTeX of the old version.
        new_tex: Raw LaTeX of the new version.
        literature_dir: Optional path to ``text/`` directory for reference comparison.
        model: Pre-loaded embedding model.

    Returns:
        Dict with per-section diffs and summary statistics.
    """
    old_sections = _extract_sections_with_text(old_tex)
    new_sections = _extract_sections_with_text(new_tex)

    if not old_sections or not new_sections:
        # Fall back to paragraph-level comparison
        old_paras = extract_paragraphs(old_tex)
        new_paras = extract_paragraphs(new_tex)
        return _paragraph_diff(old_paras, new_paras, model=model)

    # Match sections by title similarity
    old_titles = [s["title"] for s in old_sections]
    new_titles = [s["title"] for s in new_sections]
    all_titles = old_titles + new_titles
    title_emb, _ = embed_texts(all_titles, model=model, show_progress=False)
    old_title_emb = title_emb[: len(old_titles)]
    new_title_emb = title_emb[len(old_titles) :]
    title_sims = cosine_sim(old_title_emb, new_title_emb)

    # Embed section bodies
    all_texts = [s["text"][:2000] for s in old_sections] + [
        s["text"][:2000] for s in new_sections
    ]
    body_emb, backend = embed_texts(all_texts, model=model, show_progress=False)
    old_emb = body_emb[: len(old_sections)]
    new_emb = body_emb[len(old_sections) :]

    # Match old -> new by title similarity
    section_diffs: List[Dict] = []
    matched_new = set()
    for i, old_sec in enumerate(old_sections):
        best_j = int(np.argmax(title_sims[i]))
        if title_sims[i, best_j] > 0.5:
            matched_new.add(best_j)
            # Cosine distance between old and new version of this section
            old_norm = old_emb[i] / (np.linalg.norm(old_emb[i]) + 1e-12)
            new_norm = new_emb[best_j] / (np.linalg.norm(new_emb[best_j]) + 1e-12)
            shift = float(1 - np.dot(old_norm, new_norm))

            old_words = len(old_sec["text"].split())
            new_words = len(new_sections[best_j]["text"].split())

            section_diffs.append({
                "old_title": old_sec["title"],
                "new_title": new_sections[best_j]["title"],
                "semantic_shift": shift,
                "word_count_change": new_words - old_words,
                "old_words": old_words,
                "new_words": new_words,
            })
        else:
            section_diffs.append({
                "old_title": old_sec["title"],
                "new_title": None,
                "semantic_shift": 1.0,  # removed section
                "word_count_change": -len(old_sec["text"].split()),
                "old_words": len(old_sec["text"].split()),
                "new_words": 0,
            })

    # Sections only in new version
    added: List[Dict] = []
    for j, new_sec in enumerate(new_sections):
        if j not in matched_new:
            added.append({
                "title": new_sec["title"],
                "word_count": len(new_sec["text"].split()),
            })

    section_diffs.sort(key=lambda x: x["semantic_shift"], reverse=True)

    # Literature direction check
    lit_direction = None
    if literature_dir:
        ref_texts = load_reference_texts(literature_dir)
        if ref_texts:
            ref_chunk_texts, _ = prepare_reference_chunks(ref_texts)
            if ref_chunk_texts:
                ref_emb, _ = embed_texts(
                    ref_chunk_texts[:500], model=model, show_progress=False
                )
                # Overall paper embeddings
                old_centroid = np.mean(old_emb, axis=0, keepdims=True)
                new_centroid = np.mean(new_emb, axis=0, keepdims=True)
                ref_centroid = np.mean(ref_emb, axis=0, keepdims=True)

                old_to_lit = float(cosine_sim(old_centroid, ref_centroid)[0, 0])
                new_to_lit = float(cosine_sim(new_centroid, ref_centroid)[0, 0])
                lit_direction = {
                    "old_to_literature": old_to_lit,
                    "new_to_literature": new_to_lit,
                    "moved_toward_literature": new_to_lit > old_to_lit,
                    "delta": new_to_lit - old_to_lit,
                }

    shifts = [d["semantic_shift"] for d in section_diffs]
    return {
        "section_diffs": section_diffs,
        "added_sections": added,
        "summary": {
            "n_sections_compared": len(section_diffs),
            "n_sections_added": len(added),
            "mean_shift": float(np.mean(shifts)) if shifts else 0.0,
            "max_shift": float(np.max(shifts)) if shifts else 0.0,
            "most_changed": section_diffs[0]["old_title"] if section_diffs else None,
        },
        "literature_direction": lit_direction,
        "backend": backend,
    }


def _paragraph_diff(
    old_paras: List[Dict],
    new_paras: List[Dict],
    model=None,
) -> Dict:
    """Fallback: compare two versions at paragraph level."""
    old_texts = [p["text"][:500] for p in old_paras]
    new_texts = [p["text"][:500] for p in new_paras]
    all_texts = old_texts + new_texts
    if not all_texts:
        return {"error": "No paragraphs found in either version"}

    emb, backend = embed_texts(all_texts, model=model, show_progress=False)
    old_emb = emb[: len(old_texts)]
    new_emb = emb[len(old_texts) :]

    sims = cosine_sim(old_emb, new_emb)
    # For each old paragraph, find best match in new
    best_match_sims = np.max(sims, axis=1)
    removed = [
        {"line": old_paras[i]["line"], "text": old_paras[i]["text"][:100]}
        for i in range(len(old_paras))
        if best_match_sims[i] < 0.5
    ]
    # For each new paragraph, find best match in old
    best_reverse = np.max(sims, axis=0)
    added = [
        {"line": new_paras[j]["line"], "text": new_paras[j]["text"][:100]}
        for j in range(len(new_paras))
        if best_reverse[j] < 0.5
    ]

    return {
        "mode": "paragraph_level",
        "old_paragraphs": len(old_paras),
        "new_paragraphs": len(new_paras),
        "likely_removed": removed[:20],
        "likely_added": added[:20],
        "backend": backend,
    }
