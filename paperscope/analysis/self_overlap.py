"""Self-overlap check: detect high-similarity passages with other papers by the same author."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import numpy as np

from ..text import chunk_text
from ..embed import embed_texts
from ..embed.similarity import cosine_sim


def self_overlap_check(
    paper_chunks: List[Dict],
    paper_emb: np.ndarray,
    other_papers: Dict[str, str],
    threshold: float = 0.75,
    max_report: int = 10,
    model=None,
) -> Dict[str, Dict]:
    """Find high-similarity passages between the target paper and other papers.

    Args:
        paper_chunks: Target paper paragraph dicts (``line``, ``text``).
        paper_emb: Embeddings for target paper chunks.
        other_papers: ``{label: full_text}`` dict of comparison papers.
        threshold: Cosine similarity threshold for flagging overlap.
        max_report: Maximum overlapping pairs to report per paper.
        model: Pre-loaded embedding model.

    Returns:
        ``{label: {"n_chunks_compared", "mean_max_similarity",
        "n_high_overlap", "top_overlaps": [...]}}``
    """
    results: Dict[str, Dict] = {}
    for label, text in other_papers.items():
        other_chunks = chunk_text(text)
        if not other_chunks:
            continue
        other_emb, _ = embed_texts(other_chunks, model=model, show_progress=False)

        sims = cosine_sim(paper_emb, other_emb)
        overlaps: List[Dict] = []
        for i in range(sims.shape[0]):
            for j in range(sims.shape[1]):
                if sims[i, j] > threshold:
                    overlaps.append({
                        "paper_line": paper_chunks[i]["line"],
                        "paper_text": paper_chunks[i]["text"][:150],
                        "other_text": other_chunks[j][:150],
                        "similarity": float(sims[i, j]),
                    })
        overlaps.sort(key=lambda x: x["similarity"], reverse=True)

        max_sim_per_chunk = np.max(sims, axis=1)
        results[label] = {
            "n_chunks_compared": len(other_chunks),
            "mean_max_similarity": float(np.mean(max_sim_per_chunk)),
            "n_high_overlap": len(overlaps),
            "top_overlaps": overlaps[:max_report],
        }
    return results
