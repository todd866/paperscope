"""Tests for paperscope/analysis/critical_read.py :: extract_author_names.

The function has had two prior bug fixes (address patterns + LaTeX command
filtering) that landed without test coverage. Adding the missing
regression surface so the next "small fix" doesn't reintroduce them.
"""

from __future__ import annotations

from textwrap import dedent

import pytest

from paperscope.analysis.critical_read import extract_author_names


def test_comma_separated_names_above_abstract():
    text = dedent(
        """
        Widgets: a quantitative study

        Alice Smith, Bob Jones, Carol Lee

        Abstract: We did things.
        """
    )
    names = extract_author_names(text)
    assert names == ["Alice Smith", "Bob Jones", "Carol Lee"]


def test_names_with_terminal_and_clause():
    text = dedent(
        """
        Widgets: a paper title

        Alice Smith, Bob Jones and Carol Lee

        Abstract: methods.
        """
    )
    names = extract_author_names(text)
    assert "Alice Smith" in names
    assert "Bob Jones" in names
    assert "Carol Lee" in names


def test_skips_affiliation_lines():
    """Lines mentioning Department/University/Institute must be filtered
    out — they often look name-like but are affiliations."""
    text = dedent(
        """
        Paper Title

        Alice Smith, Bob Jones

        Department of Widgetry, University of Somewhere

        Abstract.
        """
    )
    names = extract_author_names(text)
    assert "Alice Smith" in names
    assert all("Department" not in n for n in names)
    assert all("University" not in n for n in names)


def test_skips_address_pattern_city_state():
    """Regression: a line like 'Sydney, NSW 2050, Australia' looks
    comma-separated and capitalised, but it's a postal address — not
    an author list."""
    text = dedent(
        """
        Title Here

        Sydney, NSW 2050, Australia

        Real Author One, Real Author Two

        Abstract.
        """
    )
    names = extract_author_names(text)
    # The Sydney/NSW line must be rejected; the real author line returned.
    assert "Real Author One" in names
    assert all("NSW" not in n for n in names)
    assert all("Sydney" not in n for n in names)


def test_skips_lines_with_latex_commands():
    """Affiliation lines often carry LaTeX markers (\\\\, \\texttt, \\href)
    — these must not be treated as author lists."""
    text = dedent(
        r"""
        Paper Title

        Alice \texttt{One}, Bob \href{x}{Two}

        Alice Smith, Bob Jones

        Abstract.
        """
    )
    names = extract_author_names(text)
    assert "Alice Smith" in names
    assert all("\\" not in n for n in names)


def test_skips_correspondence_and_email_lines():
    text = dedent(
        """
        Title

        Correspondence: alice@example.com

        Alice Smith, Bob Jones

        Abstract.
        """
    )
    names = extract_author_names(text)
    assert "Alice Smith" in names
    assert all("@" not in n for n in names)


def test_empty_input_returns_empty_list():
    assert extract_author_names("") == []


def test_no_authorlike_lines_returns_empty_list():
    text = "Just one line. Period."
    assert extract_author_names(text) == []


def test_takes_first_plausible_candidate():
    """When multiple comma-separated name-shaped lines appear early, the
    function picks the first one (typical position for the author block)."""
    text = dedent(
        """
        Title One

        Alpha First, Beta Second

        Abstract: ...

        Gamma Third, Delta Fourth
        """
    )
    names = extract_author_names(text)
    assert "Alpha First" in names
    assert "Beta Second" in names


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
