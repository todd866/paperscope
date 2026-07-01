"""Human-in-the-loop validation: turn AI screening/extraction decisions into a
work queue, by surfacing the model's own low-confidence calls for adjudication.

This is the transparency layer the pipeline lacked: `screen` and `extract` are
AI-made, and `validate` lets a human review them *without* the review being a
rubber-stamp. The AI self-audits (flags the decisions it itself thinks are
fragile), the human adjudicates the flagged subset, and disagreements are
reconciled into append-only artefacts plus a re-queue.

Naming note: the *command* is `validate` because that is the user-facing action
("validate these decisions"); the *method* is an AI-assisted uncertainty audit
plus human adjudication of flagged decisions, not independent verification.

Pieces (kept SDK-agnostic and deterministic, like `screen`/`extract`):
- `rubric`      — the friction-point rubric (the dimensions a human rates).
- `self_audit`  — the `SelfAuditor` Protocol; the model pass runs outside the CLI.
- `workbook`    — decisions + self-audit + rubric + records -> scroll-through HTML.
- `reconcile`   — human export -> validation-overrides / requeue / summary (append-only).
"""

from __future__ import annotations

from paperscope.systematic_review.validate.rubric import FrictionRubric, load_friction_rubric
from paperscope.systematic_review.validate.self_audit import SelfAuditor, stub_self_auditor
from paperscope.systematic_review.validate.workbook import build_workbook
from paperscope.systematic_review.validate.reconcile import reconcile, summarize

__all__ = [
    "FrictionRubric",
    "load_friction_rubric",
    "SelfAuditor",
    "stub_self_auditor",
    "build_workbook",
    "reconcile",
    "summarize",
]
