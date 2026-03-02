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

## Paperscope Integration

- **Discovery tools** (harvest, embed, query) → feed Opus with raw material
- **Audit tools** (verify, pre_submit, audit_usage) → enable GPT to check output
- **Both systems** can use the bibliography database as ground truth

## What This Looks Like in Practice

```
Morning: Opus drafts a new section connecting paper X to theorem Y
  → Paperscope: harvest to check for recent work on this connection
  → Paperscope: query embedding space for related claims

Afternoon: GPT reviews the section
  → Paperscope: verify all cited DOIs
  → Paperscope: audit citation usage against actual paper content

Evening: Opus revises based on GPT's findings
  → Paperscope: pre-submit check before finalizing
```
