"""Browser session and cookie persistence for institutional access.

The first run of `browser_driver.harvest` launches Chromium in headed mode
and navigates to the institution's EZProxy login URL. The user clicks
through OpenAthens / SAML once; we then dump the storage state (cookies,
localStorage) to disk. Subsequent runs reuse that state, so the entire
queue can run headless once the session is warm.

Storage state file lives at
`<corpus_dir>/.paperscope/session-state.json` by default. Treat as
private — it contains live institutional auth cookies.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Playwright


DEFAULT_STATE_PATH = Path(".paperscope/session-state.json")
SESSION_TEST_URL_TEMPLATE = "https://doi-org.{ezproxy_host}/{test_doi}"
# Pick a DOI known to be OA so we can verify the session without burning
# an institutional read. Empty string = skip the verification call.
SESSION_TEST_DOI = "10.1371/journal.pone.0000000"


class Session:
    """Wraps a Playwright BrowserContext with persistent storage state.

    Three construction paths:
      - `Session.warmup(state_path, ezproxy_host)` opens a visible browser
        with a clean profile and waits for the user to complete
        institutional login. On exit, the state is dumped to `state_path`
        for subsequent reuse.
      - Default `.open()` reuses a previously-dumped state.
      - `.open(user_data_dir=...)` uses `launch_persistent_context` against
        a real Chrome profile — cookies, saved passwords, extensions, and
        any live OpenAthens session are all available. Chrome must not be
        running with that profile at the time of launch.
    """

    def __init__(self, state_path: Path):
        self.state_path = Path(state_path)
        self._pw: Optional["Playwright"] = None
        self._browser = None
        self.context: Optional["BrowserContext"] = None
        self._is_persistent = False

    @staticmethod
    def state_exists(state_path: Path) -> bool:
        p = Path(state_path)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text())
            return bool(data.get("cookies"))
        except Exception:
            return False

    async def open(
        self,
        *,
        headless: bool = False,
        use_existing_state: bool = True,
        accept_downloads: bool = True,
        user_data_dir: Optional[str] = None,
        profile_directory: Optional[str] = None,
    ) -> "BrowserContext":
        """Launch Chrome and return a usable BrowserContext.

        If `user_data_dir` is set, uses `launch_persistent_context` against
        that profile path — cookies, saved passwords, and extensions all
        come along. Chrome must not be running with that profile already;
        Playwright will refuse to share the lock.

        Otherwise, launches a fresh Chrome and (optionally) layers in a
        previously-dumped storage state.
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise RuntimeError(
                "browser-harvest requires playwright: "
                "pip install playwright && playwright install chromium"
            ) from e

        self._pw = await async_playwright().start()

        context_kwargs = {
            "accept_downloads": accept_downloads,
            "viewport": {"width": 1280, "height": 900},
            # A real-Chrome user-agent helps publisher bot detection treat
            # us as a regular human visitor.
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
        }

        if user_data_dir:
            self._is_persistent = True
            launch_kwargs = {
                "user_data_dir": user_data_dir,
                "headless": headless,
                **context_kwargs,
            }
            # Pin profile-directory if asked (e.g. "Default", "Profile 1").
            if profile_directory:
                launch_kwargs["args"] = [f"--profile-directory={profile_directory}"]
            try:
                self.context = await self._pw.chromium.launch_persistent_context(
                    channel="chrome", **launch_kwargs
                )
            except Exception:
                self.context = await self._pw.chromium.launch_persistent_context(
                    **launch_kwargs
                )
            # The persistent context owns its own browser; we don't track _browser.
            return self.context

        # Prefer real Chrome over Chromium for Cloudflare-tolerance.
        # Falls through to bundled Chromium if Chrome isn't installed.
        try:
            self._browser = await self._pw.chromium.launch(
                headless=headless, channel="chrome"
            )
        except Exception:
            self._browser = await self._pw.chromium.launch(headless=headless)

        storage_state = None
        if use_existing_state and self.state_exists(self.state_path):
            storage_state = str(self.state_path)

        if storage_state:
            context_kwargs["storage_state"] = storage_state
        self.context = await self._browser.new_context(**context_kwargs)
        return self.context

    async def dump_state(self) -> None:
        if not self.context or self._is_persistent:
            # Persistent contexts write their own profile dir; no separate dump.
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        await self.context.storage_state(path=str(self.state_path))

    async def close(self, *, save_state: bool = True) -> None:
        try:
            if save_state and self.context and not self._is_persistent:
                await self.dump_state()
        finally:
            if self.context:
                await self.context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()

    # ---------------------------------------------------------------
    # Warmup flow
    # ---------------------------------------------------------------

    async def warmup(
        self,
        ezproxy_host: str,
        warmup_doi: str,
        timeout_minutes: int = 5,
    ) -> bool:
        """Open a visible browser to `https://doi-org.<ezproxy_host>/<doi>`
        and wait until the page lands on the publisher's article page
        (i.e. session is warm). Returns True on success.

        Polls every second up to `timeout_minutes`; if the URL hasn't left
        the openathens/login/idp domains, prints a hint and keeps waiting.
        """
        if not self.context:
            raise RuntimeError("call .open(headless=False) before .warmup()")
        page = await self.context.new_page()
        url = f"https://doi-org.{ezproxy_host}/{warmup_doi}"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        print(f"[session] warmup navigated to {url}")
        print(f"[session] complete institutional login if prompted; will wait up to {timeout_minutes} min...")

        deadline = time.time() + timeout_minutes * 60
        last_url = page.url
        while time.time() < deadline:
            current = page.url
            if current != last_url:
                print(f"[session] redirected → {current[:100]}")
                last_url = current
            if _looks_authenticated(current):
                print(f"[session] session warm: landed on {current[:100]}")
                await self.dump_state()
                await page.close()
                return True
            await asyncio.sleep(1.5)
        print("[session] warmup timeout — session may not be fully warm")
        await page.close()
        return False


def _looks_authenticated(url: str) -> bool:
    """Heuristic: we're on a real publisher page (not an SSO redirector)."""
    if not url:
        return False
    u = url.lower()
    sso_hosts = (
        "openathens",
        "login.",
        "idp.",
        "shibauth",
        "saml",
        "go.openathens.net",
        "connect.openathens.net",
    )
    if any(host in u for host in sso_hosts):
        return False
    # Common publisher domain markers
    publisher_markers = (
        "jamanetwork.com",
        "sciencedirect.com",
        "linkinghub.elsevier.com",
        "onlinelibrary.wiley.com",
        "tandfonline.com",
        "link.springer.com",
        "scielo.br",
        "karger.com",
        "thieme-connect.de",
        "neurology.org",
        "journals.lww.com",
        "/doi/",
        "/article/",
        "/abstract/",
        "/full/",
        "/pdf/",
    )
    return any(marker in u for marker in publisher_markers)
