"""Human-in-the-loop review UI: static HTML pages generated from JSONL state.

Two modes (designed; only the static export is built in v0):

  static export — `build.build_review_site(corpus_dir, out_dir)` reads records,
    screening, and extraction JSONL and writes a directory of HTML pages that
    can be opened locally or published as a GitHub Pages artefact. Useful for
    final state ("this is what we did, see this page") and read-only audit.

  live server — a thin `python -m paperscope.systematic_review.ui.serve` (not
    yet implemented) that serves the same pages but accepts include/exclude
    overrides via POST back into the JSONL. Closest to Covidence's feel.
"""

from paperscope.systematic_review.ui.build import build_review_site

__all__ = ["build_review_site"]
