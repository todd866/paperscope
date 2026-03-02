"""Cosine similarity utilities for embedding vectors."""

from __future__ import annotations

from typing import Dict, List, Sequence

import numpy as np


def cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute cosine similarity matrix between two sets of vectors.

    Args:
        a: Array of shape ``(m, d)``.
        b: Array of shape ``(n, d)``.

    Returns:
        Similarity matrix of shape ``(m, n)`` with values in ``[-1, 1]``.
    """
    a_n = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
    b_n = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
    return a_n @ b_n.T


def nearest_items(
    row: np.ndarray,
    items: Sequence[Dict],
    k: int = 5,
    key_field: str = "cite_key",
) -> List[Dict]:
    """Return top-k items from a similarity row.

    Args:
        row: 1-D similarity scores (one per item).
        items: Sequence of dicts (must have *key_field*).
        k: Number of results.
        key_field: Field name to include in output.

    Returns:
        Top-k items as ``[{key_field: ..., "similarity": float}, ...]``.
    """
    k = min(k, len(row))
    order = np.argsort(row)[-k:][::-1]
    return [
        {key_field: items[int(idx)][key_field], "similarity": float(row[idx])}
        for idx in order
    ]


def pairwise_max_sim(emb_a: np.ndarray, emb_b: np.ndarray) -> float:
    """Maximum cosine similarity between any pair from two embedding sets.

    Useful for comparing chunked representations of two documents.
    """
    sims = cosine_sim(emb_a, emb_b)
    return float(np.max(sims)) if sims.size else 0.0
