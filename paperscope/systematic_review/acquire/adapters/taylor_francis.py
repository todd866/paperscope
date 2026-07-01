"""Taylor & Francis Online (tandfonline.com).

Stable pattern: the article page has `a[href*="/doi/pdf/"]` linking to the
PDF. T&F serves with Content-Disposition: attachment in most cases, so
Playwright's `expect_download` fires; we save with our chosen filename.

T&F's auth handshake is the most reliable in our sample — once the
OpenAthens SAML completes for any tandfonline article, subsequent papers
in the same session resolve cleanly.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


class TaylorFrancisAdapter(PublisherAdapter):
    name = "taylor_francis"
    domain_patterns = ("tandfonline.com",)
    doi_prefixes = ("10.1080/", "10.3109/")

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        dest = papers_dir / f"{attempt.pmid}.pdf"

        loc = page.locator('a[href*="/doi/pdf/"]').first
        if await loc.count():
            ok, final_url, err = await self._click_and_save(page, loc, dest)
            attempt.final_url = final_url
            if ok:
                attempt.agent_note = "T&F: a[href*='/doi/pdf/']"
                return self._finalize_success(attempt, dest)
            attempt.failure_reason = err or ""

        loc = page.get_by_role("link", name="Download PDF", exact=False).first
        if await loc.count():
            ok, final_url, err = await self._click_and_save(page, loc, dest)
            attempt.final_url = final_url
            if ok:
                attempt.agent_note = "T&F: role=link 'Download PDF'"
                return self._finalize_success(attempt, dest)
            attempt.failure_reason = err or ""

        # Direct construction: tandfonline /doi/pdf/<doi>?download=true
        if attempt.doi:
            direct_url = f"https://www.tandfonline.com/doi/pdf/{attempt.doi}?download=true"
            try:
                response = await page.context.request.get(direct_url)
                body = await response.body()
                if body.startswith(b"%PDF-"):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(body)
                    attempt.final_url = direct_url
                    attempt.agent_note = "T&F: constructed /doi/pdf/<doi>?download=true"
                    return self._finalize_success(attempt, dest)
            except Exception as e:
                attempt.failure_reason = f"T&F direct-fetch err: {type(e).__name__}: {e}"[:200]

        attempt.final_url = page.url
        attempt.outcome = Outcome.NO_PDF_LINK
        if not attempt.failure_reason:
            attempt.failure_reason = "T&F: no /doi/pdf/ anchor or Download PDF role"
        return attempt
