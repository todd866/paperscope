"""Wiley Online Library (onlinelibrary.wiley.com).

The article page has a `Download PDF` button that links to
`/doi/pdf/<doi>` which serves the PDF with Content-Disposition: inline.
There's also an `/epdf/<doi>` URL which is a JS-rendered viewer — we
prefer the `/pdf/` path.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


class WileyAdapter(PublisherAdapter):
    name = "wiley"
    domain_patterns = ("onlinelibrary.wiley.com",)
    doi_prefixes = ("10.1002/", "10.1111/")

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        dest = papers_dir / f"{attempt.pmid}.pdf"

        # Prefer the direct /doi/pdf/ anchor.
        loc = page.locator('a[href*="/doi/pdf/"]').first
        if await loc.count():
            ok, final_url, err = await self._click_and_save(page, loc, dest)
            attempt.final_url = final_url
            if ok:
                attempt.agent_note = "Wiley: a[href*='/doi/pdf/']"
                return self._finalize_success(attempt, dest)
            attempt.failure_reason = err or ""

        # Fallback: "Download PDF" link by accessibility role.
        loc = page.get_by_role("link", name="Download PDF", exact=False).first
        if await loc.count():
            ok, final_url, err = await self._click_and_save(page, loc, dest)
            attempt.final_url = final_url
            if ok:
                attempt.agent_note = "Wiley: role=link 'Download PDF'"
                return self._finalize_success(attempt, dest)
            attempt.failure_reason = err or ""

        # If the article page has an /epdf/ viewer, derive the /pdf/ URL.
        doi = attempt.doi
        if doi:
            direct_url = f"https://onlinelibrary.wiley.com/doi/pdf/{doi}"
            try:
                response = await page.context.request.get(direct_url)
                body = await response.body()
                if body.startswith(b"%PDF-"):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(body)
                    attempt.final_url = direct_url
                    attempt.agent_note = "Wiley: constructed /doi/pdf/<doi>"
                    return self._finalize_success(attempt, dest)
            except Exception as e:
                attempt.failure_reason = f"Wiley direct-fetch err: {type(e).__name__}: {e}"[:200]

        attempt.final_url = page.url
        attempt.outcome = Outcome.NO_PDF_LINK
        if not attempt.failure_reason:
            attempt.failure_reason = "Wiley: no /doi/pdf anchor or Download PDF link"
        return attempt
