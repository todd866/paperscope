"""Vector embedding space for claims and queries."""

from .embed_claims import embed_texts, load_model
from .similarity import cosine_sim

__all__ = [
    "embed_texts",
    "load_model",
    "cosine_sim",
]
