"""Reviewer probe analysis: anticipate objections and map to evidence."""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np

from ..embed import embed_texts
from ..embed.similarity import cosine_sim


def reviewer_probes(
    probes: Sequence[Tuple[str, str]],
    chunk_keys: List[str],
    chunk_emb: np.ndarray,
    model=None,
    k: int = 3,
) -> List[Dict]:
    """Embed reviewer-perspective queries and find nearest literature.

    Args:
        probes: ``[(label, query_text), ...]`` pairs.
        chunk_keys: Cite key for each literature chunk.
        chunk_emb: Embeddings for literature chunks.
        model: Pre-loaded embedding model (optional).
        k: Number of nearest chunks per probe.

    Returns:
        List of ``{"label", "probe", "matches": [...]}`` dicts.
    """
    probe_texts = [t for _, t in probes]
    probe_emb, _ = embed_texts(probe_texts, model=model, show_progress=False)
    sims = cosine_sim(probe_emb, chunk_emb)
    results: List[Dict] = []
    for idx, (label, text) in enumerate(probes):
        top_idx = np.argsort(sims[idx])[-k:][::-1]
        matches = [
            {"cite_key": chunk_keys[j], "similarity": float(sims[idx, j])}
            for j in top_idx
        ]
        results.append({"label": label, "probe": text, "matches": matches})
    return results


def reviewer_response_prep(
    objections: Sequence[Tuple[str, str]],
    paper_chunks: List[Dict],
    paper_emb: np.ndarray,
    ref_chunk_keys: List[str],
    ref_chunk_texts: List[str],
    ref_chunk_emb: np.ndarray,
    model=None,
    k: int = 3,
) -> List[Dict]:
    """For each likely objection, find supporting evidence in paper and literature.

    Args:
        objections: ``[(label, objection_text), ...]`` pairs.
        paper_chunks: Paper paragraph dicts (with ``line``, ``text``).
        paper_emb: Embeddings for paper chunks.
        ref_chunk_keys: Cite key for each reference chunk.
        ref_chunk_texts: Text for each reference chunk.
        ref_chunk_emb: Embeddings for reference chunks.
        model: Pre-loaded embedding model (optional).
        k: Number of matches to return per source.

    Returns:
        List of dicts with ``objection``, ``objection_text``,
        ``paper_evidence``, ``literature_support``.
    """
    obj_texts = [text for _, text in objections]
    obj_emb, _ = embed_texts(obj_texts, model=model, show_progress=False)

    paper_sims = cosine_sim(obj_emb, paper_emb)
    lit_sims = cosine_sim(obj_emb, ref_chunk_emb)

    results: List[Dict] = []
    for idx, (label, text) in enumerate(objections):
        paper_top = np.argsort(paper_sims[idx])[-k:][::-1]
        paper_matches = [
            {
                "line": paper_chunks[j]["line"],
                "text": paper_chunks[j]["text"][:150],
                "similarity": float(paper_sims[idx, j]),
            }
            for j in paper_top
        ]
        lit_top = np.argsort(lit_sims[idx])[-k:][::-1]
        lit_matches = [
            {
                "cite_key": ref_chunk_keys[j],
                "text": ref_chunk_texts[j][:150],
                "similarity": float(lit_sims[idx, j]),
            }
            for j in lit_top
        ]
        results.append({
            "objection": label,
            "objection_text": text,
            "paper_evidence": paper_matches,
            "literature_support": lit_matches,
        })
    return results
