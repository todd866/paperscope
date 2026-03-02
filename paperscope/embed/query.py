"""Query the claim embedding space for neighbors, conflicts, and gaps."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


def find_nearest(
    query_embedding: np.ndarray,
    embeddings: np.ndarray,
    index: Dict,
    k: int = 10,
) -> List[Dict]:
    """Find k nearest claims to a query embedding.

    Args:
        query_embedding: Query vector (1D)
        embeddings: All claim embeddings (2D)
        index: Index dict with 'claims' list
        k: Number of neighbors

    Returns:
        List of dicts with 'claim', 'similarity', 'cite_key'
    """
    # Cosine similarity
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    emb_norms = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    similarities = emb_norms @ query_norm

    top_k = np.argsort(similarities)[-k:][::-1]

    results = []
    claims = index["claims"]
    for idx in top_k:
        results.append({
            **claims[idx],
            "similarity": float(similarities[idx]),
        })

    return results


def find_similar_claims(
    embeddings: np.ndarray,
    index: Dict,
    threshold: float = 0.85,
) -> List[Tuple[Dict, Dict, float]]:
    """Find pairs of highly similar claims (potential duplicates or contradictions).

    Args:
        embeddings: All claim embeddings
        index: Index dict
        threshold: Minimum cosine similarity

    Returns:
        List of (claim_a, claim_b, similarity) tuples
    """
    emb_norms = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    sim_matrix = emb_norms @ emb_norms.T

    # Zero diagonal and below
    np.fill_diagonal(sim_matrix, 0)
    sim_matrix = np.triu(sim_matrix)

    pairs = np.argwhere(sim_matrix >= threshold)
    claims = index["claims"]

    results = []
    for i, j in pairs:
        results.append((
            claims[i],
            claims[j],
            float(sim_matrix[i, j]),
        ))

    return sorted(results, key=lambda x: x[2], reverse=True)


def find_gaps(
    query_text: str,
    embeddings: np.ndarray,
    index: Dict,
    model=None,
    threshold: float = 0.5,
) -> Dict:
    """Check if a claim has support in the literature.

    Args:
        query_text: The claim to check
        embeddings: All claim embeddings
        index: Index dict
        model: sentence-transformers model
        threshold: Maximum similarity to consider a "gap"

    Returns:
        Dict with 'query', 'nearest', 'is_gap', 'max_similarity'
    """
    if model is None:
        from .embed_claims import load_model
        model = load_model()

    query_emb = model.encode([query_text])[0]
    nearest = find_nearest(query_emb, embeddings, index, k=5)

    max_sim = nearest[0]["similarity"] if nearest else 0.0

    return {
        "query": query_text,
        "nearest": nearest,
        "is_gap": max_sim < threshold,
        "max_similarity": max_sim,
    }
