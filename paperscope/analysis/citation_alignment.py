"""Citation alignment analysis: do cited references actually match the citing sentence?"""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from ..embed.similarity import cosine_sim


def citation_alignment(
    contexts: List[Dict],
    ctx_emb: np.ndarray,
    chunk_keys: List[str],
    chunk_emb: np.ndarray,
    k: int = 5,
) -> List[Dict]:
    """For each citation context, find nearest literature chunks and check cited refs.

    Args:
        contexts: Citation context dicts (with ``cited_keys``).
        ctx_emb: Embeddings for contexts.
        chunk_keys: Cite key for each literature chunk.
        chunk_emb: Embeddings for literature chunks.
        k: Number of nearest chunks to return.

    Returns:
        Enriched context dicts with ``top_matches``, ``cited_similarities``,
        ``best_cited_sim``, ``any_cited_in_top3``.
    """
    sims = cosine_sim(ctx_emb, chunk_emb)
    results: List[Dict] = []
    for i, ctx in enumerate(contexts):
        top_idx = np.argsort(sims[i])[-k:][::-1]
        top_matches = [
            {"cite_key": chunk_keys[j], "similarity": float(sims[i, j])}
            for j in top_idx
        ]
        cited_sims: Dict[str, float] = {}
        for key in ctx["cited_keys"]:
            key_indices = [j for j, ck in enumerate(chunk_keys) if ck == key]
            cited_sims[key] = (
                float(max(sims[i, j] for j in key_indices)) if key_indices else 0.0
            )
        top_keys = [m["cite_key"] for m in top_matches[:3]]
        any_cited_in_top3 = any(k in top_keys for k in ctx["cited_keys"])
        results.append({
            **ctx,
            "top_matches": top_matches,
            "cited_similarities": cited_sims,
            "best_cited_sim": max(cited_sims.values()) if cited_sims else 0.0,
            "any_cited_in_top3": any_cited_in_top3,
        })
    return results


def uncited_relevance(
    contexts: List[Dict],
    ctx_emb: np.ndarray,
    ref_keys: List[str],
    chunk_keys: List[str],
    chunk_emb: np.ndarray,
) -> List[Dict]:
    """Find references semantically relevant to the paper but not cited anywhere.

    Returns ranked list of uncited references with their best-matching context.
    """
    all_cited = set()
    for ctx in contexts:
        all_cited.update(ctx["cited_keys"])

    uncited = [k for k in set(ref_keys) if k not in all_cited]
    if not uncited:
        return []

    sims = cosine_sim(ctx_emb, chunk_emb)
    results: List[Dict] = []
    for key in uncited:
        key_indices = [j for j, ck in enumerate(chunk_keys) if ck == key]
        if not key_indices:
            continue
        max_sim = float(np.max(sims[:, key_indices]))
        best_ctx_idx = int(
            np.unravel_index(
                np.argmax(sims[:, key_indices]),
                (sims.shape[0], len(key_indices)),
            )[0]
        )
        results.append({
            "cite_key": key,
            "max_similarity_to_any_context": max_sim,
            "best_matching_context": contexts[best_ctx_idx]["id"],
            "context_text": contexts[best_ctx_idx]["text"][:120],
        })
    results.sort(key=lambda x: x["max_similarity_to_any_context"], reverse=True)
    return results
