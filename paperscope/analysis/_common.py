"""Shared loading and preparation functions for analysis tools."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..text import clean_latex, chunk_text, extract_paragraphs
from ..text.latex import clean_plaintext
from ..embed import embed_texts


def load_paper(tex_path: Path) -> str:
    """Read a .tex file and return its raw text."""
    return tex_path.read_text(encoding="utf-8", errors="replace")


def load_reference_texts(
    text_dir: Path, min_size: int = 50
) -> Dict[str, str]:
    """Load reference full texts from a directory of .txt files.

    Args:
        text_dir: Directory containing ``<cite_key>.txt`` files.
        min_size: Skip files smaller than this (bytes).

    Returns:
        ``{cite_key: full_text}`` dict.
    """
    refs: Dict[str, str] = {}
    if not text_dir.is_dir():
        return refs
    for txt_file in sorted(text_dir.glob("*.txt")):
        text = txt_file.read_text(encoding="utf-8", errors="replace").strip()
        if len(text) < min_size:
            continue
        refs[txt_file.stem] = clean_plaintext(text)
    return refs


def prepare_paper_chunks(
    tex_text: str,
    chunk_size: int = 200,
    overlap: int = 50,
    min_words: int = 10,
) -> List[Dict]:
    """Extract cleaned paragraphs from a paper with line numbers.

    Returns list of ``{"line": int, "text": str}`` dicts.
    """
    return extract_paragraphs(tex_text, min_words=min_words)


def prepare_reference_chunks(
    ref_texts: Dict[str, str],
    chunk_size: int = 200,
    overlap: int = 50,
) -> Tuple[List[str], List[str]]:
    """Chunk reference texts into passages.

    Args:
        ref_texts: ``{cite_key: full_text}`` dict.
        chunk_size: Target words per chunk.
        overlap: Overlap words between chunks.

    Returns:
        ``(chunk_texts, chunk_keys)`` parallel lists.
    """
    chunk_texts: List[str] = []
    chunk_keys: List[str] = []
    for key, text in sorted(ref_texts.items()):
        for c in chunk_text(text, target_words=chunk_size, overlap_words=overlap):
            chunk_texts.append(c)
            chunk_keys.append(key)
    return chunk_texts, chunk_keys


def embed_and_cache(
    texts: List[str],
    cache_path: Optional[Path] = None,
    model=None,
) -> Tuple[np.ndarray, Dict]:
    """Embed texts with optional .npz caching.

    If *cache_path* exists and has the right count, loads from disk.
    Otherwise embeds and saves.
    """
    if cache_path and cache_path.exists():
        try:
            data = np.load(str(cache_path))
            cached = data["embeddings"]
            if cached.shape[0] == len(texts):
                return cached, {"backend": "cache", "path": str(cache_path)}
        except Exception:
            pass

    embeddings, backend = embed_texts(texts, model=model)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(str(cache_path), embeddings=embeddings)

    return embeddings, backend
