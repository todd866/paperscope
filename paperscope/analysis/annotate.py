"""Build an annotated reading copy of a PDF from a notes spec.

Generalised from a one-off peer-review script. Given a source PDF and a list of
notes -- each pinning a short ``anchor`` phrase on a page to a colour-coded
``header`` + ``body`` -- produce a new PDF with the original pages highlighted
and numbered, interleaved with "annotator's notes" commentary pages, plus an
optional how-to/colour-key front matter, a one-screen summary page, and a
figure appendix.

It is deliberately substrate-free: the engine knows nothing about any
particular manuscript. All paper-specific content lives in the spec, so the
same tool builds a teaching copy, a referee's annotated copy, or a markup for a
collaborator.

Spec (JSON or YAML)::

    {
      "title":    "Annotated reading copy",            # optional front-matter title
      "subtitle": "MS-12345 - Some Paper (Author)",    # optional
      "intro":    "...",                                # optional; overrides the default how-to
      "bottom_line": {"label": "Major revision",        # optional summary box on the front page
                      "text": "..."},
      "summary": {                                      # optional "in one screen" page
        "title": "The paper in one screen",
        "sections": [
          {"heading": "The thesis",     "color": "teach", "items": ["..."]},
          {"heading": "My criticisms",  "color": "crit",  "items": ["1. ...", "2. ..."]}
        ]
      },
      "notes": [
        {"page": 7, "anchor": "functional closure", "cat": "CRIT",
         "header": "one-line header", "body": "What it is: ...  My read: ..."}
      ],
      "appendix": {                                     # optional
        "title": "Appendix", "intro": "...",
        "figures_dir": "figs",                          # relative to the spec file
        "figures": [{"file": "a.png", "title": "...", "caption": "..."}]
      }
    }

``cat`` is one of TEACH / DEF / STRENGTH / CRIT (case-insensitive; a ``cat`` may
combine e.g. ``"STRENGTH+CRIT"`` and the first token sets the colour).

Programmatic use::

    from paperscope.analysis.annotate import build_annotated_pdf, load_spec
    result = build_annotated_pdf("paper.pdf", load_spec("notes.json"), "annotated.pdf")
    print(result["pages"], result["misses"])

CLI::

    paperscope annotate paper.pdf notes.json -o annotated.pdf
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz

# ---- palette: (badge fill, highlight tint) ----
CATEGORIES: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "TEACH":    ((0.13, 0.40, 0.75), (0.74, 0.84, 0.98)),  # blue  - what it's doing / how to read
    "DEF":      ((0.78, 0.52, 0.04), (0.99, 0.90, 0.62)),  # amber - key definition / new object
    "CRIT":     ((0.78, 0.13, 0.13), (0.99, 0.77, 0.77)),  # red   - criticism + why
    "STRENGTH": ((0.11, 0.55, 0.27), (0.78, 0.93, 0.80)),  # green - genuine merit
}
_LEGEND = [
    ("TEACH", "what the passage is doing / how to read it"),
    ("DEF", "a key definition or new object to learn"),
    ("STRENGTH", "a genuine merit"),
    ("CRIT", "a criticism - with the reasoning for it"),
]
_DARK = (0.12, 0.16, 0.22)
_INK = (0.12, 0.12, 0.12)
PW, PH = 612, 792           # US Letter, points
M = 54                       # margin
CW = PW - 2 * M              # content width

_DEFAULT_INTRO = (
    "This is the original document with notations layered on top. Coloured highlights mark "
    "passages on the original pages; each carries a numbered badge. After every annotated page "
    "you will find a 'notes' page expanding those numbers -- first what the passage is doing in "
    "plain English, then the read or critique and why. Read a page, flip to its notes, continue."
)

# base-14 Helvetica only renders Latin-1; map the unicode we use to ASCII
_MAP = {
    "—": " - ", "–": "-", "’": "'", "‘": "'", "“": '"',
    "”": '"', "…": "...", "−": "-", "·": "*",
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta",
    "ε": "epsilon", "η": "eta", "θ": "theta", "κ": "kappa",
    "λ": "lambda", "μ": "mu", "ρ": "rho", "σ": "sigma",
    "τ": "tau", "χ": "chi", "ω": "omega",
    "Γ": "Gamma", "Δ": "Delta", "Λ": "Lambda", "Ξ": "Xi",
    "Σ": "Sigma", "Φ": "Phi", "Ψ": "Psi", "Ω": "Omega",
    "∈": " in ", "→": "->", "≤": "<=", "≥": ">=",
    "≠": "!=", "×": "x", "≈": "~=", "√": "sqrt",
    "²": "^2", "³": "^3", "⁺": "+", "₂": "2", "₀": "0",
    "≡": "=", "∇": "grad", "§": "Sec.", "≪": "<<", "≫": ">>",
    "∝": "~", "°": "deg",
}


def clean(s: str) -> str:
    """Map the unicode we use to ASCII so base-14 Helvetica renders it."""
    for k, v in _MAP.items():
        s = s.replace(k, v)
    return "".join(c if ord(c) < 128 else "?" for c in s)


def _primary(cat: str) -> str:
    key = cat.split("+")[0].split("/")[0].strip().upper()
    if key not in CATEGORIES:
        raise ValueError(f"unknown note category {cat!r}; expected one of {sorted(CATEGORIES)}")
    return key


_HELV = fitz.Font("helv")
_HEBO = fitz.Font("hebo")


def wrap(text: str, font: fitz.Font, size: float, maxw: float) -> list[str]:
    """Greedy word-wrap ``text`` (ASCII-cleaned) to ``maxw`` points."""
    out: list[str] = []
    for para in clean(text).split("\n"):
        words = para.split(" ")
        line = ""
        for w in words:
            trial = (line + " " + w).strip()
            if font.text_length(trial, size) <= maxw:
                line = trial
            else:
                if line:
                    out.append(line)
                line = w
        out.append(line)
    return out


def draw_lines(page, x, y, lines, bold, size, color, leading):
    fn = "hebo" if bold else "helv"
    for ln in lines:
        page.insert_text((x, y), ln, fontname=fn, fontsize=size, color=color)
        y += leading
    return y


def _resolve_rect(doc, hint: int, anchor: str):
    """Find the first rect for ``anchor``: hint page, then forward, then wrap-around."""
    n = doc.page_count
    rects = doc[hint].search_for(anchor) if 0 <= hint < n else []
    page_idx = hint if 0 <= hint < n else 0
    if not rects:
        for j in list(range(max(hint, 0), n)) + list(range(0, max(hint, 0))):
            r = doc[j].search_for(anchor)
            if r:
                return r, j
        return [], page_idx
    return rects, page_idx


def _place_notes(doc, notes: list[dict]) -> tuple[dict[int, list], list[tuple[int, str]]]:
    """Highlight each note's anchor, draw its numbered badge, group by resolved page."""
    misses: list[tuple[int, str]] = []
    by_page: dict[int, list] = {}
    for n_idx, note in enumerate(notes, start=1):
        cat = note["cat"]
        badge_rgb, hl_rgb = CATEGORIES[_primary(cat)]
        rects, page_idx = _resolve_rect(doc, int(note["page"]), note["anchor"])
        pg = doc[page_idx]   # hold a live reference so annots stay bound to the page
        if not rects:
            misses.append((n_idx, note["anchor"]))
            rect = fitz.Rect(560, 36, 590, 50)   # default top-right marker
        else:
            rect = rects[0]
            try:
                hl = pg.add_highlight_annot(rect)
                hl.set_colors(stroke=hl_rgb)
                hl.set_opacity(0.45)
                hl.update()
            except Exception as e:   # pragma: no cover - defensive
                misses.append((n_idx, f"{note['anchor']} [highlight fail: {e}]"))
        bx = max(8.0, rect.x0 - 13.0)
        by = rect.y0 + (rect.height / 2 if rect.height else 5) + 1.0
        sh = pg.new_shape()
        sh.draw_circle((bx, by), 6.6)
        sh.finish(fill=badge_rgb, color=badge_rgb)
        sh.commit()
        num = str(n_idx)
        tw = _HEBO.text_length(num, 7.5)
        pg.insert_text((bx - tw / 2, by + 2.7), num, fontname="hebo", fontsize=7.5, color=(1, 1, 1))
        by_page.setdefault(page_idx, []).append((n_idx, cat, note["header"], note["body"]))
    return by_page, misses


