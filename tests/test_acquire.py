"""Tests for OA acquisition + EZProxy queue.

These mock the network layer, so they run anywhere — no MND corpus needed.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from paperscope.ingest.open_access import _BROWSER_UA, acquire_oa_pdfs
from paperscope.systematic_review.acquire.ezproxy import write_ezproxy_queue
from paperscope.systematic_review.acquire.pipeline import AcquireResult


# Minimal valid PDF: magic-byte check looks at the first 5 bytes only.
_VALID_PDF = b"%PDF-1.4\n%minimal\n1 0 obj <</Type/Catalog>> endobj\n%%EOF\n"
_NOT_A_PDF = b"<html><body>Access denied</body></html>"


def _make_response(
    *,
    status: int,
    body: bytes,
    content_type: str = "application/pdf",
    final_url: str = "https://example.com/paper.pdf",
):
    """Stand-in for a `requests.Response` with stream=True semantics."""
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {"content-type": content_type}
    resp.url = final_url
    resp.iter_content = lambda chunk_size=8192: [body]
    return resp


# ---------------------------------------------------------------------------
# Browser User-Agent
# ---------------------------------------------------------------------------


def test_browser_ua_actually_replaces_default(tmp_path):
    """`requests.Session()` ships with `python-requests/X.Y` pre-populated, so
    `setdefault` would silently leave it in place — defeating the bot-block
    bypass. The session UA must be assigned outright.
    """
    s = requests.Session()
    assert s.headers.get("User-Agent", "").startswith("python-requests")  # baseline

    with patch(
        "paperscope.ingest.open_access._get_oa_pdf_urls", return_value=[]
    ):
        acquire_oa_pdfs([], tmp_path, session=s, verbose=False)

    assert s.headers["User-Agent"] == _BROWSER_UA
    assert s.headers["Accept"].startswith("application/pdf")
    assert "en" in s.headers["Accept-Language"].lower()


# ---------------------------------------------------------------------------
# Partial-write protection
# ---------------------------------------------------------------------------


def test_partial_write_does_not_create_phantom_cache(tmp_path):
    """A 200 OK that returns HTML (not a real PDF) used to land at the
    canonical .pdf path; a re-run would then treat it as a cache hit and skip
    the URL forever. The fix streams to .part and only renames on a verified
    PDF — so neither the .pdf nor a stray .part should remain.
    """
    refs = [{"cite_key": "papr", "doi": "10.1/x"}]

    def fake_get(self, url, **kwargs):
        return _make_response(status=200, body=_NOT_A_PDF)

    with patch(
        "paperscope.ingest.open_access._get_oa_pdf_urls",
        return_value=["https://example.com/paper.pdf"],
    ), patch.object(requests.Session, "get", fake_get):
        acquired = acquire_oa_pdfs(refs, tmp_path, verbose=False)

    assert acquired == {}
    assert not (tmp_path / "papr.pdf").exists()
    assert not (tmp_path / "papr.pdf.part").exists()


def test_successful_download_atomically_lands_pdf(tmp_path):
    refs = [{"cite_key": "papr", "doi": "10.1/x"}]

    def fake_get(self, url, **kwargs):
        return _make_response(status=200, body=_VALID_PDF)

    with patch(
        "paperscope.ingest.open_access._get_oa_pdf_urls",
        return_value=["https://example.com/paper.pdf"],
    ), patch.object(requests.Session, "get", fake_get):
        acquired = acquire_oa_pdfs(refs, tmp_path, verbose=False)

    assert acquired == {"papr": str(tmp_path / "papr.pdf")}
    assert (tmp_path / "papr.pdf").exists()
    assert (tmp_path / "papr.pdf").read_bytes().startswith(b"%PDF-")
    assert not (tmp_path / "papr.pdf.part").exists()


def test_existing_pdf_is_reused_without_redownload(tmp_path):
    """If the final .pdf is already on disk, don't hit the network — the
    cache-hit path also skips magic-byte verification, so an existing file is
    trusted as-is.
    """
    refs = [{"cite_key": "papr", "doi": "10.1/x"}]
    (tmp_path / "papr.pdf").write_bytes(_VALID_PDF)

    fake_get = MagicMock(side_effect=AssertionError("network must not be hit"))

    with patch(
        "paperscope.ingest.open_access._get_oa_pdf_urls",
        return_value=["https://example.com/paper.pdf"],
    ), patch.object(requests.Session, "get", fake_get):
        acquired = acquire_oa_pdfs(refs, tmp_path, verbose=False)

    assert "papr" in acquired


# ---------------------------------------------------------------------------
# Stats out-param
# ---------------------------------------------------------------------------


def test_oa_found_counts_unpaywall_hits_not_downloads(tmp_path):
    """The pipeline.py report needs oa_found ≠ oa_downloaded for honest
    coverage stats — Unpaywall regularly lists OA URLs that the publisher
    then bot-blocks at the actual PDF endpoint. The function exposes this via
    the `stats` out-param.
    """
    refs = [{"cite_key": f"p{i}", "doi": f"10.1/x{i}"} for i in range(3)]

    # Each ref has one Unpaywall candidate; only the first download succeeds.
    n = {"calls": 0}

    def fake_get(self, url, **kwargs):
        n["calls"] += 1
        if n["calls"] == 1:
            return _make_response(status=200, body=_VALID_PDF)
        return _make_response(
            status=403, body=b"forbidden", content_type="text/html"
        )

    stats: dict = {}
    with patch(
        "paperscope.ingest.open_access._get_oa_pdf_urls",
        return_value=["https://example.com/paper.pdf"],
    ), patch.object(requests.Session, "get", fake_get):
        acquired = acquire_oa_pdfs(refs, tmp_path, verbose=False, stats=stats)

    assert stats["checked"] == 3
    assert stats["oa_found"] == 3
    assert stats["oa_downloaded"] == 1
    assert len(acquired) == 1


# ---------------------------------------------------------------------------
# EZProxy queue
# ---------------------------------------------------------------------------


def test_ezproxy_queue_writes_expected_entries(tmp_path):
    paywalled = [
        {"pmid": "12345", "doi": "10.1/abc", "title": "Paper A"},
        {"pmid": "67890", "doi": "10.1/def", "title": "Paper B"},
        {"pmid": "11111", "doi": "", "title": "No DOI — should be dropped"},
    ]
    out = tmp_path / "ezproxy-queue.json"

    n = write_ezproxy_queue(paywalled, out, ezproxy_host="ezproxy.example.edu")

    assert n == 2  # DOI-less record dropped
    queue = json.loads(out.read_text())
    assert {q["cite_key"] for q in queue} == {"12345", "67890"}
    for entry in queue:
        assert entry["ezproxy_url"].startswith("https://doi-org.ezproxy.example.edu/")
        assert entry["title"]


# ---------------------------------------------------------------------------
# AcquireResult coverage maths
# ---------------------------------------------------------------------------


def test_acquire_result_coverage_pct():
    r = AcquireResult(
        review_name="t",
        corpus_dir="/x",
        with_doi=100,
        oa_downloaded=30,
        already_cached=20,
    )
    assert r.coverage_pct == 50.0


def test_acquire_result_coverage_pct_zero_doi_no_div_error():
    r = AcquireResult(review_name="t", corpus_dir="/x", with_doi=0)
    assert r.coverage_pct == 0.0


def test_acquire_result_to_dict_includes_coverage():
    r = AcquireResult(
        review_name="t",
        corpus_dir="/x",
        with_doi=50,
        oa_downloaded=10,
        already_cached=5,
    )
    d = r.to_dict()
    assert d["coverage_pct"] == 30.0
    assert d["with_doi"] == 50


def test_pretty_surfaces_shadow_guard_counters():
    """The DOI/title collision guards exist to expose wrong-paper failures —
    they must show up in the human-readable report, not be silently dropped."""
    r = AcquireResult(
        review_name="t",
        corpus_dir="/x",
        with_doi=10,
        shadow_fetched=3,
        shadow_doi_mismatch=2,
        shadow_title_mismatch=4,
    )
    out = r.pretty()
    assert "doi_mismatch=2" in out
    assert "title_mismatch=4" in out


if __name__ == "__main__":
    # Allow running as a plain script.
    raise SystemExit(pytest.main([__file__, "-v"]))
