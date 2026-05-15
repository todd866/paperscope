"""Playwright-driven institutional-access PDF harvester.

The flow per paper:
  1. Navigate to `https://doi-org.<ezproxy_host>/<doi>` (the institution's
     EZProxy entry point). Playwright follows the SAML/SSO redirect chain.
  2. Wait for the URL to settle on a publisher domain (or timeout / fail).
  3. Pick the matching publisher adapter based on the landed URL + DOI.
  4. Adapter performs publisher-specific click/fetch to produce
     `papers/<pmid>.pdf`. Adapters set `outcome` and `failure_reason`
     in the HarvestAttempt.
  5. Append the attempt to `harvest-log.jsonl`.

Concurrency: papers are processed N at a time via asyncio.Semaphore;
each runs on its own Page in a shared BrowserContext (one set of session
cookies). Default N=4 — Playwright handles more, but publisher rate
limits and Cloudflare watchfulness make modest parallelism safer.

Entry points:
  `harvest_records(records, corpus_dir, ezproxy_host, ...)` — the
  programmatic API. Returns a `BrowserHarvestReport` with per-paper
  outcomes plus aggregate counters.

The CLI wraps this; see `paperscope/systematic_review/__main__.py`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Iterable, Optional, TYPE_CHECKING

from .adapters import HarvestAttempt, Outcome, magic_bytes_ok, pick_adapter, utc_now
from .session import Session, DEFAULT_STATE_PATH
from .strategy_cache import DEFAULT_CACHE_PATH, StrategyCache

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page


_STRATUM_TO_LINK = {
    "criteria": ["1", "2"],
    "delay": ["3"],
    "feature_dense": ["5", "6"],
    "dynamics": ["6"],
}


def _links_for(strata: list[str]) -> list[str]:
    out: list[str] = []
    for s in strata or []:
        for link in _STRATUM_TO_LINK.get(s, []):
            if link not in out:
                out.append(link)
    return out


@dataclasses.dataclass
class BrowserHarvestReport:
    total: int = 0
    success: int = 0
    paywall_no_access: int = 0
    cloudflare: int = 0
    no_pdf_link: int = 0
    other_failure: int = 0
    skipped_already_have: int = 0
    attempts: list[HarvestAttempt] = dataclasses.field(default_factory=list)

    def add(self, attempt: HarvestAttempt) -> None:
        self.attempts.append(attempt)
        if attempt.outcome == Outcome.SUCCESS:
            self.success += 1
        elif attempt.outcome in (Outcome.PUBLISHER_NO_ACCESS, Outcome.PAYWALL_UNAUTH):
            self.paywall_no_access += 1
        elif attempt.outcome == Outcome.CLOUDFLARE_CHALLENGE:
            self.cloudflare += 1
        elif attempt.outcome == Outcome.NO_PDF_LINK:
            self.no_pdf_link += 1
        else:
            self.other_failure += 1

    def pretty(self) -> str:
        return (
            f"Browser harvest: {self.success}/{self.total} succeeded "
            f"({self.skipped_already_have} skipped). "
            f"paywall/no-access: {self.paywall_no_access}, "
            f"cloudflare: {self.cloudflare}, "
            f"no-pdf-link: {self.no_pdf_link}, "
            f"other: {self.other_failure}"
        )


async def _harvest_one(
    context: "BrowserContext",
    record: dict,
    ezproxy_host: str,
    papers_dir: Path,
    semaphore: asyncio.Semaphore,
    cache: Optional[StrategyCache] = None,
    *,
    nav_timeout_ms: int = 45000,
    settle_timeout_s: int = 12,
    respect_cache: bool = True,
) -> HarvestAttempt:
    """Open a fresh page, navigate, dispatch to the right adapter."""
    pmid = str(record.get("pmid", "")).strip()
    doi = (record.get("doi") or "").strip()
    title = record.get("title", "") or ""
    strata = record.get("strata", []) or []

    url_tried = f"https://doi-org.{ezproxy_host}/{doi}"
    attempt = HarvestAttempt(
        pmid=pmid,
        doi=doi,
        title=title,
        url_tried=url_tried,
        attempt_n=1,
        ts=utc_now(),
        links_served=_links_for(strata),
    )

    if not doi:
        attempt.outcome = Outcome.NOT_FOUND
        attempt.failure_reason = "no DOI"
        return attempt

    # Cache pre-check: if this DOI is known to fail permanently, skip.
    if cache is not None:
        verdict = cache.consult(doi, "", respect_cache=respect_cache)
        if verdict.should_skip:
            attempt.outcome = verdict.expected_outcome or Outcome.PAYWALL_UNAUTH
            attempt.failure_reason = f"strategy-cache hit: {verdict.reason}"
            attempt.agent_note = "skipped per strategy cache"
            return attempt

    async with semaphore:
        page: Optional["Page"] = None
        try:
            page = await context.new_page()
            try:
                await page.goto(url_tried, wait_until="domcontentloaded", timeout=nav_timeout_ms)
            except Exception as e:
                attempt.outcome = Outcome.OTHER
                attempt.failure_reason = f"navigation: {type(e).__name__}: {e}"[:200]
                attempt.final_url = page.url if page else None
                return attempt

            # Let the redirect chain settle (SSO/SAML/Cloudflare).
            await _wait_for_settle(page, settle_timeout_s)

            adapter = pick_adapter(doi, page.url)
            attempt.adapter = adapter.name
            attempt = await adapter.harvest(page, attempt, papers_dir)

            # Defensive: verify the saved file is actually a PDF.
            if attempt.outcome == Outcome.SUCCESS and attempt.saved_path:
                saved = Path(attempt.saved_path)
                if not magic_bytes_ok(saved):
                    rejects = saved.parent / "_rejects"
                    rejects.mkdir(exist_ok=True)
                    bad = rejects / saved.name
                    saved.rename(bad)
                    attempt.outcome = Outcome.OTHER
                    attempt.failure_reason = f"magic-byte verify failed; moved to {bad.relative_to(papers_dir.parent)}"
                    attempt.saved_path = None
                    attempt.file_size_bytes = None
                    attempt.sha256 = None
            return attempt

        except Exception as e:
            attempt.outcome = Outcome.OTHER
            attempt.failure_reason = f"driver exc: {type(e).__name__}: {e}"[:200]
            return attempt
        finally:
            if page is not None:
                try:
                    await page.close()
                except Exception:
                    pass


async def _wait_for_settle(page: "Page", timeout_s: int) -> None:
    """Poll the page URL every 0.5s until it stops changing for two ticks,
    or `timeout_s` elapses. SAML / Cloudflare redirect chains can take
    several seconds to complete; networkidle is unreliable on publisher
    sites with analytics beacons."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    prev = page.url
    stable_ticks = 0
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.5)
        cur = page.url
        if cur == prev:
            stable_ticks += 1
            if stable_ticks >= 2:
                return
        else:
            stable_ticks = 0
            prev = cur


