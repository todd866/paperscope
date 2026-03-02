"""Higher-level parsing: sentences, paragraphs, and citation contexts from LaTeX."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from .latex import clean_latex, extract_cite_keys


def split_sentences(paragraph: str) -> List[str]:
    """Split a paragraph into sentence-like units.

    Uses a simple heuristic: split on sentence-ending punctuation followed
    by whitespace and a capital letter or backslash.
    """
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\\])", paragraph)
    return [p.strip() for p in parts if p.strip()] or [paragraph.strip()]


def extract_paragraphs(tex_text: str, min_words: int = 10) -> List[Dict]:
    """Extract cleaned paragraphs from a LaTeX document body.

    Returns list of ``{"line": int, "text": str}`` dicts with
    line numbers referencing the original .tex file.
    """
    # Strip bibliography and everything after
    body = re.split(
        r"\\bibliography\{|\\begin\{thebibliography\}", tex_text, maxsplit=1
    )[0]
    # Remove preamble
    begin = body.find(r"\begin{document}")
    if begin >= 0:
        body = body[begin:]

    paragraphs: List[Dict] = []
    current_lines: List[str] = []
    start_line = 1

    for lineno, line in enumerate(body.splitlines(), 1):
        stripped = line.strip()
        if stripped:
            if not current_lines:
                start_line = lineno
            current_lines.append(stripped)
        elif current_lines:
            para = " ".join(current_lines)
            cleaned = clean_latex(para)
            if len(cleaned.split()) >= min_words:
                paragraphs.append({"line": start_line, "text": cleaned})
            current_lines = []

    # Flush remaining
    if current_lines:
        para = " ".join(current_lines)
        cleaned = clean_latex(para)
        if len(cleaned.split()) >= min_words:
            paragraphs.append({"line": start_line, "text": cleaned})

    return paragraphs


def extract_citation_contexts(tex_text: str) -> List[Dict]:
    """Extract sentences containing ``\\cite`` commands from the document body.

    Returns list of dicts with keys:
        - ``id``: sequential identifier (CTX01, CTX02, ...)
        - ``line``: starting line number of the containing paragraph
        - ``text``: cleaned plain-text version of the sentence
        - ``cited_keys``: list of citation keys referenced
    """
    # Strip bibliography
    body = re.split(
        r"\\bibliography\{|\\begin\{thebibliography\}", tex_text, maxsplit=1
    )[0]
    lines = body.splitlines()
    contexts: List[Dict] = []
    para_lines: List[Tuple[int, str]] = []

    def flush() -> None:
        nonlocal para_lines
        if not para_lines:
            return
        start = para_lines[0][0]
        para = " ".join(l for _, l in para_lines).strip()
        if "\\cite" in para:
            for sent in split_sentences(para):
                keys = extract_cite_keys(sent)
                if not keys:
                    continue
                cleaned = clean_latex(sent)
                if len(cleaned.split()) < 4:
                    cleaned = clean_latex(para)
                contexts.append({
                    "id": f"CTX{len(contexts) + 1:02d}",
                    "line": start,
                    "text": cleaned,
                    "cited_keys": keys,
                })
        para_lines = []

    for lineno, line in enumerate(lines, 1):
        if line.strip():
            para_lines.append((lineno, line.rstrip()))
        else:
            flush()
    flush()
    return contexts


def extract_claims(tex_text: str) -> List[Dict]:
    """Extract key claims: bold/textbf assertions and prediction items.

    Returns list of dicts with keys: ``id``, ``line``, ``text``, ``type``.
    """
    claims: List[Dict] = []
    for m in re.finditer(r"\\textbf\{([^}]+)\}", tex_text):
        text = clean_latex(m.group(1))
        if len(text.split()) >= 3:
            line = tex_text[: m.start()].count("\n") + 1
            claims.append({
                "id": f"CLM{len(claims) + 1:02d}",
                "line": line,
                "text": text,
                "type": "bold_claim",
            })
    for m in re.finditer(
        r"\\textbf\{Prediction \d+[^}]*\}[:\s]*([^\\]+?)(?=\\item|\\end|\\textbf|\n\n)",
        tex_text,
        re.DOTALL,
    ):
        text = clean_latex(m.group(0))
        if len(text.split()) >= 5:
            line = tex_text[: m.start()].count("\n") + 1
            claims.append({
                "id": f"PRD{len(claims) + 1:02d}",
                "line": line,
                "text": text,
                "type": "prediction",
            })
    return claims
