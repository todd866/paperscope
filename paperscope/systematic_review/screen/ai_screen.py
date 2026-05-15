"""AI-agent screening interface.

The full implementation belongs to the caller's agent SDK (Anthropic, OpenAI,
etc.); this module defines the *contract*: given a record + a rubric, produce a
decision dict with `decision`, `themes`, `reason`. The MND pilot ran this with
parallel Claude agents — that orchestration is intentionally out of scope here
so this module stays SDK-agnostic.

To wire up against the Anthropic SDK, implement `screen_record` to:
  1. Build a prompt from the rubric (the rubric's markdown is the prompt body)
  2. Send the record's title + abstract to Claude
  3. Parse the JSONL response per the rubric's output format
  4. Return the dict
"""

from __future__ import annotations

from typing import Callable, Protocol

from paperscope.systematic_review.screen.rubric import Rubric


class Screener(Protocol):
    """Interface any AI-screen implementation conforms to."""

    def screen_record(self, record: dict, rubric: Rubric) -> dict:
        """Return {"pmid": str, "decision": "include|exclude|maybe",
        "themes": list[str], "reason": str}."""
        ...


def stub_screener(record: dict, rubric: Rubric) -> dict:
    """Placeholder that abstains. Wire your real SDK call into a function with
    the same signature and pass it to `screen_corpus`."""
    return {
        "pmid": record.get("pmid", ""),
        "decision": "maybe",
        "themes": [],
        "reason": "AI screener not configured — record needs manual screening",
    }


def screen_corpus(
    records: list[dict],
    rubric: Rubric,
    screener: Callable[[dict, Rubric], dict] = stub_screener,
) -> list[dict]:
    """Apply `screener` to every record. Each screener call is independent —
    parallel agent dispatch belongs to the caller; this stays serial."""
    return [screener(r, rubric) for r in records]
