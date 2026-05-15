"""Tests for the shared LaTeX parsing utilities in text/parsing.py.

These cover the section/abstract extractors that abstract_alignment,
method_resolution, and revision_diff all depend on.
"""

from __future__ import annotations

import pytest

from paperscope.text.parsing import (
    extract_abstract,
    extract_paragraphs,
    extract_sections,
    split_sentences,
)


SAMPLE = r"""
\documentclass{article}
\begin{document}
\begin{abstract}
We study \emph{X} and find \textbf{Y}. The result is significant.
\end{abstract}

\section{Introduction}
This is the introduction. It has many words: one two three four five six
seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen
seventeen eighteen nineteen twenty twenty-one.

\section{Short}
Tiny stub.

\section{Methods}
We did things with rigour: alpha beta gamma delta epsilon zeta eta theta
iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi.

\bibliography{refs}
\section{Should Be Stripped}
This section is after the bibliography and must be ignored.
\end{document}
"""


# ---------------------------------------------------------------------------
# extract_abstract
# ---------------------------------------------------------------------------


def test_extract_abstract_raw_returns_latex_markup():
    raw = extract_abstract(SAMPLE)
    assert r"\emph{X}" in raw
    assert r"\textbf{Y}" in raw


def test_extract_abstract_clean_strips_latex_commands():
    cleaned = extract_abstract(SAMPLE, clean=True)
    assert r"\emph" not in cleaned
    assert r"\textbf" not in cleaned
    assert "X" in cleaned and "Y" in cleaned


def test_extract_abstract_no_abstract_returns_empty():
    assert extract_abstract(r"\section{No abstract here}") == ""
    assert extract_abstract(r"\section{No abstract here}", clean=True) == ""


# ---------------------------------------------------------------------------
# extract_sections
# ---------------------------------------------------------------------------


def test_extract_sections_drops_short_sections_below_min_words():
    sections = extract_sections(SAMPLE, min_words=10)
    titles = [s["title"] for s in sections]
    # "Short" has 9 words → dropped at min_words=10
    assert "Introduction" in titles
    assert "Methods" in titles
    assert "Short" not in titles


def test_extract_sections_strict_threshold_drops_more():
    titles_loose = {s["title"] for s in extract_sections(SAMPLE, min_words=10)}
    titles_strict = {s["title"] for s in extract_sections(SAMPLE, min_words=30)}
    # Strict drops at least as many as loose
    assert titles_strict <= titles_loose


def test_extract_sections_strips_bibliography_tail():
    """Anything after \\bibliography{...} must be excluded — even if it
    contains section commands. revision_diff relies on this to avoid
    treating reference lists as content."""
    titles = [s["title"] for s in extract_sections(SAMPLE, min_words=1)]
    assert "Should Be Stripped" not in titles


def test_extract_sections_text_is_cleaned():
    sections = extract_sections(SAMPLE, min_words=10)
    intro = next(s for s in sections if s["title"] == "Introduction")
    assert r"\section" not in intro["text"]
    assert "one two three" in intro["text"]


# ---------------------------------------------------------------------------
# split_sentences / extract_paragraphs — light sanity checks
# ---------------------------------------------------------------------------


def test_split_sentences_basic():
    out = split_sentences("First sentence. Second one! Third? Done.")
    assert out == ["First sentence.", "Second one!", "Third?", "Done."]


def test_split_sentences_fallback_returns_whole_paragraph():
    """When no terminator pattern matches, the whole paragraph comes back
    as a single sentence rather than an empty list."""
    out = split_sentences("no terminators here just a clause")
    assert out == ["no terminators here just a clause"]


def test_extract_paragraphs_skips_short_blocks():
    tex = (
        r"\begin{document}" "\n\n"
        "One two three four five six seven eight nine ten eleven twelve.\n\n"
        "Too short.\n\n"
        "Another long paragraph one two three four five six seven eight "
        "nine ten eleven twelve thirteen.\n"
    )
    paras = extract_paragraphs(tex, min_words=10)
    assert len(paras) == 2  # the "Too short." block is dropped


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
