"""Tests for the Anna's Archive DOI-collision guard.

Background: SciDB occasionally maps a DOI to an MD5 whose record is a
*different* paper. Before this guard, `acquire_shadow_pdfs` would download
and silently save that wrong file. The guard checks each candidate MD5's
landing page for the requested DOI and refuses to write a non-matching
file (recording ``doi_mismatch`` instead).

Network is mocked, so these run anywhere.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from paperscope.ingest import shadow_library as sl


# --- doi_core normalisation (pure unit) ---

@pytest.mark.parametrize("raw,expected", [
    ("10.1080/21678421.2023.2285428", "10.1080/21678421.2023.2285428"),
    ("https://doi.org/10.1001/jamanetworkopen.2024.29229",
     "10.1001/jamanetworkopen.2024.29229"),
    ("HTTPS://DX.DOI.ORG/10.1234/ABC.pdf", "10.1234/abc"),
    ("10.1080%2F09537100400004363", "10.1080/09537100400004363"),
    ("", ""),
])
def test_doi_core(raw, expected):
    assert sl.doi_core(raw) == expected


def _page(text: str):
    r = MagicMock()
    r.status_code = 200
    r.text = text
    return r


# --- md5_landing_carries_doi: the collision detector ---

def test_landing_carries_doi_true_when_doi_on_page():
    """A landing page that names the requested DOI passes."""
    doi = "10.1080/09537100400004363"
    sess = MagicMock()
    sess.headers = {"User-Agent": "x"}
    sess.get.return_value = _page(
        f"... stored as 10.1080%2F09537100400004363.pdf ... {doi} ..."
    )
    assert sl.md5_landing_carries_doi("deadbeef" * 4, doi, session=sess) is True


def test_landing_carries_doi_false_on_collision():
    """The real failure: smith's DOI requested, but the page is a *different*
    paper (the 2005 Platelets review) — guard returns False."""
    requested = "10.1080/21678421.2023.2285428"
    sess = MagicMock()
    sess.headers = {"User-Agent": "x"}
    # landing page of the wrong file SciDB actually returns for that DOI
    sess.get.return_value = _page(
        "Tetraspanin-Fc receptor interactions ... "
        "10.1080%2F09537100400004363.pdf ... Platelets 2005"
    )
    assert sl.md5_landing_carries_doi("c0ffee" * 5 + "ab", requested, session=sess) is False


# --- acquire_shadow_pdfs: end-to-end guard behaviour ---

def _records():
    return [{"pmid": "38013452", "doi": "10.1080/21678421.2023.2285428"}]


def test_acquire_records_doi_mismatch_and_writes_nothing(tmp_path):
    """SciDB returns a wrong-file MD5; guard must skip it as doi_mismatch
    and write no PDF."""
    with patch.object(sl, "fetch_via_scihub", return_value=(False, "no scihub")), \
         patch.object(sl, "resolve_doi_to_md5s", return_value=["b" * 32]), \
         patch.object(sl, "md5_landing_carries_doi", return_value=False), \
         patch.object(sl, "fetch_pdf_by_md5") as fetch_md5:
        report = sl.acquire_shadow_pdfs(
            _records(), tmp_path, pace_s=0, verify_doi=True,
        )
    assert report.doi_mismatch == 1
    assert report.fetched == 0
    fetch_md5.assert_not_called()                      # never downloaded
    assert not (tmp_path / "38013452.pdf").exists()    # nothing written
    assert report.attempts[-1].outcome == "doi_mismatch"


def test_acquire_uses_doi_matching_candidate(tmp_path):
    """When a later candidate MD5 matches the DOI, it is the one fetched."""
    def carries(md5, doi, session=None, timeout=30.0):
        return md5 == "good" + "0" * 28

    def fake_fetch(md5, dest, session=None, timeout=60.0):
        dest.write_bytes(b"%PDF-1.4 ok")
        return True, "12B"

    with patch.object(sl, "fetch_via_scihub", return_value=(False, "no scihub")), \
         patch.object(sl, "resolve_doi_to_md5s",
                      return_value=["bad" + "0" * 29, "good" + "0" * 28]), \
         patch.object(sl, "md5_landing_carries_doi", side_effect=carries), \
         patch.object(sl, "fetch_pdf_by_md5", side_effect=fake_fetch) as fetch_md5:
        report = sl.acquire_shadow_pdfs(
            _records(), tmp_path, pace_s=0, verify_doi=True,
        )
    assert report.fetched == 1
    assert report.doi_mismatch == 0
    fetch_md5.assert_called_once()
    assert fetch_md5.call_args[0][0] == "good" + "0" * 28


def test_acquire_verify_doi_off_uses_first(tmp_path):
    """With verify_doi=False the old behaviour holds: first MD5 is used."""
    def fake_fetch(md5, dest, session=None, timeout=60.0):
        dest.write_bytes(b"%PDF-1.4 ok")
        return True, "12B"

    with patch.object(sl, "fetch_via_scihub", return_value=(False, "no scihub")), \
         patch.object(sl, "resolve_doi_to_md5s", return_value=["first" + "0" * 27]), \
         patch.object(sl, "md5_landing_carries_doi") as guard, \
         patch.object(sl, "fetch_pdf_by_md5", side_effect=fake_fetch) as fetch_md5:
        report = sl.acquire_shadow_pdfs(
            _records(), tmp_path, pace_s=0, verify_doi=False,
        )
    assert report.fetched == 1
    guard.assert_not_called()
    assert fetch_md5.call_args[0][0] == "first" + "0" * 27
