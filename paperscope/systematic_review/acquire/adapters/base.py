"""Publisher-adapter abstract base + shared types.

Each publisher's PDF-acquisition quirks (DOM structure, redirect chain,
authentication chooser flow) live in a single adapter class. The browser
driver dispatches each paper to the matching adapter based on the URL
the EZProxy redirect chain lands on, falling back to the generic adapter
if no specific one matches.

Three outcome classes you'll see most often:
  - SUCCESS:           PDF saved to papers/<pmid>.pdf, magic-byte verified
  - PAYWALL_UNAUTH:    publisher refused access via your institution's
                       proxy/SSO (no subscription, or session not
                       propagated to publisher)
  - NO_PDF_LINK:       adapter couldn't find a download element

The Outcome class enumerates the rest. Adapters mutate and return a
HarvestAttempt that the driver then writes to harvest-log.jsonl.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page


class Outcome:
    """Per-attempt outcome categories. Matches harvest-log-format.md.

    Where this module adds vs the docs: PUBLISHER_NO_ACCESS distinguishes
    'we hit the auth wall and the institution genuinely doesn't subscribe'
    from PAYWALL_UNAUTH ('session wasn't propagating'). NO_PDF_LINK is the
    adapter-level signal that we landed on the article page but couldn't
    locate a downloadable PDF — different from a paywall, different from
    not_found.
    """
    SUCCESS = "success"
    PAYWALL_UNAUTH = "paywall_unauth"
    PAYWALL_AUTH = "paywall_auth"
    CLOUDFLARE_CHALLENGE = "cloudflare_challenge"
    BOT_BLOCK = "bot_block"
    NOT_FOUND = "not_found"
    PUBLISHER_NO_ACCESS = "publisher_no_access"
    NO_PDF_LINK = "no_pdf_link"
    USER_SKIP = "user_skip"
    USER_RESOLVED = "user_resolved"
    OTHER = "other"


@dataclasses.dataclass
class HarvestAttempt:
    """One per-paper acquisition attempt, matching harvest-log.jsonl schema."""

    pmid: str
    doi: str
    title: str
    url_tried: str
    final_url: Optional[str] = None
    attempt_n: int = 1
    outcome: str = Outcome.OTHER
    saved_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    failure_reason: str = ""
    links_served: list[str] = dataclasses.field(default_factory=list)
    ts: str = ""
    agent_note: str = ""
    adapter: str = ""

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        # Truncate title for log compactness, matching harvest-log-format.md.
        d["title"] = (d.get("title") or "")[:200]
        return d


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def magic_bytes_ok(path: Path) -> bool:
    """Cheap PDF validity check: file starts with `%PDF-` magic bytes."""
    try:
        with path.open("rb") as f:
            return f.read(5) == b"%PDF-"
    except FileNotFoundError:
        return False


class PublisherAdapter(ABC):
    """Per-publisher PDF acquisition logic.

    Subclasses set `name`, `domain_patterns` (substring match against the
    URL the redirect chain landed on), and optionally `doi_prefixes`. They
    implement `harvest(page, attempt, papers_dir)` which performs the
    publisher-specific click/download dance and returns the (mutated)
    attempt.
    """

    name: str = "base"
    domain_patterns: tuple[str, ...] = ()
    doi_prefixes: tuple[str, ...] = ()

    @classmethod
    def can_handle(cls, doi: str, current_url: str) -> bool:
        url_lower = (current_url or "").lower()
        for pattern in cls.domain_patterns:
            if pattern in url_lower:
                return True
        for prefix in cls.doi_prefixes:
            if doi.startswith(prefix):
                return True
        return False

    @abstractmethod
    async def harvest(
        self,
        page: "Page",
        attempt: HarvestAttempt,
        papers_dir: Path,
    ) -> HarvestAttempt:
        """Attempt PDF acquisition on the given page. Mutates `attempt`."""

    # ---------------------------------------------------------------
    # Helpers shared across adapters
    # ---------------------------------------------------------------

    async def _click_and_save(
        self,
        page: "Page",
        locator,
        dest: Path,
        click_timeout_ms: int = 8000,
    ) -> tuple[bool, str, Optional[str]]:
        """Click a locator and capture the resulting PDF.

        Two paths: (a) the click triggers a download event (publisher served
        the response with Content-Disposition: attachment) — Playwright
        intercepts it, we save with our chosen filename; (b) the click
        navigates the page to an inline PDF (Content-Disposition: inline,
        common for JAMA/Silverchair) — we fetch the final URL ourselves and
        write the bytes.

        Returns (saved, final_url, error_reason).
        """
        from playwright.async_api import TimeoutError as PWTimeout

        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            async with page.expect_download(timeout=click_timeout_ms) as dl_info:
                await locator.click()
            download = await dl_info.value
            await download.save_as(dest)
            return True, page.url, None
        except PWTimeout:
            pass
        except Exception as e:
            return False, page.url, f"click err: {type(e).__name__}: {e}"[:200]

        # No download event — assume the click navigated to an inline PDF.
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=8000)
        except Exception:
            pass
        final_url = page.url

        if not _looks_like_pdf_url(final_url):
            return False, final_url, "click did not produce a download or PDF URL"

        try:
            response = await page.context.request.get(final_url)
            body = await response.body()
        except Exception as e:
            return False, final_url, f"inline-fetch err: {type(e).__name__}: {e}"[:200]
        if not body.startswith(b"%PDF-"):
            return False, final_url, f"inline response not a PDF (first bytes: {body[:16]!r})"

        dest.write_bytes(body)
        return True, final_url, None

    def _finalize_success(self, attempt: HarvestAttempt, dest: Path) -> HarvestAttempt:
        attempt.outcome = Outcome.SUCCESS
        attempt.saved_path = str(dest)
        attempt.file_size_bytes = dest.stat().st_size
        attempt.sha256 = sha256_of(dest)
        return attempt


def _looks_like_pdf_url(url: str) -> bool:
    u = (url or "").lower()
    return any(
        marker in u
        for marker in (
            ".pdf",
            "/pdf/",
            "/pdfft",
            "/pdfdirect",
            "showpdf",
            "silverchair",
            "watermark",
        )
    )
