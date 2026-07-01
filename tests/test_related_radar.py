"""Regression tests for null-safe OpenAlex field extraction in related_radar.

OpenAlex returns ``primary_location``, its nested ``source``, and an
authorship's ``author`` as ``None`` (not ``{}``) for works with no indexed
venue/author. The previous chained ``.get(..., {})`` raised AttributeError
on those works (crashing the whole ``related`` run). These tests pin the
null-safe behavior.
"""

from paperscope.analysis.related_radar import _format_source, _format_authors


def test_format_source_null_source():
    # primary_location present but source explicitly null -> the original crash
    assert _format_source({"primary_location": {"source": None}}) == ""


def test_format_source_null_primary_location():
    assert _format_source({"primary_location": None}) == ""


def test_format_source_missing_keys():
    assert _format_source({}) == ""


def test_format_source_happy_path():
    work = {"primary_location": {"source": {"display_name": "Nature"}}}
    assert _format_source(work) == "Nature"


def test_format_authors_null_author():
    # an authorship with explicit null author must not crash
    work = {"authorships": [{"author": None}, {"author": {"display_name": "A. Turing"}}]}
    assert _format_authors(work) == "A. Turing"


def test_format_authors_null_authorships():
    assert _format_authors({"authorships": None}) == ""
