---
name: validate
description: Human-in-the-loop validation of AI screening/extraction decisions for a systematic review. Use when an AI screen or extraction pass needs author review without rubber-stamping — it surfaces the model's own low-confidence calls, builds a scroll-through workbook, and reconciles human flips into an append-only re-queue.
user-invocable: true
argument-hint: "[corpus-dir]"
---

# Validate AI decisions (uncertainty audit + human adjudication)

Turn AI screening/extraction decisions into a work queue. The model self-flags the calls it thinks are fragile, a human adjudicates only those, and disagreements are reconciled back append-only. The method is an **AI-assisted uncertainty audit plus human adjudication of flagged decisions** — not independent verification, and not a "a human looked at it" credential.

## When to use this skill

- After an AI screen (`screening.jsonl`) or extraction (`extraction.jsonl`) pass, before relying on the decisions.
- When a reviewer wants to validate AI decisions without ticking every box — attention should go to the genuinely-uncertain ones.
- To produce a defensible record ("author reviewed the AI-flagged decisions") plus a re-queue of the disagreements.

## Process

1. **Self-audit (the model pass, outside the deterministic CLI).** Run a `SelfAuditor` (see `paperscope/systematic_review/validate/self_audit.py` for the contract) over the decisions with your agent SDK, producing a self-audit JSONL: one `{record_id, confidence, flag, reasoning}` per decision. (Without this, all decisions show unflagged — still usable, just not prioritised.)

2. **Build the workbook:**
   ```bash
   python3 -m paperscope.systematic_review validate workbook \
     --decisions screening.jsonl \
     --self-audit screening-self-audit.jsonl \
     --rubric validation-rubric.yaml \
     --records records.jsonl \
     --out validation-workbook.html
   ```
   A self-contained HTML file: one card per decision, AI-flagged ones at the top, the decision + the model's reasoning + the local source abstract flattened inline, with a rater per friction dimension.

3. **Adjudicate.** Open the workbook, rate the friction dimensions, tick **reviewed** when you agree, **flip / disagree** + a note when you would change the decision. State persists in the browser. Hit **Copy review (JSON)** and save it (e.g. `export.json`).

4. **Reconcile (append-only):**
   ```bash
   python3 -m paperscope.systematic_review validate reconcile \
     --decisions screening.jsonl --human-export export.json \
     --out validation-overrides.jsonl --requeue requeue.jsonl
   ```

5. **Summary (the calibration readout):**
   ```bash
   python3 -m paperscope.systematic_review validate summary \
     --validation validation-overrides.jsonl --out validation-summary.json
   ```

6. **Close the loop.** Feed `requeue.jsonl` back into a re-screen / re-extract pass.

## The friction rubric (`validation-rubric.yaml`)

```yaml
dimensions:
  - id: eligible
    label: Eligibility correct?
    question: AI/ML diagnostic or surveillance tool, human data, discrimination metric?
    scale: ["yes", "no", "unsure"]
  - id: extraction
    label: Extraction faithful?
    question: Does the recorded operating point match the source?
    scale: ["yes", "no", "unsure"]
```
Quote scale values (`"yes"`, `"no"`) — YAML parses bare `yes`/`no` as booleans. If omitted, a generic agree/flag rubric is used.

## Notes

- **Append-only**: never mutates `screening.jsonl` / `extraction.jsonl`; reconcile writes new `validation-overrides.jsonl`, `requeue.jsonl`, `validation-summary.json`.
- **Generic `record_id`** (falls back to `pmid`/`id`) — works for non-MEDLINE sources.
- **Source context is local-first**; `--include-fulltext` backfills open-access abstracts only (never paywalled full text).
