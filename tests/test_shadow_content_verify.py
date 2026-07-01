"""Tests for the content-verification + OCR gate in shadow_library.

This gate checks a delivered PDF's own text against the expected title, so a
wrong or corrupt file is rejected rather than kept.

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


# --- tokenizer behaviour ---

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
