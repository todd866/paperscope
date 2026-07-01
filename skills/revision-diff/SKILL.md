---
name: revision-diff
description: Semantic diff between two versions of a paper. Use when comparing paper revisions, checking whether changes addressed reviewer concerns, or measuring how much a manuscript changed between versions.
user-invocable: true
argument-hint: "old.tex new.tex"
---

# Revision Diff

Measure semantic changes between two versions of a paper.

## When to use this skill

- After revising a paper to address reviewer feedback
- To verify that changes addressed specific concerns
- When comparing draft versions

## Process

1. $ARGUMENTS should specify the old and new .tex files. If not provided, look for files named with version indicators (v1, old, original, revised) or ask.

2. Look for a literature directory (check `text/`, `literature/text/`, `literature/`, `lit/`).

3. Run the diff:
```bash
python3 -m paperscope revision-diff <old.tex> <new.tex> --literature <literature_dir>
```

If no literature directory exists, omit `--literature`.

4. Read the JSON output showing per-section semantic shifts.

5. Identify sections that changed most, ranked by magnitude.

6. For each major change, explain the direction: did the revision move toward or away from the literature?

7. If reviewer comments are available, assess whether each change addresses the concern.

8. Flag regressions: sections that moved away from literature support without good reason.

9. Summarize: sections improved, sections unchanged, sections needing more work.
