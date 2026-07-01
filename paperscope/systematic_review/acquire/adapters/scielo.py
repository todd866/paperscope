"""SciELO (scielo.br, scielo.org, scielo.cl, etc.).

SciELO's PDF "button" is a real `<button>` element (not `<a>`) that opens
the PDF in a new tab via JS. The cleanest path is to find the `<a>` with
href containing `.pdf` (which always exists alongside the button) and
fetch the bytes directly. Falls back to clicking the visible button.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


class SciELOAdapter(PublisherAdapter):
    name = "scielo"
    domain_patterns = ("scielo.br", "scielo.org", "scielo.cl", "scielosp.org")
    doi_prefixes = ("10.1590/",)

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        dest = papers_dir / f"{attempt.pmid}.pdf"

        # Approach 1: anchor with PDF href (the "Download PDF (English)" link)
        for selector in (
            'a[href$=".pdf"]',
            'a[href*=".pdf?"]',
            'a[href*="/pdf/"]',
        ):
            loc = page.locator(selector).first
            if await loc.count():
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                if ok:
                    attempt.agent_note = f"SciELO: {selector}"
                    return self._finalize_success(attempt, dest)
                attempt.failure_reason = err or ""

        # Approach 2: text-based fallback for buttons / English-language pick
        for text in ("Download PDF (English)", "Download PDF", "PDF (English)", "PDF"):
            loc = page.get_by_role("link", name=text, exact=False).first
            if not await loc.count():
                loc = page.get_by_role("button", name=text, exact=False).first
            if await loc.count():
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                if ok:
                    attempt.agent_note = f"SciELO: role-text {text!r}"
                    return self._finalize_success(attempt, dest)
                attempt.failure_reason = err or ""

        attempt.final_url = page.url
        attempt.outcome = Outcome.NO_PDF_LINK
        if not attempt.failure_reason:
            attempt.failure_reason = "SciELO: no PDF anchor or button"
        return attempt
