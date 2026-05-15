"""Cosine similarity utilities for embedding vectors."""

from __future__ import annotations

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
