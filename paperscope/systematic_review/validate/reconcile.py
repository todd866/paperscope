"""Reconcile a human validation pass back onto the decisions — append-only.

Takes the original decisions (screening.jsonl / extraction.jsonl) and the
human export from the workbook, and produces NEW artefacts. It never mutates
the source decision files: provenance stays append-only, as the rest of the
pipeline does.

Outputs:
- `validation-overrides.jsonl` — one row per human-touched record: the rating
  on each friction dimension, agree/flip, note, and the original decision.
- `requeue.jsonl` — the records the human flipped, ready to feed back into a
  re-screen / re-extract pass (closing the loop, rather than a dead note).
- `validation-summary.json` — counts + agreement rate + per-dimension tallies
  (the calibration readout: where does the AI rater disagree with the human?).
"""

from __future__ import annotations

from paperscope.systematic_review.records import record_id


def reconcile(decisions: list[dict], human_export: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """Return (overrides, requeue). Append-only: inputs are not modified."""
    by_id = {record_id(d): d for d in decisions}
    overrides: list[dict] = []
    requeue: list[dict] = []
    for rid, h in human_export.items():
        orig = by_id.get(rid, {})
        flip = bool(h.get("flip"))
        overrides.append({
            "record_id": rid,
            "human": "flip" if flip else "agree",
            "reviewed": bool(h.get("reviewed")),
            "ratings": h.get("ratings", {}),
            "note": h.get("note", ""),
            "original_decision": orig,
        })
        if flip:
            requeue.append({
                "record_id": rid,
                "reason": "human flip on validation",
                "note": h.get("note", ""),
                "original_decision": orig,
            })
    return overrides, requeue


def summarize(overrides: list[dict]) -> dict:
    """Aggregate overrides into a calibration summary."""
    n = len(overrides)
    reviewed = sum(1 for o in overrides if o.get("reviewed"))
    flipped = sum(1 for o in overrides if o.get("human") == "flip")
    agree = sum(1 for o in overrides if o.get("human") == "agree")
    per_dim: dict[str, dict[str, int]] = {}
    for o in overrides:
        for dim, val in (o.get("ratings") or {}).items():
            per_dim.setdefault(dim, {}).setdefault(str(val), 0)
            per_dim[dim][str(val)] += 1
    return {
        "n_records_touched": n,
        "reviewed": reviewed,
        "flipped": flipped,
        "agreement_rate": (agree / n) if n else None,
        "per_dimension": per_dim,
    }
