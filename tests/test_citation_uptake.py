"""Tests for paperscope/analysis/citation_uptake.py.

The one HTTP chokepoint is ``author_profile._oa_get`` (citation_uptake reuses
it). We patch that single helper with a side_effect that routes by endpoint —
a work lookup vs the citing-works page — so every test runs offline.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from paperscope.analysis import author_profile, citation_uptake
from paperscope.analysis.citation_uptake import check_uptake, _normalize_doi


# --- fixtures: fake OpenAlex payloads ---

ORIG_A = "https://openalex.org/A111"
ORIG_B = "https://openalex.org/A222"
OUTSIDER = "https://openalex.org/A999"


def _work(authors, **over):
    base = {
        "id": "https://openalex.org/W1",
        "title": "Keystone result",
        "publication_year": 2022,
        "cited_by_count": 0,
        "authorships": [{"author": {"id": a}} for a in authors],
    }
    base.update(over)
    return base


def _citing(wid, authors, title, year=2024):
    return {
        "id": wid,
        "title": title,
        "publication_year": year,
        "authorships": [{"author": {"id": a}} for a in authors],
    }


def _router(work, citing_results):
    """Return a side_effect for _oa_get: route by endpoint string."""
    def side_effect(endpoint, params=None):
        if endpoint.startswith("works/doi:"):
            return work if work is not None else {}
        if endpoint == "works":
            return {"results": citing_results}
        raise AssertionError(f"unexpected endpoint {endpoint!r}")
    return side_effect


# --- _normalize_doi (pure unit) ---

@pytest.mark.parametrize("raw,expected", [
    ("10.1109/NAP62956.2024.10739752", "10.1109/nap62956.2024.10739752"),
    ("https://doi.org/10.1/AbC", "10.1/abc"),
    ("doi:10.5/XyZ", "10.5/xyz"),
    ("  10.7/W  ", "10.7/w"),
])
def test_normalize_doi(raw, expected):
    assert _normalize_doi(raw) == expected


# --- classification: one self, one independent ---

def test_classifies_self_and_independent():
    work = _work([ORIG_A, ORIG_B], cited_by_count=2)
    citing = [
        _citing("https://openalex.org/W_self", [ORIG_A, OUTSIDER], "We follow up our own work"),
        _citing("https://openalex.org/W_indep", [OUTSIDER], "An outsider replicates it"),
    ]
    with patch.object(author_profile, "_oa_get", side_effect=_router(work, citing)):
        report = check_uptake("10.1/keystone")

    assert report["work_id"] == "https://openalex.org/W1"
    assert report["title"] == "Keystone result"
    assert report["year"] == 2022
    assert report["cited_by_count"] == 2
    assert report["independent_cited_by_count"] == 1
    assert report["self_cited_by_count"] == 1
    # one independent, below LOW_UPTAKE_THRESHOLD -> low_uptake, not zero
    assert "low_uptake" in report["flags"]
    assert "zero_independent_uptake" not in report["flags"]
    # sample carries the independence label
    by_id = {c["id"]: c for c in report["sample_citing"]}
    assert by_id["https://openalex.org/W_indep"]["independent"] is True
    assert by_id["https://openalex.org/W_self"]["independent"] is False


def test_zero_cited_by_flags_zero_independent_uptake():
    """The review-#15 case: cited_by_count 0 -> zero_independent_uptake,
    and no citing-works page is fetched."""
    work = _work([ORIG_A], cited_by_count=0)
    side = _router(work, [])
    with patch.object(author_profile, "_oa_get", side_effect=side) as oa:
        report = check_uptake("10.1109/NAP62956.2024.10739752")

    assert report["cited_by_count"] == 0
    assert report["independent_cited_by_count"] == 0
    assert "zero_independent_uptake" in report["flags"]
    # only the work lookup happened; the citing page was skipped
    assert oa.call_count == 1
    assert oa.call_args_list[0].args[0].startswith("works/doi:")


def test_all_self_citations_flags_zero_independent_uptake():
    work = _work([ORIG_A, ORIG_B], cited_by_count=2)
    citing = [
        _citing("https://openalex.org/W_s1", [ORIG_A], "Self cite one"),
        _citing("https://openalex.org/W_s2", [ORIG_B, OUTSIDER], "Self cite two"),
    ]
    with patch.object(author_profile, "_oa_get", side_effect=_router(work, citing)):
        report = check_uptake("10.1/keystone")

    assert report["self_cited_by_count"] == 2
    assert report["independent_cited_by_count"] == 0
    assert "zero_independent_uptake" in report["flags"]


def test_explicit_author_ids_override_derivation():
    """Caller-supplied author ids are used instead of the work's authorships."""
    # Work's own authorship is OUTSIDER, but caller declares ORIG_A as the
    # original author -> a citing work by ORIG_A must count as self.
    work = _work([OUTSIDER], cited_by_count=1)
    citing = [_citing("https://openalex.org/Wc", [ORIG_A], "By the supplied original author")]
    with patch.object(author_profile, "_oa_get", side_effect=_router(work, citing)):
        report = check_uptake("10.1/keystone", original_author_ids=[ORIG_A])

    assert report["self_cited_by_count"] == 1
    assert report["independent_cited_by_count"] == 0


def test_healthy_independent_uptake_has_no_uptake_flags():
    work = _work([ORIG_A], cited_by_count=4)
    citing = [
        _citing(f"https://openalex.org/Wi{i}", [f"https://openalex.org/A{i+1000}"], f"Cite {i}")
        for i in range(4)
    ]
    with patch.object(author_profile, "_oa_get", side_effect=_router(work, citing)):
        report = check_uptake("10.1/keystone")

    assert report["independent_cited_by_count"] == 4
    assert "zero_independent_uptake" not in report["flags"]
    assert "low_uptake" not in report["flags"]


def test_work_not_found_flags_and_short_circuits():
    side = _router(None, [])
    with patch.object(author_profile, "_oa_get", side_effect=side) as oa:
        report = check_uptake("10.1/missing")

    assert report["work_id"] is None
    assert "work_not_found" in report["flags"]
    assert oa.call_count == 1  # no citing-works page fetched


def test_no_author_set_unable_to_classify():
    """Work resolves with citations but no usable author ids -> we say we
    cannot classify rather than imply independence."""
    work = _work([], cited_by_count=1)  # no authorships
    citing = [_citing("https://openalex.org/Wc", [OUTSIDER], "Some cite")]
    with patch.object(author_profile, "_oa_get", side_effect=_router(work, citing)):
        report = check_uptake("10.1/noauthors")

    assert "no_author_set_unable_to_classify" in report["flags"]
    assert "zero_independent_uptake" not in report["flags"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
