"""PDF content verification, plus a stub for last-resort ("shadow") acquisition.

The public build ships the generic content-verification helpers — matching a
downloaded PDF's own text against the expected title — but NOT any last-resort
acquisition provider. `acquire_shadow_pdfs` is a stub that raises; bring your own
provider. See docs/ACQUISITION.md.

Open-access acquisition (Unpaywall, publisher OA, EZProxy) is unaffected: it lives
in `paperscope.ingest.open_access` and uses `pdf_matches_title` below to verify
what it downloaded.
"""

from __future__ import annotations

import re
from pathlib import Path


_TITLE_STOPWORDS = frozenset({
    "a", "an", "as", "at", "be", "by", "in", "is", "of", "on", "or", "to",
    "we", "the", "and", "for", "with", "from", "this", "that", "into", "than",
    "then", "are", "was", "were", "has", "have", "had", "not", "but", "its",
    "via", "per", "using", "based", "study", "studies", "among", "between",
    "versus", "vs",
})


def _content_tokens(s: str) -> set[str]:
    """Alphanumeric tokens for title/content overlap scoring.

    Keeps tokens of length >= 2 (so acronyms, gene/protein symbols, and numbers
    survive) and drops a small stopword set. A 4+-letters-only rule discarded
    exactly the tokens that carry a short biomedical title's identity.
    """
    toks = re.findall(r"[a-z0-9]{2,}", (s or "").lower())
    return {t for t in toks if t not in _TITLE_STOPWORDS}


def _ocr_pdf_text(pdf_bytes: bytes, max_pages: int = 2, dpi: int = 200) -> str:
    """OCR the first pages of a (likely scanned) PDF; "" on any failure.

    Pre-~2000 papers are frequently image-only scans with no text layer. OCR
    recovers the real text. Requires `tesseract` on PATH and PyMuPDF; degrades to
    "" when unavailable.
    """
    import subprocess
    import tempfile
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return ""
    out: list[str] = []
    for i in range(min(max_pages, len(doc))):
        try:
            pix = doc[i].get_pixmap(dpi=dpi)
            with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as tf:
                pix.save(tf.name)
                r = subprocess.run(
                    ["tesseract", tf.name, "-", "--psm", "6"],
                    capture_output=True, text=True, timeout=120,
                )
                out.append(r.stdout)
        except Exception:
            break
    return "\n".join(out)


def pdf_matches_title(
    pdf_bytes: bytes,
    title: str,
    min_ratio: float = 0.45,
) -> tuple[bool, float]:
    """Does the PDF's own text contain enough of `title`? Returns (ok, ratio).

    The content guard: an acquisition source can occasionally deliver an unrelated
    paper (or an HTML error page). Checking the delivered bytes' text against the
    expected title catches this where a DOI-landing check cannot. No title to
    check against -> (True, 1.0) (the check is opt-in per record).

    Scanned PDFs have no usable text layer, so a low text-layer score is re-judged
    on OCR before rejecting; the higher of the two ratios wins.
    """
    if not title:
        return True, 1.0
    tt = _content_tokens(title)
    if not tt:
        return True, 1.0
    head = ""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        head = "".join(doc[i].get_text() for i in range(min(2, len(doc))))
    except Exception:
        head = ""

    def ratio_of(text: str) -> float:
        return len(tt & _content_tokens(text)) / len(tt)

    ratio = ratio_of(head)
    if ratio < min_ratio:  # sparse/scanned/watermark text layer -> OCR and re-judge
        ratio = max(ratio, ratio_of(_ocr_pdf_text(pdf_bytes)))
    return ratio >= min_ratio, ratio


def _title_gate_failed(dest: Path, title: str, verify_title: bool) -> tuple[bool, float]:
    """Has the just-downloaded `dest` failed the content gate? Deletes it if so.

    Returns (failed, ratio). A no-op (never fails) when verification is off, no
    title is available, or the file can't be read.
    """
    if not (verify_title and title):
        return False, 1.0
    try:
        ok, ratio = pdf_matches_title(dest.read_bytes(), title)
    except OSError:
        return False, 1.0
    if not ok:
        try:
            dest.unlink()
        except OSError:
            pass
        return True, ratio
    return False, ratio


def acquire_shadow_pdfs(*args, **kwargs):
    """Not included in the public build.

    Last-resort ("shadow") acquisition is intentionally omitted from the public
    paperscope. Open-access acquisition (`paperscope.ingest.open_access`) is
    unaffected. Bring your own provider — see docs/ACQUISITION.md.
    """
    raise NotImplementedError(
        "Shadow acquisition is not part of the public paperscope build. "
        "Bring your own provider; see docs/ACQUISITION.md."
    )
