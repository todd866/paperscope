# Validate — human-in-the-loop adjudication of AI decisions

The systematic-review pipeline is `search → screen → extract → synthesise`, where `screen` and `extract` are AI-made. `validate` is the missing step between those AI decisions and trusting them: it turns the model's own uncertainty into a human work queue.

## Why this and not an accuracy/kappa layer

A second-rater "accuracy" pass treats validation as a credential ("a human looked at it"). But human screeners rubber-stamp too, so the credential is not evidence. The useful product is different: the AI **self-audits** — surfaces the specific decisions it itself thinks are fragile — and the human adjudicates **only those**, with disagreements reconciled back as work, not notes.

Naming: the *command* is `validate` (the user-facing action); the *method* is an **AI-assisted uncertainty audit plus human adjudication of flagged decisions**, not independent verification. Keep that distinction in any write-up.

## Design constraints

- **SDK-agnostic + deterministic core.** The model self-audit pass runs *outside* the CLI (like `screen`/`extract`); `self_audit.py` defines only the `SelfAuditor` contract. `validate workbook` consumes a precomputed self-audit JSONL.
- **Append-only provenance.** Reconcile never mutates `screening.jsonl`/`extraction.jsonl`; it writes new `validation-overrides.jsonl`, `requeue.jsonl`, `validation-summary.json`.
- **Generic `record_id`** (falls back to `pmid`/`id`) — not MEDLINE/PMID-bound.
- **Local source first.** Workbook context comes from the local corpus (`records.jsonl` abstracts); `--include-fulltext` backfills open-access abstracts from Europe PMC only. Paywalled full text is never embedded by default.

## Pipeline

```bash
# 1. (your agent SDK) run a SelfAuditor over the decisions -> screening-self-audit.jsonl
#    one {record_id, confidence, flag, reasoning} per decision

# 2. build the scroll-through workbook (AI-flagged decisions sort to the top)
python -m paperscope.systematic_review validate workbook \
  --decisions screening.jsonl --self-audit screening-self-audit.jsonl \
  --rubric validation-rubric.yaml --records records.jsonl \
  --out validation-workbook.html

# 3. (human) rate the friction dimensions, flip+note disagreements, Copy review (JSON) -> export.json

# 4. reconcile (append-only)
python -m paperscope.systematic_review validate reconcile \
  --decisions screening.jsonl --human-export export.json \
  --out validation-overrides.jsonl --requeue requeue.jsonl

# 5. calibration summary (agreement rate, per-dimension tallies)
python -m paperscope.systematic_review validate summary \
  --validation validation-overrides.jsonl --out validation-summary.json

# 6. feed requeue.jsonl back into a re-screen / re-extract pass
```

## The friction rubric

A small YAML naming the dimensions a human rates — the generalisation of "rate different friction points" (eligibility, extraction fidelity, claimed-vs-supported task, comparator realism, ...):

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

Quote scale values (`"yes"`/`"no"`) — YAML 1.1 parses bare `yes`/`no` as booleans (the loader coerces them defensively anyway). Omit the rubric and a generic agree/flag pass is used.

## Provenance

The pattern was prototyped on a real review's AI-screening QC: rather than human-rubber-stamping an AI eligibility screen, the decisions were re-examined for self-flagged uncertainty, and disputable headline tags were reported as ranges instead of fixed counts. `validate` is the generalised version.
