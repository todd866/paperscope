"""BMJ Publishing Group journals (JNNP, BMJ, BMJ Open, etc.).

BMJ's article page has a `Full text PDF` or `Download PDF` link that
points to `/content/<vol>/<issue>/<page>.full.pdf`. The PDF is served
with Content-Disposition: inline; we fetch the bytes after click.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


class BMJAdapter(PublisherAdapter):
    name = "bmj"
    domain_patterns = ("bmj.com", "jnnp.bmj.com", "thorax.bmj.com", "gut.bmj.com")
    doi_prefixes = ("10.1136/",)

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        dest = papers_dir / f"{attempt.pmid}.pdf"

        for selector in (
            'a[href$=".full.pdf"]',
            'a[href*=".full.pdf"]',
            'a[href*="/content/"][href*=".pdf"]',
            'a[href$=".pdf"]',
        ):
            loc = page.locator(selector).first
            if await loc.count():
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                if ok:
                    attempt.agent_note = f"BMJ: {selector}"
                    return self._finalize_success(attempt, dest)
                attempt.failure_reason = err or ""

        for text in ("Full text PDF", "Download PDF", "PDF", "View PDF"):
            loc = page.get_by_role("link", name=text, exact=False).first
            if await loc.count():
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                if ok:
                    attempt.agent_note = f"BMJ: role=link text={text!r}"
                    return self._finalize_success(attempt, dest)

        attempt.final_url = page.url
        attempt.outcome = Outcome.NO_PDF_LINK
        if not attempt.failure_reason:
            attempt.failure_reason = "BMJ: no .full.pdf anchor or PDF link"
        return attempt
