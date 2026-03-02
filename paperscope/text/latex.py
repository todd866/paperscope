"""LaTeX text cleaning and citation key extraction."""

from __future__ import annotations

import re
from typing import List


def clean_latex(text: str) -> str:
    """Strip LaTeX commands, math, URLs and special characters to plain text.

    Handles nested commands (up to 6 levels), inline math, environments,
    and common escapes. Returns clean, whitespace-normalized text.
    """
    # Remove citation/ref/label/url commands entirely
    text = re.sub(r"\\(?:cite\w*|ref|eqref|label|url|href)\{[^}]*\}", " ", text)
    # Replace inline math with placeholder
    text = re.sub(r"\$[^$]*\$", " MATH ", text)
    # Remove environment markers
    text = re.sub(r"\\begin\{[^}]+\}", " ", text)
    text = re.sub(r"\\end\{[^}]+\}", " ", text)
    # Unwrap nested commands: \cmd[opt]{content} -> content
    pattern = re.compile(r"\\[a-zA-Z*]+(?:\[[^\]]*\])?\{([^{}]*)\}")
    for _ in range(6):
        new = pattern.sub(r" \1 ", text)
        if new == text:
            break
        text = new
    # Remove remaining bare commands
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    # Clean special characters
    text = text.replace("~", " ").replace("---", " \u2014 ").replace("--", "\u2013")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\b10\.\S+", " ", text)  # bare DOIs
    text = re.sub(r"[{}_^%&]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_cite_keys(text: str) -> List[str]:
    """Extract citation keys from LaTeX \\cite commands.

    Handles \\cite, \\citep, \\citet, \\citeauthor, etc.
    Returns keys in order of appearance, with duplicates preserved.
    """
    keys: List[str] = []
    for m in re.finditer(r"\\(?:cite\w*)\{([^}]+)\}", text):
        for k in m.group(1).split(","):
            k = k.strip()
            if k and k != "*":
                keys.append(k)
    return keys


def clean_plaintext(text: str) -> str:
    """Clean extracted plain text (from PDFs, web pages, etc.)."""
    text = text.replace("\x0c", " ")
    text = re.sub(r"-\s+\n", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
