---
name: analyze
description: Analyze an academic paper for citation alignment, novelty, and argument strength. Use when reviewing a LaTeX paper, checking whether citations support claims, identifying novel contributions, finding weak arguments, or preparing a manuscript for submission.
user-invocable: true
argument-hint: "[paper.tex]"
---

# Paper Analysis

Analyze a LaTeX paper for citation alignment, novelty detection, and argument strength.

## When to use this skill

- After drafting or revising a paper
- Before submission to check citation quality
- When a user asks to review, check, or analyze a paper
- When working on a .tex file and the user asks about citation quality or argument strength

## Process

1. Find the main .tex file. If $ARGUMENTS specifies a file, use that. Otherwise search for .tex files in the current directory.

2. Find the literature directory containing .txt files extracted from reference papers. Check these locations in order: `text/`, `literature/text/`, `literature/`, `lit/`. If none found, tell the user and suggest running `python3 -m paperscope ingest` first.

3. Run the analysis:
```bash
python3 -m paperscope analyze <paper.tex> --literature <literature_dir>
```

4. Read the JSON output and identify the most actionable issues.

5. For **citation alignment issues** (alignment below 0.4): read the relevant passage in the .tex file and check whether the citation is genuinely mismatched or just semantically indirect. Suggest specific replacement references if the bibliography contains better matches.

6. For **novel claims** (similarity < 0.4): note which ones genuinely need stronger justification vs. which are appropriately novel contributions. The paper's main thesis being novel is expected, not a problem.

7. For **weak paragraphs** (citation support < 0.3): suggest whether they need a citation, a literature connection, or are fine as-is. Methodology descriptions and transitions don't need citations.

8. Present a summary:
   - Top citation alignment issues with line numbers and suggested fixes
   - Claims that need stronger justification
   - Weak paragraphs that would benefit from support
   - Overall assessment of paper readiness