def _append_log(log_path: Path, attempt: HarvestAttempt) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as f:
        f.write(json.dumps(attempt.to_dict(), ensure_ascii=False) + "\n")


async def harvest_records(
    records: Iterable[dict],
    *,
    corpus_dir: Path | str,
    ezproxy_host: str = "ezproxy.library.usyd.edu.au",
    concurrency: int = 4,
    headless: bool = False,
    skip_already_have: bool = True,
    state_path: Path | None = None,
    warmup_doi: Optional[str] = None,
    verbose: bool = True,
) -> BrowserHarvestReport:
    """Run the browser-driven harvest. Returns a BrowserHarvestReport.

    Per-paper outcomes append to `<corpus_dir>/harvest-log.jsonl`. PDFs
    land in `<corpus_dir>/papers/<pmid>.pdf`.

    `warmup_doi`: if provided and no usable session state exists, opens a
    headed browser, navigates to that DOI, and waits for institutional
    login to complete before starting the queue. Pick a DOI known to be
    paywalled for the institution; that exposes the auth chooser.
    """
    corpus_dir = Path(corpus_dir)
    papers_dir = corpus_dir / "papers"
    papers_dir.mkdir(parents=True, exist_ok=True)
    log_path = corpus_dir / "harvest-log.jsonl"

    if state_path is None:
        state_path = corpus_dir / DEFAULT_STATE_PATH

    cache = StrategyCache(corpus_dir / DEFAULT_CACHE_PATH)

    records = list(records)
    if skip_already_have:
        have = {p.stem for p in papers_dir.glob("*.pdf")}
        records_to_run = [r for r in records if str(r.get("pmid", "")) not in have]
        skipped = len(records) - len(records_to_run)
    else:
        records_to_run = records
        skipped = 0

    report = BrowserHarvestReport(total=len(records_to_run), skipped_already_have=skipped)
    if not records_to_run:
        if verbose:
            print(f"Nothing to harvest — all {len(records)} records already in papers/.")
        return report

    session = Session(Path(state_path))

    # Warmup: if no usable state exists or caller insists, open headed first.
    needs_warmup = warmup_doi and not Session.state_exists(Path(state_path))
    await session.open(headless=False if needs_warmup else headless)

    try:
        if needs_warmup:
            ok = await session.warmup(ezproxy_host, warmup_doi)
            if not ok and verbose:
                print("[driver] warmup did not complete; proceeding anyway")

        sem = asyncio.Semaphore(concurrency)
        tasks = [
            asyncio.create_task(
                _harvest_one(session.context, rec, ezproxy_host, papers_dir, sem, cache)
            )
            for rec in records_to_run
        ]
        for i, task in enumerate(asyncio.as_completed(tasks), 1):
            attempt = await task
            _append_log(log_path, attempt)
            # Record outcome in the strategy cache so future runs benefit.
            publisher_domain = _publisher_domain_from(attempt.final_url or "")
            cache.note_attempt(
                attempt.doi,
                attempt.outcome,
                attempt.adapter,
                publisher_domain,
                strategy_name=attempt.agent_note,
                evidence=attempt.failure_reason,
            )
            report.add(attempt)
            if verbose:
                marker = "✓" if attempt.outcome == Outcome.SUCCESS else "·"
                print(
                    f"  [{i}/{len(records_to_run)}] {marker} {attempt.pmid} "
                    f"({attempt.adapter}) → {attempt.outcome}"
                )

    finally:
        cache.save()
        await session.close(save_state=True)

    if verbose:
        print()
        print(report.pretty())
        print(cache.summary())
    return report


def _publisher_domain_from(url: str) -> str:
    """Extract a publisher domain marker from a final URL for cache keying."""
    u = (url or "").lower()
    for marker in (
        "jamanetwork.com",
        "sciencedirect.com",
        "linkinghub.elsevier.com",
        "onlinelibrary.wiley.com",
        "tandfonline.com",
        "link.springer.com",
        "scielo.br",
        "scielo.org",
        "karger.com",
        "thieme-connect.de",
        "neurology.org",
        "journals.lww.com",
        "bmj.com",
    ):
        if marker in u:
            return marker
    # Fall back to scheme+host
    try:
        from urllib.parse import urlparse
        return urlparse(u).netloc
    except Exception:
        return ""
