"""Base class for paper discovery sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Paper:
    """Represents a discovered paper."""
    id: str  # DOI or arXiv ID
    title: str
    authors: List[str]
    abstract: str
    published_date: Optional[datetime] = None
    source: str = ""  # semantic_scholar, arxiv, openalex, biorxiv
    source_url: str = ""
    pdf_url: Optional[str] = None
    matched_keywords: List[str] = field(default_factory=list)
    matched_authors: List[str] = field(default_factory=list)

    @property
    def display_id(self) -> str:
        """Return a display-friendly ID."""
        if self.id.startswith("10."):
            return f"DOI:{self.id}"
        return self.id

    @property
    def first_author(self) -> str:
        """Return first author et al."""
        if not self.authors:
            return "Unknown"
        if len(self.authors) == 1:
            return self.authors[0]
        return f"{self.authors[0]} et al."


class DiscoverySource(ABC):
    """Abstract base class for paper discovery sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def search(
        self,
        keywords: List[str],
        authors: List[str],
        max_results: int = 30,
        lookback_days: int = 7,
    ) -> List[Paper]:
        pass
