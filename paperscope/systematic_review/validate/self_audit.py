"""AI self-audit interface — the model re-examines its own decision and says
where it is genuinely unsure.

Like `screen.ai_screen`, the real model pass belongs to the caller's agent SDK;
this module defines only the *contract*, so the deterministic CLI never embeds
LLM orchestration. A caller runs a `SelfAuditor` over the decisions and writes
the results to a self-audit JSONL, which `validate workbook` then consumes (the
flagged-uncertain items are sorted to the top of the workbook).

The point of the self-audit is the project's core stance: a confident binary
that hides its uncertainty is the failure mode. So instead of asking a human to
rubber-stamp every decision, the model surfaces the calls it itself thinks are
fragile, and the human's attention goes only there.

Output contract, one dict per decision:
    {"record_id": str,
     "confidence": float,        # 0..1; how sure the model is of its own call
     "flag": bool,               # True = "look at this one"
     "reasoning": str,           # why it is or isn't confident
     "dimension": str|None}      # optional: which friction dimension is shaky
"""

from __future__ import annotations

from typing import Protocol

from paperscope.systematic_review.records import record_id
from paperscope.systematic_review.validate.rubric import FrictionRubric


class SelfAuditor(Protocol):
    """Interface any AI self-audit implementation conforms to."""

    def audit_decision(self, decision: dict, record: dict, rubric: FrictionRubric) -> dict:
        """Re-examine one decision and return a self-audit dict (see module docstring)."""
        ...


def stub_self_auditor(decision: dict, record: dict, rubric: FrictionRubric) -> dict:
    """Placeholder that flags everything for review (abstains from a confidence
    judgement). Wire a real SDK call into a function with the same signature."""
    return {
        "record_id": record_id(decision),
        "confidence": 0.0,
        "flag": True,
        "reasoning": "self-auditor not configured — every decision flagged for human review",
        "dimension": None,
    }


def self_audit_corpus(decisions: list[dict], records_by_id: dict[str, dict],
                      rubric: FrictionRubric, auditor=stub_self_auditor) -> list[dict]:
    """Run a `SelfAuditor` over decisions. Deterministic helper; the default
    `auditor` is the stub (caller passes a real SDK-backed one)."""
    out = []
    for d in decisions:
        out.append(auditor(d, records_by_id.get(record_id(d), {}), rubric))
    return out
