"""Vector embedding space for claims and queries."""

from .embed_claims import embed_texts, embed_groups, embed_claims, load_model
from .similarity import cosine_sim, nearest_items, pairwise_max_sim

__all__ = [
    "embed_texts",
    "embed_groups",
    "embed_claims",
    "load_model",
    "cosine_sim",
    "nearest_items",
    "pairwise_max_sim",
]
