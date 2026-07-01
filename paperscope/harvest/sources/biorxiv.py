"""bioRxiv/medRxiv API client for preprint discovery.

bioRxiv API docs: https://api.biorxiv.org/
"""

import time
from datetime import datetime, timedelta
from typing import List
import requests

from .base import DiscoverySource, Paper


class BiorxivSource(DiscoverySource):
    """Discover preprints via bioRxiv API."""

    BASE_URL = "https://api.biorxiv.org/details"
    RATE_LIMIT_DELAY = 1.0

    def __init__(self, server: str = "biorxiv"):
        self.server = server
        self.session = requests.Session()
        self._last_request_time = 0.0

    @property
    def name(self) -> str:
        return self.server

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _fetch_recent(self, from_date: datetime, to_date: datetime, cursor: int = 0) -> List[dict]:
        self._rate_limit()
        url = f"{self.BASE_URL}/{self.server}/{from_date.strftime('%Y-%m-%d')}/{to_date.strftime('%Y-%m-%d')}/{cursor}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json().get("collection", [])
        except requests.RequestException as e:
            print(f"  Warning: {self.server} fetch failed: {e}")
            return []

    def _keyword_match(self, text: str, keywords: List[str]) -> List[str]:
        text_lower = text.lower()
        return [kw for kw in keywords if kw.lower() in text_lower]

    def _author_match(self, authors_str: str, target_authors: List[str]) -> List[str]:
        authors_lower = authors_str.lower()
        matched = []
        for author in target_authors:
            parts = author.lower().split()
            last_name = parts[-1] if parts else author.lower()
            if last_name in authors_lower or author.lower() in authors_lower:
                matched.append(author)
        return matched

    def search(
        self,
        keywords: List[str],
        authors: List[str],
        max_results: int = 30,
        lookback_days: int = 30,
    ) -> List[Paper]:
        to_date = datetime.now()
        from_date = to_date - timedelta(days=lookback_days)

        print(f"  Fetching recent {self.server} preprints...")
        all_preprints = []
        cursor = 0

        while True:
            batch = self._fetch_recent(from_date, to_date, cursor)
            if not batch:
                break
            all_preprints.extend(batch)
            if len(batch) < 100:
                break
            cursor += 100
            if cursor >= 500:
                break

        print(f"  Found {len(all_preprints)} total preprints, filtering...")

        papers = []
        seen_ids = set()

        for preprint in all_preprints:
            doi = preprint.get("doi", "")
            if not doi or doi in seen_ids:
                continue

            title = preprint.get("title", "")
            abstract = preprint.get("abstract", "")
            authors_str = preprint.get("authors", "")

            matched_keywords = self._keyword_match(f"{title} {abstract}", keywords)
            matched_authors = self._author_match(authors_str, authors)

            if not matched_keywords and not matched_authors:
                continue

            seen_ids.add(doi)

            pub_date = None
            date_str = preprint.get("date")
            if date_str:
                try:
                    pub_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    pass

            author_list = [a.strip() for a in authors_str.split(";") if a.strip()]

            paper = Paper(
                id=f"doi:{doi}",
                title=title,
                authors=author_list,
                abstract=abstract,
                published_date=pub_date,
                source=self.name,
                source_url=f"https://www.{self.server}.org/content/{doi}",
                pdf_url=f"https://www.{self.server}.org/content/{doi}.full.pdf",
                matched_keywords=matched_keywords,
                matched_authors=matched_authors,
            )
            papers.append(paper)

            if len(papers) >= max_results:
                break

        return papers
