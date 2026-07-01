"""Persistent learning store for the browser-driven harvester.

After every harvest attempt the driver records outcomes here. On the
next run, the cache lets us:

  - Skip DOIs we've conclusively failed on (e.g. Sydney isn't subscribed
    to Seminars in Neurology → don't waste a browser navigation).
  - Skip publishers known to need headed-with-human mode (e.g. live
    Cloudflare challenges) when running headless.
  - Track which adapter strategies actually work per publisher, so a
    future smarter ordering pass can prioritise high-yield strategies.

Schema (`<corpus_dir>/.paperscope/strategy-cache.json`):

```
{
  "version": 1,
  "doi_overrides": {
    "10.1055/s-2001-15263": {
      "permanent_outcome": "publisher_no_access",
      "evidence": "Thieme: type=auth_denied",
      "last_seen": "2026-05-15T...",
      "skip_next_run": true
    }
  },
  "publisher_health": {
    "neurology.org": {
      "consecutive_cloudflare": 3,
      "last_success_ts": null,
      "needs_headed": true
    },
    "jamanetwork.com": {
      "successful_strategies": {
        "JAMA: a[href*='articlepdf']": {"hits": 12, "last": "..."},
      }
    }
  },
  "stats": {"total_attempts": 87, "total_success": 25}
}
```

The cache is a *hint*, not authority. The driver still attempts a DOI
even if cached as failed unless `--respect-cache` is set.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import json
import os
from pathlib import Path
from typing import Optional


SCHEMA_VERSION = 1
DEFAULT_CACHE_PATH = ".paperscope/strategy-cache.json"


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclasses.dataclass
class CacheVerdict:
    """What the cache says about a particular paper before we try it."""
    should_skip: bool = False
    reason: str = ""
    expected_outcome: str = ""
    publisher_hint: str = ""  # e.g. "needs-headed", "ok-for-headless"


class StrategyCache:
    """JSON-backed strategy cache. Cheap, no DB.

    Reads on construction, writes on `save()` (called by the driver after
    each batch). Concurrent runs are not supported — last writer wins. The
    cache file is per-corpus so different reviews don't collide.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> dict:
        if not self.path.exists():
            return {
                "version": SCHEMA_VERSION,
                "doi_overrides": {},
                "publisher_health": {},
                "stats": {"total_attempts": 0, "total_success": 0},
            }
        try:
            data = json.loads(self.path.read_text())
            data.setdefault("doi_overrides", {})
            data.setdefault("publisher_health", {})
            data.setdefault("stats", {"total_attempts": 0, "total_success": 0})
            return data
        except Exception:
            # Corrupt cache — start fresh, don't crash the run.
            return {
                "version": SCHEMA_VERSION,
                "doi_overrides": {},
                "publisher_health": {},
                "stats": {"total_attempts": 0, "total_success": 0},
            }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: temp file + rename.
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))
        os.replace(tmp, self.path)

    # -----------------------------------------------------------------
    # Lookups
    # -----------------------------------------------------------------

    def consult(self, doi: str, publisher_domain: str = "", respect_cache: bool = True) -> CacheVerdict:
        verdict = CacheVerdict()
        override = self.data["doi_overrides"].get(doi)
        if override and respect_cache and override.get("skip_next_run"):
            verdict.should_skip = True
            verdict.reason = override.get("evidence", "cached as failed")
            verdict.expected_outcome = override.get("permanent_outcome", "")
            return verdict

        health = self.data["publisher_health"].get(publisher_domain or "")
        if health and health.get("needs_headed"):
            verdict.publisher_hint = "needs-headed"
        return verdict

    # -----------------------------------------------------------------
    # Updates from outcomes
    # -----------------------------------------------------------------

    def note_attempt(
        self,
        doi: str,
        outcome: str,
        adapter: str,
        publisher_domain: str = "",
        strategy_name: str = "",
        evidence: str = "",
    ) -> None:
        self.data["stats"]["total_attempts"] += 1
        if outcome == "success":
            self.data["stats"]["total_success"] += 1
            # Clear any prior override
            self.data["doi_overrides"].pop(doi, None)
            ph = self.data["publisher_health"].setdefault(publisher_domain or adapter, {})
            ph["last_success_ts"] = _utc_now()
            ph["consecutive_cloudflare"] = 0
            ph["needs_headed"] = False
            if strategy_name:
                strats = ph.setdefault("successful_strategies", {})
                s = strats.setdefault(strategy_name, {"hits": 0, "last": None})
                s["hits"] += 1
                s["last"] = _utc_now()
            return

        # Non-success
        ph = self.data["publisher_health"].setdefault(publisher_domain or adapter, {})
        if outcome == "cloudflare_challenge":
            ph["consecutive_cloudflare"] = (ph.get("consecutive_cloudflare", 0) or 0) + 1
            if ph["consecutive_cloudflare"] >= 2:
                ph["needs_headed"] = True

        if outcome in ("publisher_no_access", "paywall_unauth"):
            # Mark this DOI permanently
            self.data["doi_overrides"][doi] = {
                "permanent_outcome": outcome,
                "evidence": evidence or f"adapter={adapter} reported {outcome}",
                "last_seen": _utc_now(),
                "skip_next_run": True,
            }

    # -----------------------------------------------------------------
    # Reporting
    # -----------------------------------------------------------------

    def summary(self) -> str:
        s = self.data["stats"]
        n_overrides = len(self.data["doi_overrides"])
        n_pubs = len(self.data["publisher_health"])
        return (
            f"strategy cache: {s['total_success']}/{s['total_attempts']} attempts succeeded "
            f"({n_overrides} DOI-specific skips, {n_pubs} publisher health entries)"
        )
