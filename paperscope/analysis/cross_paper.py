"""Cross-paper consistency: detect shared-topic passages that may contain contradictions."""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from ..text import chunk_text
from ..embed import embed_texts
from ..embed.similarity import cosine_sim


def cross_paper_consistency(
    paper_chunks: List[Dict],
    paper_emb: np.ndarray,
    other_papers: Dict[str, str],
    threshold: float = 0.7,
    max_report: int = 8,
    model=None,
) -> Dict[str, Dict]:
    """Find semantically similar passages between papers for consistency review.

    High similarity + different wording = potential inconsistency. Results
    are for manual review, not automatic flagging.

    Args:
        paper_chunks: Target paper paragraph dicts (``line``, ``text``).
        paper_emb: Embeddings for target paper.
        other_papers: ``{label: full_text}`` of comparison papers.
        threshold: Minimum similarity to flag.
        max_report: Max pairs per paper.
        model: Pre-loaded embedding model.

    Returns:
        ``{label: {"mean_max_similarity", "n_high_similarity", "top_pairs"}}``
    """
    results: Dict[str, Dict] = {}
    for label, text in other_papers.items():
        other_chunks = chunk_text(text)
        if not other_chunks:
            continue
        other_emb, _ = embed_texts(other_chunks, model=model, show_progress=False)

        sims = cosine_sim(paper_emb, other_emb)
        pairs: List[Dict] = []
        for i in range(sims.shape[0]):
            best_j = int(np.argmax(sims[i]))
            if sims[i, best_j] > threshold:
                pairs.append({
                    "paper_line": paper_chunks[i]["line"],
                    "paper_text": paper_chunks[i]["text"][:200],
                    "other_text": other_chunks[best_j][:200],
                    "similarity": float(sims[i, best_j]),
                })
        pairs.sort(key=lambda x: x["similarity"], reverse=True)

        max_per_chunk = np.max(sims, axis=1)
        results[label] = {
            "mean_max_similarity": float(np.mean(max_per_chunk)),
            "median_max_similarity": float(np.median(max_per_chunk)),
            "n_high_similarity": len(pairs),
            "top_pairs": pairs[:max_report],
        }
    return results
