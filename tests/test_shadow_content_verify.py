"""Tests for the content-verification + OCR gate in shadow_library.

The DOI-landing guard (test_shadow_doi_guard.py) checks the MD5 *landing page*.
This gate checks the *delivered PDF's own text* against the expected title — the
guard against Sci-Hub (which is unguarded by the landing check) and against a
libgen chain delivering a wrong/corrupt file.

Fixtures are real PDFs built with PyMuPDF, so no network. The OCR tests need
tesseract and are skipped when it is absent.
"""
from __future__ import annotations

import shutil

import fitz  # PyMuPDF
import pytest

from paperscope.ingest import shadow_library as sl

TITLE = "Gold Coast diagnostic criteria increase sensitivity in amyotrophic lateral sclerosis"
OTHER = "Tetraspanin Fc receptor interactions on the surface of activated platelets"

_HAS_TESSERACT = shutil.which("tesseract") is not None


def _text_pdf(text: str) -> bytes:
    """A normal PDF with a real text layer."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text, fontsize=12)
    return doc.tobytes()


def _image_only_pdf(text: str) -> bytes:
    """A scanned-style PDF: the text is rendered to an image, no text layer."""
    src = fitz.open()
    p = src.new_page()
    p.insert_text((72, 100), text, fontsize=22)
    pix = p.get_pixmap(dpi=150)
    out = fitz.open()
    ip = out.new_page(width=pix.width, height=pix.height)
    ip.insert_image(ip.rect, pixmap=pix)
    return out.tobytes()


# --- text-layer behaviour ---

def test_empty_title_passes_without_reading():
    assert sl.pdf_matches_title(b"%PDF-not even valid", "") == (True, 1.0)


def test_matching_text_pdf_passes():
    ok, ratio = sl.pdf_matches_title(_text_pdf(TITLE), TITLE)
    assert ok is True
    assert ratio >= 0.9


def test_unrelated_text_pdf_is_rejected():
    ok, ratio = sl.pdf_matches_title(_text_pdf(OTHER), TITLE)
    assert ok is False
    assert ratio < 0.45


def test_non_pdf_bytes_do_not_match_a_real_title():
    ok, ratio = sl.pdf_matches_title(b"<html>403 Forbidden</html>", TITLE)
    assert ok is False


# --- OCR fallback (scanned PDFs) ---

@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract not installed")
def test_image_only_pdf_matches_via_ocr():
    """A scan with no text layer must still match its title via OCR."""
    ok, ratio = sl.pdf_matches_title(_image_only_pdf(TITLE), TITLE)
    assert ok is True
    assert ratio >= 0.45


@pytest.mark.skipif(not _HAS_TESSERACT, reason="tesseract not installed")
def test_image_only_wrong_paper_still_rejected_after_ocr():
    """OCR must not rescue a genuinely wrong scanned paper."""
    ok, _ = sl.pdf_matches_title(_image_only_pdf(OTHER), TITLE)
    assert ok is False


# --- acquire_shadow_pdfs: end-to-end content-gate behaviour (network mocked) ---

from unittest.mock import patch  # noqa: E402


def _records(title=TITLE):
    rec = {"pmid": "P1", "doi": "10.1/x"}
    if title is not None:
        rec["title"] = title
    return [rec]


def test_scihub_wrong_paper_rejected_by_title_gate(tmp_path):
    """The key gap: Sci-Hub is the unguarded first stage. A wrong paper from
    Sci-Hub must be caught by the content gate and not kept."""
    def fake_scihub(doi, dest, session=None, timeout=60.0):
        dest.write_bytes(_text_pdf(OTHER))
        return True, "wrote wrong paper"

    with patch.object(sl, "fetch_via_scihub", side_effect=fake_scihub), \
         patch.object(sl, "resolve_doi_to_md5s", return_value=[]):
        report = sl.acquire_shadow_pdfs(
            _records(), tmp_path, pace_s=0, verify_title=True,
        )
    assert report.title_mismatch == 1
    assert report.fetched == 0
    assert not (tmp_path / "P1.pdf").exists()
    assert report.attempts[-1].outcome == "title_mismatch"


def test_scihub_correct_paper_is_kept(tmp_path):
    def fake_scihub(doi, dest, session=None, timeout=60.0):
        dest.write_bytes(_text_pdf(TITLE))
        return True, "wrote right paper"

    with patch.object(sl, "fetch_via_scihub", side_effect=fake_scihub):
        report = sl.acquire_shadow_pdfs(
            _records(), tmp_path, pace_s=0, verify_title=True,
        )
    assert report.fetched == 1
    assert (tmp_path / "P1.pdf").exists()


def test_md5_wrong_paper_rejected_by_title_gate(tmp_path):
    """A libgen-delivered file that passes the DOI-landing guard but is still
    the wrong paper must be caught by the content gate."""
    def fake_md5(md5, dest, session=None, timeout=60.0):
        dest.write_bytes(_text_pdf(OTHER))
        return True, "wrote wrong paper"

    with patch.object(sl, "fetch_via_scihub", return_value=(False, "no scihub")), \
         patch.object(sl, "resolve_doi_to_md5s", return_value=["a" * 32]), \
         patch.object(sl, "md5_landing_carries_doi", return_value=True), \
         patch.object(sl, "fetch_pdf_by_md5", side_effect=fake_md5):
        report = sl.acquire_shadow_pdfs(
            _records(), tmp_path, pace_s=0, verify_title=True, verify_doi=True,
        )
    assert report.title_mismatch == 1
    assert report.fetched == 0
    assert not (tmp_path / "P1.pdf").exists()


def test_verify_title_off_keeps_unverified_file(tmp_path):
    """Back-compat: with verify_title=False the content gate is not applied."""
    def fake_scihub(doi, dest, session=None, timeout=60.0):
        dest.write_bytes(_text_pdf(OTHER))
        return True, "wrote"

    with patch.object(sl, "fetch_via_scihub", side_effect=fake_scihub):
        report = sl.acquire_shadow_pdfs(
            _records(), tmp_path, pace_s=0, verify_title=False,
        )
    assert report.fetched == 1
    assert (tmp_path / "P1.pdf").exists()


def test_no_title_in_record_is_noop_even_when_verifying(tmp_path):
    """A record without a title can't be content-checked; it must still be kept
    (the gate is opt-in per record)."""
    def fake_scihub(doi, dest, session=None, timeout=60.0):
        dest.write_bytes(_text_pdf(OTHER))
        return True, "wrote"

    with patch.object(sl, "fetch_via_scihub", side_effect=fake_scihub):
        report = sl.acquire_shadow_pdfs(
            _records(title=None), tmp_path, pace_s=0, verify_title=True,
        )
    assert report.fetched == 1
    assert (tmp_path / "P1.pdf").exists()


def test_scihub_wrong_then_libgen_right_is_fetched(tmp_path):
    """Recall guard: a Sci-Hub title mismatch must fall through to the libgen
    route, not abandon the record. Wrong Sci-Hub PDF + correct libgen PDF ->
    fetched (not title_mismatch)."""
    def fake_scihub(doi, dest, session=None, timeout=60.0):
        dest.write_bytes(_text_pdf(OTHER))     # wrong paper from Sci-Hub
        return True, "wrong scihub"

    def fake_md5(md5, dest, session=None, timeout=60.0):
        dest.write_bytes(_text_pdf(TITLE))     # right paper from libgen
        return True, "right libgen"

    with patch.object(sl, "fetch_via_scihub", side_effect=fake_scihub), \
         patch.object(sl, "resolve_doi_to_md5s", return_value=["a" * 32]), \
         patch.object(sl, "md5_landing_carries_doi", return_value=True), \
         patch.object(sl, "fetch_pdf_by_md5", side_effect=fake_md5):
        report = sl.acquire_shadow_pdfs(
            _records(), tmp_path, pace_s=0, verify_title=True, verify_doi=True,
        )
    assert report.fetched == 1
    assert report.title_mismatch == 0
    assert (tmp_path / "P1.pdf").exists()
    assert sl.pdf_matches_title((tmp_path / "P1.pdf").read_bytes(), TITLE)[0]


def test_short_acronym_title_discriminates():
    """Short biomedical titles are mostly acronyms/genes/numbers. The tokenizer
    must keep them (ALS, SOD1, C9orf72) or it can't tell right from wrong."""
    title = "SOD1 and C9orf72 in ALS"
    right = sl.pdf_matches_title(_text_pdf("SOD1 C9orf72 ALS familial cohort"), title)
    wrong = sl.pdf_matches_title(_text_pdf("Tetraspanin platelet receptor study"), title)
    assert right[0] is True
    assert wrong[0] is False


def test_tokenizer_keeps_acronyms_and_numbers_drops_stopwords():
    toks = sl._content_tokens("SOD1 and C9orf72 in ALS TDP-43")
    assert {"sod1", "c9orf72", "als", "tdp", "43"} <= toks
    assert "and" not in toks and "in" not in toks