def _build_commentary(i: int, notes: list, page_count: int) -> fitz.Document:
    cdoc = fitz.open()
    pg = cdoc.new_page(width=PW, height=PH)
    sh = pg.new_shape(); sh.draw_rect(fitz.Rect(0, 0, PW, 40)); sh.finish(fill=_DARK, color=_DARK); sh.commit()
    pg.insert_text((M, 26), clean(f"Annotator's notes  -  source p.{i + 1}"),
                   fontname="hebo", fontsize=13, color=(1, 1, 1))
    y = 64
    for (n, cat, header, body) in notes:
        badge_rgb, _ = CATEGORIES[_primary(cat)]
        if y > PH - 120:
            pg = cdoc.new_page(width=PW, height=PH); y = 64
        sh = pg.new_shape(); sh.draw_circle((M + 8, y - 3), 8.2); sh.finish(fill=badge_rgb, color=badge_rgb); sh.commit()
        nt = _HEBO.text_length(str(n), 9)
        pg.insert_text((M + 8 - nt / 2, y - 0.2), str(n), fontname="hebo", fontsize=9, color=(1, 1, 1))
        y = draw_lines(pg, M + 24, y, wrap(f"[{cat}]  {header}", _HEBO, 10.5, CW - 26), True, 10.5, badge_rgb, 14)
        y += 2
        for ln in wrap(body, _HELV, 9.5, CW - 6):
            if y > PH - 40:
                pg = cdoc.new_page(width=PW, height=PH); y = 56
            pg.insert_text((M + 6, y), ln, fontname="helv", fontsize=9.5, color=_INK)
            y += 13.0
        y += 12
        sh = pg.new_shape(); sh.draw_line((M, y - 6), (PW - M, y - 6)); sh.finish(color=(0.8, 0.8, 0.8), width=0.5); sh.commit()
        y += 6
    return cdoc


