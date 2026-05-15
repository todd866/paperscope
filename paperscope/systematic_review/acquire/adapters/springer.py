"""Springer Nature (link.springer.com).

Pattern: `a[data-track-action="Download PDF"]` or `a[href*="/content/pdf/"]`.
Springer serves PDFs at `/content/pdf/<doi>.pdf` which Chrome saves
directly (Content-Disposition: attachment).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


class SpringerAdapter(PublisherAdapter):
    name = "springer"
    domain_patterns = ("link.springer.com", "rdcu.be")
    doi_prefixes = ("10.1007/", "10.1038/", "10.1186/")

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        dest = papers_dir / f"{attempt.pmid}.pdf"

        for selector in (
            'a[data-track-action="Download PDF"]',
            'a[data-track-action*="pdf" i]',
            'a[href*="/content/pdf/"]',
            'a[href$=".pdf"]',
        ):
            loc = page.locator(selector).first
            if await loc.count():
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                if ok:
                    attempt.agent_note = f"Springer: {selector}"
                    return self._finalize_success(attempt, dest)
                attempt.failure_reason = err or ""

        # Direct construction
        if attempt.doi:
            direct_url = f"https://link.springer.com/content/pdf/{attempt.doi}.pdf"
            try:
                response = await page.context.request.get(direct_url)
                body = await response.body()
                if body.startswith(b"%PDF-"):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(body)
                    attempt.final_url = direct_url
                    attempt.agent_note = "Springer: constructed /content/pdf/<doi>.pdf"
                    return self._finalize_success(attempt, dest)
            except Exception as e:
                attempt.failure_reason = f"Springer direct-fetch err: {type(e).__name__}: {e}"[:200]

        attempt.final_url = page.url
        attempt.outcome = Outcome.NO_PDF_LINK
        if not attempt.failure_reason:
            attempt.failure_reason = "Springer: no Download PDF anchor or /content/pdf/ link"
        return attempt
