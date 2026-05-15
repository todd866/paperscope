"""Paper analysis tools — embedding-powered and forensic."""

from .citation_alignment import citation_alignment, uncited_relevance
from .novelty import novelty_analysis
from .reviewer_probes import reviewer_probes

# Lazy imports for modules with heavier dependencies (scipy, etc.):
#   from paperscope.analysis.forensic_stats import grim, ...
#   from paperscope.analysis.critical_read import critical_read

__all__ = [
    "citation_alignment",
    "uncited_relevance",
    "novelty_analysis",
    "reviewer_probes",
]
