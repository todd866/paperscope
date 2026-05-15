"""JAMA Network family (JAMA, JAMA Neurology, JAMA Internal Medicine, etc.).

JAMA serves PDFs via Silverchair: clicking a `Download PDF` link on the
article page (href like `/journals/jamaneurology/articlepdf/<id>/<noc>.pdf`)
follows a redirect to `watermarkXX.silverchair.com/<noc>.pdf?token=...`.
Silverchair serves the PDF with Content-Disposition: inline, so Chrome
displays it. Playwright's `expect_download` won't fire; the
`_click_and_save` helper then fetches the final URL via the page's
request context (which carries the auth cookies) and writes the bytes.

Observed quirk during testing: Chrome's per-origin auto-download prompt
engages after the first JAMA download. With Playwright we bypass that
because we save the inline-served PDF directly rather than triggering
a browser-level download.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


class JamaNetworkAdapter(PublisherAdapter):
    name = "jama_network"
    domain_patterns = ("jamanetwork.com",)
    doi_prefixes = ("10.1001/",)

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        # The PDF link is consistently `a[href*="articlepdf"]`.
        loc = page.locator('a[href*="articlepdf"]').first
        if not await loc.count():
            attempt.outcome = Outcome.NO_PDF_LINK
            attempt.failure_reason = "JAMA: no a[href*='articlepdf'] element"
            attempt.final_url = page.url
            return attempt

        dest = papers_dir / f"{attempt.pmid}.pdf"
        ok, final_url, err = await self._click_and_save(page, loc, dest, click_timeout_ms=4000)
        attempt.final_url = final_url
        if ok:
            attempt.agent_note = "JAMA Network: article-PDF link → Silverchair signed URL → inline fetch"
            return self._finalize_success(attempt, dest)
        attempt.failure_reason = err or "JAMA: click did not yield a PDF"
        attempt.outcome = Outcome.OTHER
        return attempt
