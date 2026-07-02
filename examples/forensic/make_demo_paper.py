#!/usr/bin/env python3
"""Generate demo-paper.pdf: a two-page SYNTHETIC mini-paper with planted errors.

The paper is deliberately fake ("SYNTHETIC DEMONSTRATION -- not real research")
and its Results section embeds one of each thing the forensic CLI detects:

  1. a decision error   -- t(38) = 1.02, p = .003  (recomputed p ~ .31: the
                           significance claim flips -> FAIL)
  2. a reporting error  -- t(38) = 2.20, p = .019  (recomputed p ~ .034: wrong
                           number, but still significant -> FLAG)
  3. a consistent test  -- F(2, 57) = 4.51, p = .015 (recomputes fine -> PASS)
  4. an impossible r    -- r(24) = 1.07, p < .001  (|r| >= 1 -> FAIL)
  5. a Table 1 whose treatment mean fails GRIM: mean 18.72 with n = 22 is
     unreachable by any integer-valued sum (411.84 rounds to no achievable
     mean) -- caught in table mode via table1.json.

Each statistic is kept on a single rendered line so text extraction returns
it verbatim and the annotate engine's anchor search can bind it.

Usage:
    python3 examples/forensic/make_demo_paper.py [out.pdf]

Programmatic:
    from make_demo_paper import build_demo_pdf
    build_demo_pdf("demo-paper.pdf")
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz  # PyMuPDF

PW, PH = 612, 792   # US Letter, points (matches the annotate engine)
M = 72              # margin

# ── page 1: front matter, clearly marked synthetic ──
PAGE1 = [
    ("hebo", 18, "The Effect of X on Y: A Randomised Trial"),
    ("helv", 10, ""),
    ("helv", 11, "A. Nonymous and B. Ogus"),
    ("helv", 10, "Institute for Synthetic Examples"),
    ("hebo", 10, "SYNTHETIC DEMONSTRATION -- not real research, not real "
                 "authors."),
    ("hebo", 10, "Every statistic below was fabricated to exercise "
                 "paperscope's forensic checks."),
    ("helv", 10, ""),
    ("hebo", 12, "Abstract"),
    ("helv", 10, "We randomised 46 participants to treatment (n = 22) or"),
    ("helv", 10, "control (n = 24) and measured outcome Y on the Q-scale"),
    ("helv", 10, "(range 0-63). Treatment improved Y across the board."),
    ("helv", 10, ""),
    ("hebo", 12, "1. Introduction"),
    ("helv", 10, "X has long been suspected to affect Y. We test this"),
    ("helv", 10, "directly. Method details are on page 2 with the results."),
]

# ── page 2: Results with the planted errors + Table 1 ──
PAGE2 = [
    ("hebo", 12, "2. Results"),
    ("helv", 10, ""),
    ("helv", 10, "Participants in the treatment group scored higher than"),
    ("helv", 10, "controls, t(38) = 1.02, p = .003, a large and reliable"),
    ("helv", 10, "difference. A follow-up comparison of the two subscales"),
    ("helv", 10, "also reached significance, t(38) = 2.20, p = .019. The"),
    ("helv", 10, "omnibus effect of condition was significant,"),
    ("helv", 10, "F(2, 57) = 4.51, p = .015. Pre-test scores correlated"),
    ("helv", 10, "strongly with post-test scores, r(24) = 1.07, p < .001."),
    ("helv", 10, ""),
    ("hebo", 11, "Table 1. Baseline Q-scale scores by group."),
    ("helv", 10, ""),
    ("helv", 10, "  Group        n     Mean     SD"),
    ("helv", 10, "  ------------------------------"),
    ("helv", 10, "  Treatment   22    18.72   5.31"),
    ("helv", 10, "  Control     24    17.29   5.44"),
    ("helv", 10, ""),
    ("hebo", 12, "3. Discussion"),
    ("helv", 10, "The effect of X on Y is decisive and completely made up."),
    ("helv", 10, "Transcribe Table 1 into table1.json for the GRIM check;"),
    ("helv", 10, "point the forensic CLI at this PDF for the p-value checks."),
]


def _render_page(doc: fitz.Document, lines) -> None:
    page = doc.new_page(width=PW, height=PH)
    y = 90
    for fontname, size, text in lines:
        if text:
            page.insert_text((M, y), text, fontname=fontname, fontsize=size)
        y += size * 1.55


def build_demo_pdf(out_path) -> Path:
    """Write the two-page synthetic demo paper to ``out_path``."""
    out_path = Path(out_path)
    doc = fitz.open()
    _render_page(doc, PAGE1)
    _render_page(doc, PAGE2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    doc.close()
    return out_path


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path(__file__).parent / "demo-paper.pdf"
    build_demo_pdf(out)
    print(f"wrote {out}")
