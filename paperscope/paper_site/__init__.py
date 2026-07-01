"""Reusable PaperScope paper-site scaffolding.

The paper_site module owns the shared web-reader contract used by academic
PaperScope projects and medical LocalEvidence projects. LocalEvidence should
wrap this module rather than fork its own paper-reader UI.
"""

from .scaffold import PaperSiteConfig, scaffold_paper_site

__all__ = ["PaperSiteConfig", "scaffold_paper_site"]
