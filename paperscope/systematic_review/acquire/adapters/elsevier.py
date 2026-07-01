"""Elsevier ScienceDirect (and the journal-branded subdomains).

ScienceDirect's article page has multiple PDF entry points, all of which
ultimately resolve to a `/showPdf?pii=<PII>` URL. The most reliable
locator is the menuitem with text "Standard PDF (opens in a new tab)"
which lives inside the "View PDF" dropdown. We also try
`a[href*="/pdfft"]` (the legacy ScienceDirect download URL) and the
`/article/<PII>/pdf` pattern as fallbacks.

Authentication: institutional access through EZProxy typically lands on
either the linkinghub.elsevier.com redirector or directly on the journal
subdomain (e.g. jns-journal.com). The auth cookie set during the
OpenAthens / Shibboleth handshake propagates to all three.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .base import HarvestAttempt, Outcome, PublisherAdapter

if TYPE_CHECKING:
    from playwright.async_api import Page


class ElsevierAdapter(PublisherAdapter):
    name = "elsevier"
    domain_patterns = (
        "sciencedirect.com",
        "linkinghub.elsevier.com",
        "jns-journal.com",
        "clinph-journal.com",
        ".elsevier.com",
        "thelancet.com",
    )
    doi_prefixes = ("10.1016/",)

    async def harvest(self, page: "Page", attempt: HarvestAttempt, papers_dir: Path) -> HarvestAttempt:
        dest = papers_dir / f"{attempt.pmid}.pdf"

        # Approach 1: the "Standard PDF" menuitem inside the View-PDF dropdown.
        # `get_by_role` matches accessibility tree; survives DOM churn.
        loc = page.get_by_role("menuitem", name="Standard PDF", exact=False).first
        if await loc.count():
            ok, final_url, err = await self._click_and_save(page, loc, dest)
            attempt.final_url = final_url
            if ok:
                attempt.agent_note = "Elsevier: menuitem 'Standard PDF'"
                return self._finalize_success(attempt, dest)
            attempt.failure_reason = err or ""

        # Approach 2: legacy `/pdfft` anchor on classic ScienceDirect pages.
        loc = page.locator('a[href*="/pdfft"]').first
        if await loc.count():
            ok, final_url, err = await self._click_and_save(page, loc, dest)
            attempt.final_url = final_url
            if ok:
                attempt.agent_note = "Elsevier: a[href*='/pdfft']"
                return self._finalize_success(attempt, dest)
            attempt.failure_reason = err or ""

        # Approach 3: any `/showPdf` or `/article/<PII>/pdf` link.
        for href_pat in ("showpdf", "/article/", "/pdf"):
            loc = page.locator(f'a[href*="{href_pat}"]').first
            if await loc.count():
                ok, final_url, err = await self._click_and_save(page, loc, dest)
                attempt.final_url = final_url
                if ok:
                    attempt.agent_note = f"Elsevier: a[href*={href_pat!r}]"
                    return self._finalize_success(attempt, dest)
                attempt.failure_reason = err or ""

        attempt.final_url = page.url
        attempt.outcome = Outcome.NO_PDF_LINK
        if not attempt.failure_reason:
            attempt.failure_reason = "Elsevier: no Standard PDF / pdfft / showPdf link"
        return attempt
