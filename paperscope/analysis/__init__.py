"""Paper analysis tools — embedding-powered and forensic."""

from .citation_alignment import citation_alignment, uncited_relevance
from .novelty import novelty_analysis
from .reviewer_probes import reviewer_probes, reviewer_response_prep
from .self_overlap import self_overlap_check
from .argument_flow import argument_flow
from .cross_paper import cross_paper_consistency

# Lazy imports for modules with heavier dependencies (scipy, etc.)
# Use: from paperscope.analysis.forensic_stats import grim, ...
# Use: from paperscope.analysis.critical_read import critical_read

__all__ = [
    "citation_alignment",
    "uncited_relevance",
    "novelty_analysis",
    "reviewer_probes",
    "reviewer_response_prep",
    "self_overlap_check",
    "argument_flow",
    "cross_paper_consistency",
]
