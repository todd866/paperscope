"""Strength heatmap: per-paragraph support strength from citations and argument flow."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ..embed.similarity import cosine_sim


def strength_heatmap(
    paper_chunks: List[Dict],
    paper_emb: np.ndarray,
    chunk_keys: List[str],
    chunk_emb: np.ndarray,
) -> Dict:
    """For each paragraph, measure citation support and argument continuity.

    Returns:
        Dict with ``paragraphs`` (list of per-paragraph scores) and
        ``summary`` statistics.
    """
    n = len(paper_chunks)
    if n == 0:
        return {"paragraphs": [], "summary": {}}

    # Citation support: best similarity to any literature chunk
    lit_sims = cosine_sim(paper_emb, chunk_emb)
    best_lit_sim = np.max(lit_sims, axis=1)
    best_lit_key = [chunk_keys[int(np.argmax(lit_sims[i]))] for i in range(n)]

    # Argument continuity: similarity to preceding paragraph
    norms = paper_emb / (np.linalg.norm(paper_emb, axis=1, keepdims=True) + 1e-12)
    continuity = np.zeros(n)
    for i in range(1, n):
        continuity[i] = float(np.dot(norms[i], norms[i - 1]))

    paragraphs: List[Dict] = []
    for i in range(n):
        paragraphs.append({
            "line": paper_chunks[i]["line"],
            "text_preview": paper_chunks[i]["text"][:100],
            "citation_support": float(best_lit_sim[i]),
            "best_supporting_ref": best_lit_key[i],
            "argument_continuity": float(continuity[i]),
        })

    return {
        "paragraphs": paragraphs,
        "summary": {
            "mean_citation_support": float(np.mean(best_lit_sim)),
            "min_citation_support": float(np.min(best_lit_sim)),
            "mean_continuity": float(np.mean(continuity[1:])) if n > 1 else 0.0,
            "weak_paragraphs": sum(1 for p in paragraphs if p["citation_support"] < 0.3),
        },
    }


def plot_strength_heatmap(
    heatmap_result: Dict,
    output_path: Path,
) -> None:
    """Generate a dual-bar heatmap of citation support and continuity.

    Requires matplotlib. Skipped silently if unavailable.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    paras = heatmap_result["paragraphs"]
    if not paras:
        return

    n = len(paras)
    support = [p["citation_support"] for p in paras]
    continuity = [p["argument_continuity"] for p in paras]
    indices = range(n)

    fig, axes = plt.subplots(2, 1, figsize=(14, 6), sharex=True)

    ax = axes[0]
    colors = ["#e74c3c" if s < 0.3 else "#2ecc71" if s > 0.5 else "#f39c12" for s in support]
    ax.bar(indices, support, color=colors, alpha=0.8, width=1.0)
    ax.set_ylabel("Citation support")
    ax.set_title("Per-Paragraph Strength", fontsize=10)
    ax.axhline(0.3, color="red", ls="--", lw=0.7, alpha=0.5)

    ax = axes[1]
    ax.bar(indices, continuity, color="steelblue", alpha=0.7, width=1.0)
    ax.set_ylabel("Argument continuity")
    ax.set_xlabel("Paragraph index")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=200)
    plt.close(fig)
