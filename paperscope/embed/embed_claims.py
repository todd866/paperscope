"""Encode text as vectors using sentence-transformers (with TF-IDF fallback)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

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


def embed_groups(
    groups: Sequence[Tuple[str, Sequence[str]]],
    model=None,
    model_name: str = "all-MiniLM-L6-v2",
) -> Tuple[Dict[str, np.ndarray], Dict]:
    """Embed multiple named groups in a single batch.

    Args:
        groups: ``[(name, texts), ...]`` pairs.
        model: Pre-loaded model (optional).
        model_name: Model to load if not provided.

    Returns:
        ``(outputs, backend_info)`` where *outputs* maps group names
        to embedding arrays.
    """
    sizes = {name: len(texts) for name, texts in groups}
    all_texts = [text for _, texts in groups for text in texts]
    embeddings, backend = embed_texts(
        all_texts, model=model, model_name=model_name, show_progress=False
    )

    outputs: Dict[str, np.ndarray] = {}
    start = 0
    for name, _ in groups:
        size = sizes[name]
        outputs[name] = embeddings[start : start + size]
        start += size
    return outputs, backend


def embed_claims(
    claims: List[Dict],
    model=None,
    model_name: str = "all-MiniLM-L6-v2",
) -> np.ndarray:
    """Embed a list of claim dicts (must have ``"text"`` field).

    Returns numpy array of shape ``(n_claims, dim)``.
    """
    texts = [c["text"] for c in claims]
    embeddings, _ = embed_texts(texts, model=model, model_name=model_name)
    return embeddings


def save_embeddings(
    embeddings: np.ndarray,
    claims: List[Dict],
    embeddings_path: Path,
    index_path: Path,
) -> None:
    """Save embeddings and their index."""
    embeddings_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(embeddings_path), embeddings)

    index = {
        "model": "all-MiniLM-L6-v2",
        "n_claims": len(claims),
        "embedding_dim": embeddings.shape[1],
        "claims": claims,
    }
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def load_embeddings(embeddings_path: Path, index_path: Path) -> tuple:
    """Load embeddings and index.

    Returns ``(embeddings_array, index_dict)``.
    """
    embeddings = np.load(str(embeddings_path))
    with open(index_path) as f:
        index = json.load(f)
    return embeddings, index