def _front_matter(spec: dict) -> fitz.Document:
    fdoc = fitz.open()
    pa = fdoc.new_page(width=PW, height=PH)
    sh = pa.new_shape(); sh.draw_rect(fitz.Rect(0, 0, PW, 70)); sh.finish(fill=_DARK, color=_DARK); sh.commit()
    pa.insert_text((M, 34), clean(spec.get("title", "Annotated reading copy")), fontname="hebo", fontsize=20, color=(1, 1, 1))
    if spec.get("subtitle"):
        pa.insert_text((M, 56), clean(spec["subtitle"]), fontname="helv", fontsize=11, color=(0.85, 0.88, 0.93))
    y = 96
    y = draw_lines(pa, M, y, wrap(spec.get("intro", _DEFAULT_INTRO), _HELV, 11, CW), False, 11, _INK, 16)
    y += 14
    pa.insert_text((M, y), "The colour key", fontname="hebo", fontsize=13, color=_DARK); y += 22
    for cat, desc in _LEGEND:
        rgb, _ = CATEGORIES[cat]
        sh = pa.new_shape(); sh.draw_circle((M + 8, y - 3), 8); sh.finish(fill=rgb, color=rgb); sh.commit()
        pa.insert_text((M + 24, y), cat, fontname="hebo", fontsize=10.5, color=rgb)
        pa.insert_text((M + 110, y), clean(desc), fontname="helv", fontsize=10.5, color=_INK)
        y += 22
    bl = spec.get("bottom_line")
    if bl:
        y += 12
        sh = pa.new_shape(); sh.draw_rect(fitz.Rect(M, y, PW - M, y + 152)); sh.finish(fill=(0.96, 0.97, 0.99), color=(0.7, 0.75, 0.82), width=1); sh.commit()
        pa.insert_text((M + 12, y + 22), clean(f"Bottom line: {bl.get('label', '')}"), fontname="hebo", fontsize=13, color=(0.78, 0.13, 0.13))
        draw_lines(pa, M + 12, y + 42, wrap(bl.get("text", ""), _HELV, 9.7, CW - 24), False, 9.7, _INK, 13)

    summary = spec.get("summary")
    if summary:
        pb = fdoc.new_page(width=PW, height=PH)
        sh = pb.new_shape(); sh.draw_rect(fitz.Rect(0, 0, PW, 40)); sh.finish(fill=_DARK, color=_DARK); sh.commit()
        pb.insert_text((M, 26), clean(summary.get("title", "In one screen")), fontname="hebo", fontsize=14, color=(1, 1, 1))
        y = 64
        for sec in summary.get("sections", []):
            rgb, _ = CATEGORIES[_primary(sec.get("color", "TEACH"))]
            if y > PH - 80:
                pb = fdoc.new_page(width=PW, height=PH); y = 64
            pb.insert_text((M, y), clean(sec.get("heading", "")), fontname="hebo", fontsize=12, color=rgb); y += 18
            for item in sec.get("items", []):
                if y > PH - 60:
                    pb = fdoc.new_page(width=PW, height=PH); y = 64
                y = draw_lines(pb, M + 6, y, wrap(item, _HELV, 9.6, CW - 12), False, 9.6, _INK, 12.5)
                y += 4
            y += 8
    return fdoc


