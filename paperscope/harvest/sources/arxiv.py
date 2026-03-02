"""arXiv API client for paper discovery."""

import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List
import requests

from .base import DiscoverySource, Paper


class ArxivSource(DiscoverySource):
    """Discover papers via arXiv API."""

    BASE_URL = "http://export.arxiv.org/api/query"
    RATE_LIMIT_DELAY = 3.0  # arXiv asks for 3 seconds between requests

    ATOM_NS = "{http://www.w3.org/2005/Atom}"
    ARXIV_NS = "{http://arxiv.org/schemas/atom}"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ResearchEngine/0.1 (academic research tool)"
        })
        self._last_request_time = 0.0

    @property
    def name(self) -> str:
        return "arxiv"

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _search(self, query: str, max_results: int = 50) -> List[dict]:
        self._rate_limit()

        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            response = self.session.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            return self._parse_response(response.text)
        except requests.RequestException as e:
            print(f"  Warning: arXiv search failed: {e}")
            return []

    def _parse_response(self, xml_text: str) -> List[dict]:
        results = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        for entry in root.findall(f"{self.ATOM_NS}entry"):
            entry_id = entry.findtext(f"{self.ATOM_NS}id", "")
            arxiv_id = entry_id.split("/abs/")[-1] if "/abs/" in entry_id else ""

            title = entry.findtext(f"{self.ATOM_NS}title", "").strip()
            title = " ".join(title.split())

            abstract = entry.findtext(f"{self.ATOM_NS}summary", "").strip()

            authors = []
            for author in entry.findall(f"{self.ATOM_NS}author"):
                name = author.findtext(f"{self.ATOM_NS}name", "")
                if name:
                    authors.append(name)

            published = entry.findtext(f"{self.ATOM_NS}published", "")
            pub_date = None
            if published:
                try:
                    pub_date = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError:
                    pass

            categories = []
            for cat in entry.findall(f"{self.ATOM_NS}category"):
                term = cat.get("term", "")
                if term:
                    categories.append(term)

            pdf_url = None
            for link in entry.findall(f"{self.ATOM_NS}link"):
                if link.get("type") == "application/pdf":
                    pdf_url = link.get("href")
                    break

            results.append({
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "published_date": pub_date,
                "categories": categories,
                "pdf_url": pdf_url,
                "url": entry_id,
            })

        return results

    def search(
        self,
        keywords: List[str],
        authors: List[str],
        max_results: int = 30,
        lookback_days: int = 7,
        categories: List[str] = None,
    ) -> List[Paper]:
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        seen_ids: set = set()
        papers: List[Paper] = []

        if categories:
            cat_query = " OR ".join(f"cat:{cat}" for cat in categories)
        else:
            cat_query = None

        for keyword in keywords:
            query_parts = [f'all:"{keyword}"']
            if cat_query:
                query_parts.append(f"({cat_query})")

            query = " AND ".join(query_parts)
            print(f"  Searching arXiv for: {keyword}")

            results = self._search(query, max_results=30)

            for result in results:
                arxiv_id = result["arxiv_id"]
                if not arxiv_id or arxiv_id in seen_ids:
                    continue

                pub_date = result["published_date"]
                if pub_date and pub_date.replace(tzinfo=None) < cutoff_date:
                    continue

                seen_ids.add(arxiv_id)

                matched_authors = []
                for auth in authors:
                    auth_lower = auth.lower()
                    for name in result["authors"]:
                        if auth_lower in name.lower():
                            matched_authors.append(auth)
                            break

                paper = Paper(
                    id=f"arXiv:{arxiv_id}",
                    title=result["title"],
                    authors=result["authors"],
                    abstract=result["abstract"],
                    published_date=pub_date.replace(tzinfo=None) if pub_date else None,
                    source=self.name,
                    source_url=result["url"],
                    pdf_url=result["pdf_url"],
                    matched_keywords=[keyword],
                    matched_authors=matched_authors,
                )
                papers.append(paper)

                if len(papers) >= max_results:
                    return papers

        return papers
