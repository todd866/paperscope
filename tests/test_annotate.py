"""Unit tests for the annotate submodule (PDF + notes spec -> annotated copy).

Self-contained -- builds a tiny in-memory source PDF, no external corpus needed.

  python tests/test_annotate.py   # standalone, prints PASS/FAIL
  pytest tests/test_annotate.py   # under pytest
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import fitz  # noqa: E402

from paperscope.analysis.annotate import (  # noqa: E402
    build_annotated_pdf, clean, wrap, _HELV,
)


def _make_src(path: Path, pages: list[str]) -> None:
    doc = fitz.open()
    for text in pages:
        pg = doc.new_page(width=612, height=792)
        pg.insert_text((72, 100), text, fontname="helv", fontsize=12)
    doc.save(str(path))
    doc.close()


def _spec() -> dict:
    return {
        "title": "Test annotated copy",
        "subtitle": "unit test",
        "bottom_line": {"label": "Major revision", "text": "A bottom line with an em-dash — and alpha α."},
        "summary": {"title": "In one screen", "sections": [
            {"heading": "Thesis", "color": "teach", "items": ["point one", "point two"]},
            {"heading": "Criticisms", "color": "crit", "items": ["1. first", "2. second"]},
        ]},
        "notes": [
            {"page": 0, "anchor": "alpha keystone", "cat": "DEF",
             "header": "the keystone", "body": "What it is: a test. My read: fine."},
            {"page": 1, "anchor": "river flows", "cat": "CRIT",
             "header": "the river", "body": "A criticism with Greek λ and an arrow →."},
            {"page": 1, "anchor": "this anchor is absent xyz", "cat": "STRENGTH",
             "header": "missing one", "body": "should be reported as a miss."},
        ],
    }


def test_clean_maps_unicode():
    out = clean("alpha α — β ε ∝ ² § Φ →")
    assert "?" not in out, f"clean left non-ASCII: {out!r}"
    assert "alpha" in out and "beta" in out and "Phi" in out


def test_wrap_respects_width():
    lines = wrap("word " * 80, _HELV, 10, 200)
    assert len(lines) > 1
    assert all(_HELV.text_length(ln, 10) <= 201 for ln in lines)


def test_build_and_misses():
    tmp = Path(tempfile.mkdtemp())
    src, out = tmp / "src.pdf", tmp / "out.pdf"
    _make_src(src, ["alpha keystone page zero", "river flows here on page one"])
    res = build_annotated_pdf(src, _spec(), out)
    # 2 front-matter pages + 2 source pages + >=2 interleaved commentary pages
    assert res["pages"] > 4, res
    assert res["n_notes"] == 3
    # exactly one anchor is deliberately absent
    assert len(res["misses"]) == 1, res["misses"]
    assert "absent" in res["misses"][0][1]
    d = fitz.open(str(out))
    full = "\n".join(d[i].get_text() for i in range(d.page_count))
    d.close()
    assert "the keystone" in full and "the river" in full
    assert "In one screen" in full and "Criticisms" in full
    assert "Major revision" in full
    assert "?" not in full   # no clean() garbage in any commentary/front-matter text


def test_bad_category_rejected():
    tmp = Path(tempfile.mkdtemp())
    src = tmp / "s.pdf"
    _make_src(src, ["x"])
    spec = {"notes": [{"page": 0, "anchor": "x", "cat": "NOPE", "header": "h", "body": "b"}]}
    try:
        build_annotated_pdf(src, spec, tmp / "o.pdf")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown category")


def test_missing_fields_rejected():
    tmp = Path(tempfile.mkdtemp())
    src = tmp / "s.pdf"
    _make_src(src, ["x"])
    spec = {"notes": [{"page": 0, "anchor": "x", "cat": "CRIT"}]}  # no header/body
    try:
        build_annotated_pdf(src, spec, tmp / "o.pdf")
    except ValueError:
        return
    raise AssertionError("expected ValueError for missing note fields")


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                fails += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    sys.exit(1 if fails else 0)
