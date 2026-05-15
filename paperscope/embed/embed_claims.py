"""Encode text as vectors using sentence-transformers (with TF-IDF fallback)."""

from __future__ import annotations

from typing import Dict, Sequence, Tuple

import numpy as np


def load_model(model_name: str = "all-MiniLM-L6-v2"):
    """Load a sentence-transformers model."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "'sentence-transformers' package required. "
            "Install with: pip install sentence-transformers"
        )
    return SentenceTransformer(model_name)


def embed_texts(
    texts: Sequence[str],
    model=None,
    model_name: str = "all-MiniLM-L6-v2",
    show_progress: bool = True,
    batch_size: int = 64,
) -> Tuple[np.ndarray, Dict]:
    """Embed a list of strings, with TF-IDF fallback.

    Args:
        texts: Strings to embed.
        model: Pre-loaded SentenceTransformer (optional).
        model_name: Model to load if *model* is not provided.
        show_progress: Show encoding progress bar.
        batch_size: Batch size for encoding.

    Returns:
        ``(embeddings, backend_info)`` where *embeddings* has shape
        ``(len(texts), dim)`` and *backend_info* is a metadata dict.
    """
    text_list = list(texts)
    if not text_list:
        return np.zeros((0, 1)), {"backend": "empty"}

    try:
        if model is None:
            model = load_model(model_name)
        embeddings = model.encode(
            text_list, show_progress_bar=show_progress, batch_size=batch_size
        )
        return np.asarray(embeddings), {
            "backend": "sentence-transformers",
            "model": model_name,
            "n_items": len(text_list),
            "dim": int(embeddings.shape[1]),
        }
    except Exception as exc:
        # TF-IDF fallback
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        embeddings = vectorizer.fit_transform(text_list).toarray()
        return np.asarray(embeddings), {
            "backend": "tfidf",
            "vocabulary_size": len(vectorizer.vocabulary_),
            "n_items": len(text_list),
            "dim": int(embeddings.shape[1]),
            "fallback_reason": str(exc),
        }