def _build_appendix(doc, spec: dict, base_dir: Path) -> None:
    ap_spec = spec.get("appendix")
    if not ap_spec:
        return
    figs_dir = base_dir / ap_spec.get("figures_dir", ".")
    ap = doc.new_page(width=PW, height=PH)
    sh = ap.new_shape(); sh.draw_rect(fitz.Rect(0, 0, PW, 64)); sh.finish(fill=_DARK, color=_DARK); sh.commit()
    ap.insert_text((M, 30), clean(ap_spec.get("title", "Appendix")), fontname="hebo", fontsize=16, color=(1, 1, 1))
    yy = 92
    if ap_spec.get("intro"):
        yy = draw_lines(ap, M, yy, wrap(ap_spec["intro"], _HELV, 10.5, CW), False, 10.5, _INK, 15)
        yy += 8
    for fig in ap_spec.get("figures", []):
        pg = doc.new_page(width=PW, height=PH)
        y2 = 56
        y2 = draw_lines(pg, M, y2, wrap(fig.get("title", ""), _HEBO, 12, CW), True, 12, _DARK, 16)
        y2 += 2
        if fig.get("caption"):
            y2 = draw_lines(pg, M, y2, wrap(fig["caption"], _HELV, 9.6, CW), False, 9.6, (0.2, 0.2, 0.2), 13)
        y2 += 10
        fp = figs_dir / fig["file"]
        try:
            px = fitz.Pixmap(str(fp)); aspect = px.height / px.width
            iw = CW; ih = iw * aspect
            if y2 + ih > PH - M:
                ih = PH - M - y2; iw = ih / aspect
            x0 = M + (CW - iw) / 2
            pg.insert_image(fitz.Rect(x0, y2, x0 + iw, y2 + ih), filename=str(fp))
        except Exception as e:   # pragma: no cover - missing figure is non-fatal
            pg.insert_text((M, y2 + 20), clean(f"[figure {fig['file']} unavailable: {e}]"),
                           fontname="helv", fontsize=9, color=(0.6, 0, 0))


def build_annotated_pdf(src_pdf, spec: dict, out_pdf, *, sort_by_page: bool = True) -> dict[str, Any]:
    """Build an annotated copy of ``src_pdf`` from ``spec`` and write ``out_pdf``.

    Returns ``{"output", "pages", "n_notes", "misses"}``. ``misses`` lists
    ``(note_number, anchor)`` for any anchor that did not bind anywhere in the
    document (the note is still emitted on its hint page, badge-only).
    """
    src_pdf = Path(src_pdf)
    out_pdf = Path(out_pdf)
    base_dir = Path(spec.get("_base_dir", src_pdf.parent))
    notes = list(spec.get("notes", []))
    for i, nt in enumerate(notes):
        missing = {"page", "anchor", "cat", "header", "body"} - set(nt)
        if missing:
            raise ValueError(f"note #{i + 1} missing fields {sorted(missing)}")
        _primary(nt["cat"])   # validate category early
    if sort_by_page:
        notes.sort(key=lambda n: int(n["page"]))   # badges/commentary in reading order

    doc = fitz.open(str(src_pdf))
    by_page, misses = _place_notes(doc, notes)

    # interleave commentary pages back-to-front so source indices stay valid
    for i in sorted(by_page.keys(), reverse=True):
        cdoc = _build_commentary(i, sorted(by_page[i], key=lambda t: t[0]), doc.page_count)
        doc.insert_pdf(cdoc, start_at=i + 1)
        cdoc.close()

    # front matter at the very start
    fdoc = _front_matter(spec)
    doc.insert_pdf(fdoc, start_at=0)
    fdoc.close()

    _build_appendix(doc, spec, base_dir)

    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_pdf), deflate=True, garbage=3)
    result = {"output": str(out_pdf), "pages": doc.page_count, "n_notes": len(notes), "misses": misses}
    doc.close()
    return result


def load_spec(path) -> dict:
    """Load a notes spec from JSON or YAML; records the spec dir for appendix figures."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml
        spec = yaml.safe_load(text)
    else:
        spec = json.loads(text)
    if not isinstance(spec, dict) or "notes" not in spec:
        raise ValueError(f"{path}: spec must be a JSON/YAML object with a 'notes' list")
    spec.setdefault("_base_dir", str(path.parent))
    return spec
