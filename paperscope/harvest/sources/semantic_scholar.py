"""Semantic Scholar API client for paper discovery."""

import time
from datetime import datetime, timedelta
from typing import List
import requests

from .base import DiscoverySource, Paper


class SemanticScholarSource(DiscoverySource):
    """Discover papers via Semantic Scholar API."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    RATE_LIMIT_DELAY = 3.5

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ResearchEngine/0.1 (academic research tool)"
        })
        self._last_request_time = 0.0

    @property
    def name(self) -> str:
        return "semantic_scholar"

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _search_keyword(self, keyword: str, limit: int = 20) -> List[dict]:
        self._rate_limit()
        url = f"{self.BASE_URL}/paper/search"
        params = {
            "query": keyword,
            "limit": limit,
            "fields": "paperId,title,authors,abstract,year,publicationDate,openAccessPdf,externalIds,url",
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json().get("data", [])
        except requests.RequestException as e:
            print(f"  Warning: Semantic Scholar search failed for '{keyword}': {e}")
            return []

    def search(
        self,
        keywords: List[str],
        authors: List[str],
        max_results: int = 30,
        lookback_days: int = 7,
    ) -> List[Paper]:
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        seen_ids: set = set()
        papers: List[Paper] = []

        for keyword in keywords:
            print(f"  Searching Semantic Scholar for: {keyword}")
            results = self._search_keyword(keyword, limit=20)

            for result in results:
                paper_id = result.get("paperId")
                if not paper_id or paper_id in seen_ids:
                    continue

                pub_date_str = result.get("publicationDate")
                pub_date = None
                if pub_date_str:
                    try:
                        pub_date = datetime.fromisoformat(pub_date_str)
                        if pub_date < cutoff_date:
                            continue
                    except ValueError:
                        pass

                external_ids = result.get("externalIds", {})
                doi = external_ids.get("DOI")
                arxiv_id = external_ids.get("ArXiv")
                canonical_id = doi or (f"arXiv:{arxiv_id}" if arxiv_id else paper_id)

                if canonical_id in seen_ids:
                    continue
                seen_ids.add(canonical_id)
                seen_ids.add(paper_id)

                author_list = result.get("authors", [])
                author_names = [a.get("name", "") for a in author_list if a.get("name")]

                matched_authors = []
                for auth in authors:
                    auth_lower = auth.lower()
                    for name in author_names:
                        if auth_lower in name.lower():
                            matched_authors.append(auth)
                            break

                pdf_url = None
                oa_pdf = result.get("openAccessPdf")
                if oa_pdf and isinstance(oa_pdf, dict):
                    pdf_url = oa_pdf.get("url")

                paper = Paper(
                    id=canonical_id,
                    title=result.get("title", "Untitled"),
                    authors=author_names,
                    abstract=result.get("abstract") or "",
                    published_date=pub_date,
                    source=self.name,
                    source_url=result.get("url", ""),
                    pdf_url=pdf_url,
                    matched_keywords=[keyword],
                    matched_authors=matched_authors,
                )
                papers.append(paper)

                if len(papers) >= max_results:
                    return papers

        return papers
