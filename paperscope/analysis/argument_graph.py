"""Argument graph: build a cross-paper dependency graph for a research program."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ..text import clean_latex
from ..embed import embed_texts
from ..embed.similarity import cosine_sim


def _find_tex_files(project_root: Path) -> List[Path]:
    """Find main .tex files, skipping archives and templates."""
    tex_files: List[Path] = []
    for p in sorted(project_root.rglob("*.tex")):
        # Skip common non-paper dirs
        parts = p.parts
        if any(
            skip in parts
            for skip in ("archive", "old", "TEMPLATES", ".git", "node_modules")
        ):
            continue
        # Must have abstract or section to be a paper
        try:
            text = p.read_text(encoding="utf-8", errors="replace")[:5000]
            if "\\begin{abstract}" in text or "\\section{" in text:
                tex_files.append(p)
        except Exception:
            continue
    return tex_files


def _extract_conclusions(tex_text: str) -> List[str]:
    """Extract conclusion/discussion sentences from a paper."""
    # Look for conclusion section
    m = re.search(
        r"\\section\*?\{(?:Conclusion|Discussion|Summary)[^}]*\}(.*?)(?=\\section|\Z)",
        tex_text,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        text = clean_latex(m.group(1))
    else:
        # Fallback: last 500 words
        text = clean_latex(tex_text)
        words = text.split()
        text = " ".join(words[-500:]) if len(words) > 500 else text

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [s.strip() for s in sentences if len(s.split()) >= 8][:15]


def _extract_premises(tex_text: str) -> List[str]:
    """Extract introduction/premise sentences from a paper."""
    m = re.search(
        r"\\section\*?\{(?:Introduction|Background|Motivation)[^}]*\}(.*?)(?=\\section)",
        tex_text,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        text = clean_latex(m.group(1))
    else:
        # Fallback: first 500 words after abstract
        abstract_end = tex_text.find("\\end{abstract}")
        start = abstract_end if abstract_end > 0 else 0
        text = clean_latex(tex_text[start:])
        words = text.split()
        text = " ".join(words[:500])

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [s.strip() for s in sentences if len(s.split()) >= 8][:15]


def build_argument_graph(
    project_root: Path,
    similarity_threshold: float = 0.7,
    model=None,
) -> Dict:
    """Build a directed graph of cross-paper dependencies.

    For each pair of papers, checks whether paper A's conclusions
    support paper B's premises (and vice versa). Returns a graph
    structure suitable for visualization.

    Args:
        project_root: Root directory containing paper subdirectories.
        similarity_threshold: Minimum cosine similarity for an edge.
        model: Pre-loaded embedding model.

    Returns:
        Dict with ``nodes`` (papers), ``edges`` (dependencies), and
        ``stats``.
    """
    tex_files = _find_tex_files(project_root)
    if len(tex_files) < 2:
        return {"error": f"Found {len(tex_files)} papers, need at least 2"}

    papers: List[Dict] = []
    for tex_path in tex_files:
        tex_text = tex_path.read_text(encoding="utf-8", errors="replace")
        conclusions = _extract_conclusions(tex_text)
        premises = _extract_premises(tex_text)
        if conclusions or premises:
            # Use folder name as label
            label = tex_path.parent.name
            if label in (".", "revisions"):
                label = tex_path.stem
            papers.append({
                "path": str(tex_path),
                "label": label,
                "conclusions": conclusions,
                "premises": premises,
            })

    if len(papers) < 2:
        return {"error": "Not enough papers with extractable content"}

    # Embed all conclusions and premises
    conclusion_texts: List[str] = []
    conclusion_paper_idx: List[int] = []
    premise_texts: List[str] = []
    premise_paper_idx: List[int] = []

    for i, paper in enumerate(papers):
        for c in paper["conclusions"]:
            conclusion_texts.append(c)
            conclusion_paper_idx.append(i)
        for p in paper["premises"]:
            premise_texts.append(p)
            premise_paper_idx.append(i)

    if not conclusion_texts or not premise_texts:
        return {"error": "No conclusions or premises extracted"}

    all_texts = conclusion_texts + premise_texts
    emb, backend = embed_texts(all_texts, model=model, show_progress=False)
    conc_emb = emb[: len(conclusion_texts)]
    prem_emb = emb[len(conclusion_texts) :]

    # Cross-paper similarities: conclusion A -> premise B
    sims = cosine_sim(conc_emb, prem_emb)

    edges: List[Dict] = []
    for ci in range(len(conclusion_texts)):
        for pi in range(len(premise_texts)):
            paper_a = conclusion_paper_idx[ci]
            paper_b = premise_paper_idx[pi]
            if paper_a == paper_b:
                continue
            if sims[ci, pi] > similarity_threshold:
                edges.append({
                    "from": papers[paper_a]["label"],
                    "to": papers[paper_b]["label"],
                    "similarity": float(sims[ci, pi]),
                    "conclusion": conclusion_texts[ci][:100],
                    "premise": premise_texts[pi][:100],
                })

    # Deduplicate edges (keep strongest per pair)
    edge_map: Dict[tuple, Dict] = {}
    for e in edges:
        key = (e["from"], e["to"])
        if key not in edge_map or e["similarity"] > edge_map[key]["similarity"]:
            edge_map[key] = e
    edges = sorted(edge_map.values(), key=lambda x: x["similarity"], reverse=True)

    nodes = [
        {
            "label": p["label"],
            "n_conclusions": len(p["conclusions"]),
            "n_premises": len(p["premises"]),
        }
        for p in papers
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "n_papers": len(papers),
            "n_edges": len(edges),
            "mean_edge_sim": (
                float(np.mean([e["similarity"] for e in edges])) if edges else 0.0
            ),
        },
        "backend": backend,
    }


def plot_argument_graph(graph_result: Dict, output_path: Path) -> None:
    """Render the argument graph using networkx + matplotlib.

    Skipped silently if dependencies unavailable.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx
    except ImportError:
        return

    nodes = graph_result.get("nodes", [])
    edges = graph_result.get("edges", [])
    if not nodes:
        return

    G = nx.DiGraph()
    for node in nodes:
        G.add_node(node["label"])
    for edge in edges:
        G.add_edge(
            edge["from"], edge["to"],
            weight=edge["similarity"],
        )

    fig, ax = plt.subplots(figsize=(14, 10))
    pos = nx.spring_layout(G, k=2.0, seed=42)

    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=800, node_color="#3498db", alpha=0.8)
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=6)

    if edges:
        weights = [G[u][v]["weight"] for u, v in G.edges()]
        min_w = min(weights) if weights else 0
        max_w = max(weights) if weights else 1
        widths = [1 + 3 * (w - min_w) / (max_w - min_w + 1e-6) for w in weights]
        nx.draw_networkx_edges(
            G, pos, ax=ax, width=widths, alpha=0.6,
            edge_color="gray", arrows=True, arrowsize=15,
        )

    ax.set_title(
        f"Cross-Paper Argument Graph ({len(nodes)} papers, {len(edges)} dependencies)",
        fontsize=10,
    )
    ax.axis("off")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=200)
    plt.close(fig)
