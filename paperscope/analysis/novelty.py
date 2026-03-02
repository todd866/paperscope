"""Novelty analysis: which claims are furthest from existing literature?"""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from ..embed.similarity import cosine_sim


def novelty_analysis(
    claims: List[Dict],
    claim_emb: np.ndarray,
    chunk_keys: List[str],
    chunk_emb: np.ndarray,
    k: int = 3,
    threshold: float = 0.4,
) -> List[Dict]:
    """Rank claims by distance from literature. Low max similarity = high novelty.

    Args:
        claims: Claim dicts (with ``text``).
        claim_emb: Embeddings for claims.
        chunk_keys: Cite key for each literature chunk.
        chunk_emb: Embeddings for literature chunks.
        k: Number of nearest literature chunks to return per claim.
        threshold: Claims with ``max_sim < threshold`` get ``novelty_flag=True``.

    Returns:
        Claims sorted by ascending max similarity (most novel first),
        each enriched with ``max_literature_similarity``, ``nearest_refs``,
        ``novelty_flag``.
    """
    sims = cosine_sim(claim_emb, chunk_emb)
    results: List[Dict] = []
    for i, claim in enumerate(claims):
        top_idx = np.argsort(sims[i])[-k:][::-1]
        nearest = [
            {"cite_key": chunk_keys[j], "similarity": float(sims[i, j])}
            for j in top_idx
        ]
        max_sim = float(np.max(sims[i]))
        results.append({
            **claim,
            "max_literature_similarity": max_sim,
            "nearest_refs": nearest,
            "novelty_flag": max_sim < threshold,
        })
    results.sort(key=lambda x: x["max_literature_similarity"])
    return results
