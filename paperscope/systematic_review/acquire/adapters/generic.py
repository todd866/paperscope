"""Fallback adapter: best-effort PDF discovery on any unrecognised publisher.

Tries a sequence of common patterns in priority order:
  1. <a href> containing PDF-shaped path segments (articlepdf, pdfft,
     pdfdirect, /pdf/, .pdf)
  2. anchor/button with text matching common PDF-action phrases
  3. accessibility-role-tagged "menuitem" with PDF text (covers Elsevier-
     ScienceDirect-style dropdown PDF selectors)

When the generic adapter wins, that's a signal we should think about a
dedicated adapter for that publisher.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


_PDF_TEXTS = (
    "download pdf",
    "view pdf",
    "full text pdf",
    "full text: pdf",
    "standard pdf",
    "pdf (this article)",
    "english pdf",
)

_PDF_HREF_PATTERNS = (
    "articlepdf",
    "/pdfft",
    "/pdfdirect",
    "/pdf/",
    ".pdf",
    "showpdf",
)


class GenericAdapter(PublisherAdapter):
    name = "generic"
    # Generic always matches as a last resort; the driver should try
    # publisher-specific adapters first.
    domain_patterns = ()
    doi_prefixes = ()

    @classmethod
    def can_handle(cls, doi: str, current_url: str) -> bool:  # noqa: D401
        return True  # last-resort fallback

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        # 1. <a> with PDF-ish href
        for pattern in _PDF_HREF_PATTERNS:
            loc = page.locator(f'a[href*="{pattern}" i]').first
            if await loc.count():
                dest = papers_dir / f"{attempt.pmid}.pdf"
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                if ok:
                    attempt.agent_note = f"generic: matched a[href*={pattern!r}]"
                    return self._finalize_success(attempt, dest)
                attempt.failure_reason = err or ""

        # 2. anchor/button with PDF-action text
        for text in _PDF_TEXTS:
            loc = page.get_by_role("link", name=text, exact=False).first
            if not await loc.count():
                loc = page.get_by_role("button", name=text, exact=False).first
            if not await loc.count():
                loc = page.get_by_role("menuitem", name=text, exact=False).first
            if await loc.count():
                dest = papers_dir / f"{attempt.pmid}.pdf"
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                if ok:
                    attempt.agent_note = f"generic: matched role with text {text!r}"
                    return self._finalize_success(attempt, dest)
                attempt.failure_reason = err or ""

        attempt.outcome = Outcome.NO_PDF_LINK
        if not attempt.failure_reason:
            attempt.failure_reason = "generic adapter: no PDF link or button on page"
        attempt.final_url = page.url
        return attempt
