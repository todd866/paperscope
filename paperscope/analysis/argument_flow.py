"""Argument flow analysis: track a paper's trajectory through semantic space."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ..embed.similarity import cosine_sim


def argument_flow(
    paper_chunks: List[Dict],
    paper_emb: np.ndarray,
    jump_sigma: float = 1.5,
    loop_min_gap: int = 5,
    loop_threshold: float = 0.85,
) -> Dict:
    """Analyse how a paper moves through semantic space paragraph by paragraph.

    Detects topic jumps (large consecutive distances) and semantic loops
    (distant paragraphs that are semantically similar).

    Args:
        paper_chunks: Paper paragraph dicts (``line``, ``text``).
        paper_emb: Embeddings for paper chunks.
        jump_sigma: Standard deviations above mean to flag a jump.
        loop_min_gap: Minimum paragraph gap to consider a loop.
        loop_threshold: Cosine similarity threshold for loops.

    Returns:
        Dict with ``n_paragraphs``, ``mean_step_distance``, ``jumps``,
        ``loops``.
    """
    norms = paper_emb / (np.linalg.norm(paper_emb, axis=1, keepdims=True) + 1e-12)
    step_sims = np.array([
        float(np.dot(norms[i], norms[i + 1]))
        for i in range(len(norms) - 1)
    ])
    step_distances = 1 - step_sims

    mean_dist = float(np.mean(step_distances))
    std_dist = float(np.std(step_distances))
    threshold = mean_dist + jump_sigma * std_dist

    jumps: List[Dict] = []
    for i, d in enumerate(step_distances):
        if d > threshold:
            jumps.append({
                "from_line": paper_chunks[i]["line"],
                "to_line": paper_chunks[i + 1]["line"],
                "distance": float(d),
                "from_text": paper_chunks[i]["text"][:80],
                "to_text": paper_chunks[i + 1]["text"][:80],
            })

    loops: List[Dict] = []
    for i in range(len(paper_chunks)):
        for j in range(i + loop_min_gap, len(paper_chunks)):
            sim = float(np.dot(norms[i], norms[j]))
            if sim > loop_threshold:
                loops.append({
                    "line_a": paper_chunks[i]["line"],
                    "line_b": paper_chunks[j]["line"],
                    "similarity": sim,
                    "text_a": paper_chunks[i]["text"][:100],
                    "text_b": paper_chunks[j]["text"][:100],
                })
    loops.sort(key=lambda x: x["similarity"], reverse=True)

    return {
        "n_paragraphs": len(paper_chunks),
        "mean_step_distance": mean_dist,
        "std_step_distance": std_dist,
        "step_distances": [float(d) for d in step_distances],
        "jumps": jumps,
        "loops": loops[:20],
    }


def plot_argument_flow(
    flow_result: Dict,
    paper_emb: np.ndarray,
    paper_chunks: List[Dict],
    output_path: Path,
) -> None:
    """Generate argument flow visualization (PCA trajectory + step-distance bar chart).

    Requires matplotlib and sklearn. Skipped silently if unavailable.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.decomposition import PCA
    except ImportError:
        return

    pca = PCA(n_components=2)
    coords = pca.fit_transform(paper_emb)
    lines = np.array([c["line"] for c in paper_chunks])
    step_distances = flow_result["step_distances"]
    mean_dist = flow_result["mean_step_distance"]
    std_dist = flow_result["std_step_distance"]

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Left: trajectory
    ax = axes[0]
    scatter = ax.scatter(
        coords[:, 0], coords[:, 1], c=lines, cmap="viridis",
        s=30, zorder=3, edgecolors="white", linewidths=0.3,
    )
    for i in range(len(coords) - 1):
        alpha = 0.3 if step_distances[i] < mean_dist + std_dist else 0.7
        color = "red" if step_distances[i] > mean_dist + 1.5 * std_dist else "gray"
        ax.annotate(
            "", xy=(coords[i + 1, 0], coords[i + 1, 1]),
            xytext=(coords[i, 0], coords[i, 1]),
            arrowprops=dict(arrowstyle="->", color=color, alpha=alpha, lw=0.6),
        )
    plt.colorbar(scatter, ax=ax, label="Line number", shrink=0.8)
    ax.set_title("Argument Flow Through Semantic Space", fontsize=9)
    ax.set_xlabel(f"PC1 ({pca.explained_variance_ratio_[0]:.1%})")
    ax.set_ylabel(f"PC2 ({pca.explained_variance_ratio_[1]:.1%})")

    # Right: step distances
    ax = axes[1]
    colors = [
        "red" if d > mean_dist + 1.5 * std_dist else "steelblue"
        for d in step_distances
    ]
    ax.bar(range(len(step_distances)), step_distances, color=colors, alpha=0.7, width=1.0)
    ax.axhline(mean_dist, color="gray", ls="--", lw=0.8, label=f"mean={mean_dist:.3f}")
    ax.axhline(
        mean_dist + 1.5 * std_dist, color="red", ls="--", lw=0.8,
        label=f"threshold={mean_dist + 1.5 * std_dist:.3f}",
    )
    ax.set_xlabel("Paragraph index")
    ax.set_ylabel("Cosine distance to next paragraph")
    ax.set_title("Step-by-Step Semantic Distance", fontsize=9)
    ax.legend(fontsize=7)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=200)
    plt.close(fig)
