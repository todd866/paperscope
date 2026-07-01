# Workflow: Two-System Methodology

## The Setup

Use two AI systems with complementary strengths:

**System 1 — High-D reasoning (Claude Opus 4.5):**
- Ideation, framework construction, theoretical synthesis
- Navigating conceptual spaces, finding structural analogies
- Generating novel mathematical formalisms
- Writing papers and constructing arguments

**System 2 — Low-D verification (GPT 5.2 Pro):**
- Checking specific claims against literature
- Catching arithmetic and logical errors
- Grounding abstractions in concrete examples
- Finding counterexamples

## When to Use Which

| Task | System | Why |
|------|--------|-----|
| "What's the connection between X and Y?" | Opus | High-D navigation |
| "Is this derivation correct?" | GPT | Error detection |
| "Write the paper" | Opus | Framework construction |
| "Check all citations" | GPT | Systematic verification |
| "What am I missing?" | Both | Opus for blind spots, GPT for facts |

## The Handoff Pattern

1. **Opus generates** a framework, argument, or draft
2. **GPT verifies** specific claims, citations, math
3. **Opus revises** based on GPT's corrections
4. **GPT re-checks** the revision

## PaperScope Integration

- **Discovery tools** (harvest, embed, ingest) → feed Opus with raw material
- **Audit tools** (verify, pre_submit, citation_alignment, critical_read, forensic_stats) → enable GPT to check output
- **Both systems** can use the bibliography database as ground truth

## What This Looks Like in Practice

```
Morning: Opus drafts a new section connecting paper X to theorem Y
  → PaperScope: harvest to check for recent work on this connection
  → PaperScope: analyze for embedding-based gap detection against your literature

Afternoon: GPT reviews the section
  → PaperScope: verify all cited DOIs
  → PaperScope: analyze → citation_alignment flags low-similarity citations
    for manual check against the cited paper's text

Evening: Opus revises based on GPT's findings
  → PaperScope: pre-submit check before finalizing
```
