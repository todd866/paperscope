"""Thieme E-Journals (thieme-connect.de).

Thieme attaches a long `ERSESSIONTOKEN` query parameter to every URL,
which trips most URL-content filters. The PDF link points to
`/products/ejournals/pdf/<doi>.pdf` and works through institutional
access when Sydney has a subscription to the title. For *Seminars in
Neurology* specifically, Sydney does NOT subscribe — the link lands on
`profile.thieme.de/.../?type=auth_denied`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


class ThiemeAdapter(PublisherAdapter):
    name = "thieme"
    domain_patterns = ("thieme-connect.de", "thieme-connect.com")
    doi_prefixes = ("10.1055/",)

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        dest = papers_dir / f"{attempt.pmid}.pdf"

        for selector in (
            'a[href*="/products/ejournals/pdf/"]',
            'a[href*="/pdf/"]',
            'a[href$=".pdf"]',
        ):
            loc = page.locator(selector).first
            if await loc.count():
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                # Thieme login wall has `type=auth_denied` in the URL
                if final_url and "auth_denied" in final_url:
                    attempt.outcome = Outcome.PUBLISHER_NO_ACCESS
                    attempt.failure_reason = (
                        "Thieme: type=auth_denied — institution not subscribed to this title"
                    )
                    return attempt
                if ok:
                    attempt.agent_note = f"Thieme: {selector}"
                    return self._finalize_success(attempt, dest)
                attempt.failure_reason = err or ""

        # Try direct URL construction
        if attempt.doi:
            direct_url = f"https://www.thieme-connect.de/products/ejournals/pdf/{attempt.doi}.pdf"
            try:
                response = await page.context.request.get(direct_url)
                body = await response.body()
                if body.startswith(b"%PDF-"):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(body)
                    attempt.final_url = direct_url
                    attempt.agent_note = "Thieme: constructed /products/ejournals/pdf/<doi>.pdf"
                    return self._finalize_success(attempt, dest)
                if b"auth_denied" in body[:2000] or b"login" in body[:2000].lower():
                    attempt.outcome = Outcome.PUBLISHER_NO_ACCESS
                    attempt.failure_reason = "Thieme: direct PDF URL returned login/auth_denied response"
                    attempt.final_url = direct_url
                    return attempt
            except Exception as e:
                attempt.failure_reason = f"Thieme direct-fetch err: {type(e).__name__}: {e}"[:200]

        attempt.final_url = page.url
        attempt.outcome = Outcome.NO_PDF_LINK
        if not attempt.failure_reason:
            attempt.failure_reason = "Thieme: no PDF anchor and direct construction failed"
        return attempt
