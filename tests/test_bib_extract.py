"""Regression tests for paperscope/bib/extract.py.

The 675-line citation extractor underpins every downstream paperscope tool;
this file backfills coverage for the parsing logic, the dataclass
behaviour, and end-to-end extraction.

Failures here mean bibliographies will silently produce wrong citation
metadata — exactly the AI-assisted writing failure mode paperscope exists
to catch. Worth defending against regressions.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from paperscope.bib.extract import (
    Reference,
    _clean_bib_value,
    _extract_braced_body,
    _parse_bib_fields,
    deduplicate,
    extract_all,
    extract_cite_keys,
    find_bib_references,
    parse_bib_file,
    parse_bibitem_block,
)


# ---------------------------------------------------------------------------
# Low-level parsing helpers
# ---------------------------------------------------------------------------


def test_extract_braced_body_matches_nested_braces():
    text = "@article{key, title = {Outer {nested} body}, year = 2024}"
    body = _extract_braced_body(text, 0)
    # The outer braces of the entire entry — nested braces preserved.
    assert body is not None
    assert "title = {Outer {nested} body}" in body
    assert "year = 2024" in body


def test_extract_braced_body_returns_none_when_unmatched():
    assert _extract_braced_body("no braces here", 0) is None
    assert _extract_braced_body("{unclosed", 0) is None


def test_parse_bib_fields_braced_quoted_and_numeric_values():
    body = (
        'title = {Brace value}, journal = "Quoted journal", '
        "year = 2024, volume = {7}"
    )
    fields = _parse_bib_fields(body)
    assert fields["title"] == "Brace value"
    assert fields["journal"] == "Quoted journal"
    assert fields["year"] == "2024"
    assert fields["volume"] == "7"


def test_parse_bib_fields_handles_nested_braces_in_value():
    body = "title = {A {B} C}, year = 2020"
    fields = _parse_bib_fields(body)
    assert fields["title"] == "A {B} C"
    assert fields["year"] == "2020"


def test_clean_bib_value_strips_outer_braces_and_collapses_whitespace():
    assert _clean_bib_value("{Hello}") == "Hello"
    assert _clean_bib_value("  multiple   spaces  ") == "multiple spaces"
    assert _clean_bib_value("") == ""


# ---------------------------------------------------------------------------
# parse_bib_file end-to-end
# ---------------------------------------------------------------------------


def _write(path: Path, contents: str) -> Path:
    path.write_text(dedent(contents).strip(), encoding="utf-8")
    return path


def test_parse_bib_file_basic_article(tmp_path):
    bib = _write(
        tmp_path / "refs.bib",
        r"""
        @article{smith2024,
            title = {A study of widgets},
            author = {Smith, A. and Jones, B.},
            journal = {Journal of Widgets},
            year = {2024},
            volume = {12},
            pages = {1--10},
            doi = {10.1234/widgets.2024},
        }
        """,
    )
    refs = parse_bib_file(bib)
    assert len(refs) == 1
    r = refs[0]
    assert r.cite_key == "smith2024"
    assert r.entry_type == "article"
    assert r.title == "A study of widgets"
    assert r.authors == "Smith, A. and Jones, B."
    assert r.journal == "Journal of Widgets"
    assert r.year == "2024"
    assert r.doi == "10.1234/widgets.2024"
    assert r.source_format == "bibtex"


def test_parse_bib_file_picks_up_arxiv_eprint(tmp_path):
    bib = _write(
        tmp_path / "refs.bib",
        r"""
        @article{arxiv_paper,
            title = {Preprint},
            eprint = {2401.12345},
            archiveprefix = {arXiv},
            year = {2024},
        }
        """,
    )
    refs = parse_bib_file(bib)
    assert refs[0].arxiv_id == "2401.12345"


def test_parse_bib_file_multiple_entries(tmp_path):
    bib = _write(
        tmp_path / "refs.bib",
        r"""
        @article{a, title = {A}, year = {2020}}
        @book{b, title = {B}, year = {2021}}
        @inproceedings{c, title = {C}, year = {2022}}
        """,
    )
    refs = parse_bib_file(bib)
    assert [r.cite_key for r in refs] == ["a", "b", "c"]
    assert [r.entry_type for r in refs] == ["article", "book", "inproceedings"]


# ---------------------------------------------------------------------------
# parse_bibitem_block (inline thebibliography environment)
# ---------------------------------------------------------------------------


def test_parse_bibitem_block_medical_style(tmp_path):
    tex = _write(
        tmp_path / "paper.tex",
        r"""
        \begin{thebibliography}{1}
        \bibitem{smith}
        Smith A. A widget study. J Widgets 2024;12:1-10.
        \end{thebibliography}
        """,
    )
    refs = parse_bibitem_block(tex)
    assert len(refs) == 1
    r = refs[0]
    assert r.cite_key == "smith"
    assert r.authors == "Smith A"
    assert r.title == "A widget study"
    assert r.journal == "J Widgets"
    assert r.year == "2024"
    assert r.volume == "12"
    assert r.pages == "1-10"
    assert r.source_format == "bibitem"


def test_parse_bibitem_block_extracts_doi(tmp_path):
    tex = _write(
        tmp_path / "paper.tex",
        r"""
        \begin{thebibliography}{1}
        \bibitem{any}
        Anon. Whatever. DOI: 10.5678/whatever.2020
        \end{thebibliography}
        """,
    )
    refs = parse_bibitem_block(tex)
    assert refs[0].doi == "10.5678/whatever.2020"


# ---------------------------------------------------------------------------
# Citation-key extraction and bib-file discovery
# ---------------------------------------------------------------------------


def test_extract_cite_keys_handles_natbib_variants(tmp_path):
    tex = _write(
        tmp_path / "paper.tex",
        r"""
        See \cite{smith2024,jones2023} and also \citep{wong2022}.
        Plus \citet{lee2021}, plus a forgotten \nocite{omitted}.
        """,
    )
    keys = extract_cite_keys(tex)
    assert keys == {"smith2024", "jones2023", "wong2022", "lee2021", "omitted"}


def test_extract_cite_keys_drops_star_wildcard(tmp_path):
    tex = _write(tmp_path / "paper.tex", r"\nocite{*}")
    assert extract_cite_keys(tex) == set()


def test_find_bib_references_resolves_neighbouring_files(tmp_path):
    _write(tmp_path / "main.bib", r"@article{a, year={2020}}")
    _write(tmp_path / "extra.bib", r"@article{b, year={2021}}")
    tex = _write(
        tmp_path / "paper.tex",
        r"\bibliography{main, extra}",
    )
    bibs = find_bib_references(tex)
    names = sorted(b.name for b in bibs)
    assert names == ["extra.bib", "main.bib"]


def test_find_bib_references_skips_missing(tmp_path):
    tex = _write(tmp_path / "paper.tex", r"\bibliography{nonexistent}")
    assert find_bib_references(tex) == []


# ---------------------------------------------------------------------------
# Reference dataclass
# ---------------------------------------------------------------------------


def test_reference_normalized_title_strips_latex():
    r = Reference(cite_key="x", title=r"A \textit{lovely} {study} of \emph{widgets}")
    assert r.normalized_title == "a lovely study of widgets"


def test_reference_merge_from_fills_missing_fields():
    base = Reference(cite_key="x", title="T", year="")
    other = Reference(cite_key="x", title="T", year="2020", journal="J")
    base.merge_from(other)
    assert base.year == "2020"
    assert base.journal == "J"


def test_reference_merge_from_prefers_bibtex_over_bibitem():
    bibtex = Reference(
        cite_key="x", title="Authoritative", source_format="bibtex"
    )
    bibitem = Reference(
        cite_key="x", title="Loose paraphrase", source_format="bibitem"
    )
    # When we merge bibtex *from* bibitem, the bibtex value should win on
    # conflict (per merge_from's source_format check).
    bibtex.merge_from(bibitem)
    assert bibtex.title == "Authoritative"

    # In the other direction, bibitem yields to bibtex.
    bibitem.merge_from(bibtex)
    assert bibitem.title == "Authoritative"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_deduplicate_merges_by_cite_key():
    a = Reference(cite_key="smith", title="X", year="2020", journal="J")
    b = Reference(cite_key="smith", title="X", year="2020", doi="10.1/x")
    merged = deduplicate([a, b])
    assert len(merged) == 1
    assert merged[0].journal == "J"
    assert merged[0].doi == "10.1/x"


def test_deduplicate_merges_by_fuzzy_title_and_year():
    a = Reference(
        cite_key="smith2020",
        title="A study of widgets",
        year="2020",
        source_format="bibtex",
    )
    b = Reference(
        cite_key="smith20",  # different key
        title="A study of widgets.",  # near-identical title (trailing dot)
        year="2020",
        source_format="bibitem",
        doi="10.1/x",
    )
    merged = deduplicate([a, b])
    assert len(merged) == 1
    base = merged[0]
    assert base.doi == "10.1/x"
    assert "smith20" in base.alternate_keys or "smith2020" in base.alternate_keys


def test_deduplicate_keeps_distinct_works_separate():
    a = Reference(cite_key="a", title="Widgets and their uses", year="2020")
    b = Reference(cite_key="b", title="Quantum chromodynamics review", year="2020")
    merged = deduplicate([a, b])
    assert len(merged) == 2


def test_deduplicate_does_not_merge_same_title_across_years():
    """A genuine reissue and the original should stay separate — the year
    component of the dedup key keeps them apart."""
    a = Reference(cite_key="a", title="Foundational textbook", year="1995")
    b = Reference(cite_key="b", title="Foundational textbook", year="2010")
    merged = deduplicate([a, b])
    assert len(merged) == 2


# ---------------------------------------------------------------------------
# End-to-end extract_all
# ---------------------------------------------------------------------------


def test_extract_all_finds_bib_and_bibitem_and_stats(tmp_path):
    _write(
        tmp_path / "refs.bib",
        r"""
        @article{smith2024,
            title = {Widgets},
            author = {Smith, A.},
            year = {2024},
            doi = {10.1/w},
        }
        """,
    )
    _write(
        tmp_path / "paper.tex",
        r"""
        \cite{smith2024}
        \bibliography{refs}
        """,
    )
    refs, stats = extract_all(tmp_path)
    assert stats["bibtex_refs_found"] >= 1
    assert stats["with_doi"] >= 1
    assert any(r.cite_key == "smith2024" for r in refs)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
