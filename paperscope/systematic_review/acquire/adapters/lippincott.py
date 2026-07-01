"""Lippincott Williams & Wilkins / Wolters Kluwer journals (Neurology, etc.).

Neurology.org and the wider WK family route every authenticated request
through Cloudflare for bot protection. In our experience the SSO start
URL (`/action/ssostart`) returns a Cloudflare challenge that
Playwright's default Chromium often fails to clear automatically.

Strategy:
  1. Try the regular click flow first. If a download lands, great.
  2. If we see a Cloudflare interstitial title, surface that as the
     outcome so the driver can escalate to headed-with-human mode.
  3. Direct fetch of `/doi/pdf/<doi>` as a last resort.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


_CLOUDFLARE_TITLES = ("just a moment", "moment...", "checking your browser")


class LippincottAdapter(PublisherAdapter):
    name = "lippincott_wk"
    domain_patterns = (
        "neurology.org",
        "journals.lww.com",
        "lww.com",
        "wkhealth.com",
    )
    doi_prefixes = ("10.1212/", "10.1097/")

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        dest = papers_dir / f"{attempt.pmid}.pdf"
        title = (await page.title()).lower() if page.url else ""

        if any(marker in title for marker in _CLOUDFLARE_TITLES):
            attempt.outcome = Outcome.CLOUDFLARE_CHALLENGE
            attempt.failure_reason = (
                f"Neurology.org / WK: Cloudflare interstitial — title {title!r}. "
                "Needs a real browser session (headed mode + human clickthrough)."
            )
            attempt.final_url = page.url
            return attempt

        for selector in (
            'a[href*="/doi/pdf/"]',
            'a[href*="/pdfdirect"]',
            'a[href*="/doi/pdfdirect/"]',
            'a[href$=".pdf"]',
        ):
            loc = page.locator(selector).first
            if await loc.count():
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                if ok:
                    attempt.agent_note = f"Lippincott/WK: {selector}"
                    return self._finalize_success(attempt, dest)
                attempt.failure_reason = err or ""

        # Direct fetch attempt
        if attempt.doi and "neurology.org" in (page.url or ""):
            direct_url = f"https://www.neurology.org/doi/pdf/{attempt.doi}"
            try:
                response = await page.context.request.get(direct_url)
                body = await response.body()
                if body.startswith(b"%PDF-"):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(body)
                    attempt.final_url = direct_url
                    attempt.agent_note = "Lippincott/WK: constructed /doi/pdf/<doi>"
                    return self._finalize_success(attempt, dest)
            except Exception as e:
                attempt.failure_reason = f"WK direct-fetch err: {type(e).__name__}: {e}"[:200]

        attempt.final_url = page.url
        attempt.outcome = Outcome.NO_PDF_LINK
        if not attempt.failure_reason:
            attempt.failure_reason = "Lippincott/WK: no /doi/pdf or pdfdirect link"
        return attempt
