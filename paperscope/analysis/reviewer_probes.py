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
