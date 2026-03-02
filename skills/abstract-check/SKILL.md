---
name: abstract-check
description: Check whether a paper's abstract covers all major sections. Use when finalizing a paper for submission, reviewing abstract completeness, or checking abstract-body alignment in a LaTeX manuscript.
user-invocable: true
argument-hint: "[paper.tex]"
---

# Abstract Coverage Check

Verify that the abstract represents all major sections of the paper.

## When to use this skill

- Before submission to ensure the abstract is complete
- After major revisions that changed paper structure
- When a user asks about abstract quality or coverage

## Process

1. Find the main .tex file. If $ARGUMENTS specifies a file, use that.

2. Run the check:
```bash
python3 -m paperscope abstract-check <paper.tex>
```

3. Read the JSON output showing per-section similarity to the abstract.

4. For each underrepresented section (below-median similarity), read that section of the .tex file and draft a 1-sentence addition to the abstract that would cover it.

5. Present suggestions as concrete edits: "Add to abstract: [sentence]" with the specific location in the abstract where it fits best.

6. Check abstract length. If adding coverage would exceed ~250 words, suggest what to trim.

Keep suggestions minimal. The goal is coverage, not rewriting the abstract.
