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

from paperscope.ingest.browser_queue import resolve_ezproxy_host

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
    inter_paper_delay_s: float = 0.0,
    start_lock: Optional[asyncio.Lock] = None,
    start_state: Optional[dict[str, float]] = None,
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
        if inter_paper_delay_s > 0 and start_lock is not None and start_state is not None:
            # Space actual navigation starts globally across concurrent tasks.
            async with start_lock:
                loop = asyncio.get_event_loop()
                last = start_state.get("last_start")
                if last is not None:
                    wait_s = inter_paper_delay_s - (loop.time() - last)
                    if wait_s > 0:
                        await asyncio.sleep(wait_s)
                start_state["last_start"] = loop.time()
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

            # Defensive: the saved file must be a PDF AND actually contain the paper
            # we asked for. magic_bytes_ok catches HTML/error pages; the title gate
            # catches a wrong-paper delivery (publisher served a neighbour article,
            # a DOI->wrong-PDF, etc.) that is a valid PDF of the wrong content - the
            # exact failure that poisoned ~24% of an earlier corpus. Mirrors the
            # shadow-library guard so every adapter is covered at this one chokepoint.
            if attempt.outcome == Outcome.SUCCESS and attempt.saved_path:
                saved = Path(attempt.saved_path)
                reject_reason = None
                if not magic_bytes_ok(saved):
                    reject_reason = "magic-byte verify failed"
                elif title:
                    try:
                        from ...ingest.shadow_library import pdf_matches_title
                        ok, ratio = pdf_matches_title(saved.read_bytes(), title)
                        if not ok:
                            reject_reason = f"title-content mismatch (ratio={ratio:.2f})"
                    except Exception:
                        pass  # matcher unavailable -> magic-byte check already passed
                if reject_reason:
                    rejects = saved.parent / "_rejects"
                    rejects.mkdir(exist_ok=True)
                    bad = rejects / saved.name
                    saved.rename(bad)
                    attempt.outcome = Outcome.OTHER
                    attempt.failure_reason = f"{reject_reason}; moved to {bad.relative_to(papers_dir.parent)}"
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
    ezproxy_host: str | None = None,
    concurrency: int = 4,
    headless: bool = False,
    skip_already_have: bool = True,
    state_path: Path | None = None,
    warmup_doi: Optional[str] = None,
    user_data_dir: Optional[str] = None,
    profile_directory: Optional[str] = None,
    inter_paper_delay_s: float = 0.0,
    group_by_publisher: bool = False,
    verbose: bool = True,
) -> BrowserHarvestReport:
    """Run the browser-driven harvest. Returns a BrowserHarvestReport.

    Per-paper outcomes append to `<corpus_dir>/harvest-log.jsonl`. PDFs
    land in `<corpus_dir>/papers/<pmid>.pdf`.

    `warmup_doi`: if provided and no usable session state exists, opens a
    headed browser, navigates to that DOI, and waits for institutional
    login to complete before starting the queue. Pick a DOI known to be
    paywalled for the institution; that exposes the auth chooser.

    `user_data_dir`: path to a real Chrome profile (e.g. macOS default at
    `~/Library/Application Support/Google/Chrome`). When set, Playwright
    launches Chrome with that profile via persistent_context — cookies,
    passwords, extensions, and any live OpenAthens session are all
    inherited. Chrome must not be running against the same profile.
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

    if group_by_publisher:
        # Sort so consecutive papers from the same publisher batch together —
        # one SAML / OAuth handshake per publisher then cached cookies do the
        # rest. Massive reduction in IDP traffic.
        def _pub_key(r):
            doi = (r.get("doi") or "").strip().lower()
            return doi.split("/", 1)[0] if "/" in doi else doi
        records_to_run.sort(key=_pub_key)

    report = BrowserHarvestReport(total=len(records_to_run), skipped_already_have=skipped)
    if not records_to_run:
        if verbose:
            print(f"Nothing to harvest — all {len(records)} records already in papers/.")
        return report

    # Every harvested URL goes through the proxy, so fail before launching
    # a browser if no host is configured (arg or $PAPERSCOPE_EZPROXY_HOST).
    # Resolved only now: a no-op rerun (everything cached) needs no host.
    ezproxy_host = resolve_ezproxy_host(ezproxy_host)

    session = Session(Path(state_path))

    # Warmup runs whenever caller passes a warmup_doi. In persistent-context
    # mode this lets the user click through OpenAthens once if their existing
    # session has lapsed; in fresh-launch mode it's the only way to bootstrap
    # institutional cookies. Skipped only if the storage state already looks warm.
    needs_warmup = bool(
        warmup_doi
        and (user_data_dir or not Session.state_exists(Path(state_path)))
    )
    await session.open(
        headless=False if needs_warmup else headless,
        user_data_dir=user_data_dir,
        profile_directory=profile_directory,
    )

    try:
        if needs_warmup:
            ok = await session.warmup(ezproxy_host, warmup_doi)
            if not ok and verbose:
                print("[driver] warmup did not complete; proceeding anyway")

        sem = asyncio.Semaphore(concurrency)
        start_lock = asyncio.Lock() if inter_paper_delay_s > 0 else None
        start_state: dict[str, float] = {}
        tasks = [
            asyncio.create_task(
                _harvest_one(
                    session.context,
                    rec,
                    ezproxy_host,
                    papers_dir,
                    sem,
                    cache,
                    inter_paper_delay_s=inter_paper_delay_s,
                    start_lock=start_lock,
                    start_state=start_state,
                )
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
