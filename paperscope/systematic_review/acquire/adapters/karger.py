"""Karger Publishers (karger.com).

Karger's article page typically has a `Download PDF` button at the top.
Behind institutional access, the PDF is served at
`/Article/Pdf/<article-id>` or `/Article/FullText/<id>?DownloadPDF=true`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


class KargerAdapter(PublisherAdapter):
    name = "karger"
    domain_patterns = ("karger.com",)
    doi_prefixes = ("10.1159/",)

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        dest = papers_dir / f"{attempt.pmid}.pdf"

        for selector in (
            'a[href*="article-pdf"]',
            'a[href*="article-Pdf"]',
            'a[href*="/Article/Pdf/"]',
            'a[href*="DownloadPDF=true"]',
            'a[href$=".pdf"]',
        ):
            loc = page.locator(selector).first
            if await loc.count():
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                if ok:
                    attempt.agent_note = f"Karger: {selector}"
                    return self._finalize_success(attempt, dest)
                attempt.failure_reason = err or ""

        # Role-based fallback
        for text in ("Download PDF", "PDF", "Save PDF"):
            for role in ("link", "button"):
                loc = page.get_by_role(role, name=text, exact=False).first
                if await loc.count():
                    ok, final_url, err = await self._click_and_save(page, loc, dest)
                    attempt.final_url = final_url
                    if ok:
                        attempt.agent_note = f"Karger: role={role} text={text!r}"
                        return self._finalize_success(attempt, dest)

        attempt.final_url = page.url
        attempt.outcome = Outcome.NO_PDF_LINK
        if not attempt.failure_reason:
            attempt.failure_reason = (
                "Karger: no PDF anchor. Abstract page may have hidden the "
                "PDF link pending institutional auth — Sydney's session may "
                "not be propagating."
            )
        return attempt
