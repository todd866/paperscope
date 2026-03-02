"""Text chunking with configurable size and overlap."""

from __future__ import annotations

from typing import List


def chunk_text(
    text: str,
    target_words: int = 200,
    overlap_words: int = 50,
    min_chunk_words: int = 20,
) -> List[str]:
    """Split text into overlapping word-level chunks.

    Uses a step-based approach: each chunk starts ``step = target - overlap``
    words after the previous one, ensuring consistent coverage.

    Args:
        text: Input text.
        target_words: Target number of words per chunk.
        overlap_words: Number of words shared between consecutive chunks.
        min_chunk_words: Discard trailing chunks smaller than this.

    Returns:
        List of chunk strings. Returns ``[text]`` if input is shorter than
        *target_words*, or ``[]`` if input is empty.
    """
    words = text.split()
    if not words:
        return []
    if len(words) <= target_words:
        return [" ".join(words)]

    chunks: List[str] = []
    step = max(target_words - overlap_words, 1)
    start = 0
    while start < len(words):
        end = min(start + target_words, len(words))
        chunk = " ".join(words[start:end])
        if len(chunk.split()) >= min_chunk_words:
            chunks.append(chunk)
        if end == len(words):
            break
        start += step
    return chunks
