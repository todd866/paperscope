---
name: related
description: Find missing related work for a paper. Use when checking bibliography completeness, searching for papers to cite, or identifying gaps in a literature review before submission.
user-invocable: true
argument-hint: "[paper.tex]"
---

# Related Work Radar

Find papers semantically similar to yours that aren't in your bibliography.

## When to use this skill

- Before submission to catch missing related work
- When a reviewer says "you missed relevant literature"
- When building or expanding a literature review

## Process

1. Find the main .tex file. If $ARGUMENTS specifies a file, use that.

2. Run the search:
```bash
python3 -m paperscope related <paper.tex>
```

This searches OpenAlex for semantically similar papers not in your bibliography. Requires PAPERSCOPE_EMAIL environment variable.

3. Read the JSON output with ranked missing references.

4. Filter for genuinely relevant papers. Remove false positives (similar keywords but different domains).

5. For each relevant missing reference, explain:
   - What it's about (1 sentence)
   - Why it's relevant to this paper
   - Where in the paper it should be cited
   - Whether it supports, contradicts, or extends the claims

6. Draft BibTeX entries for the top 3-5 missing references.

7. Suggest specific citation sentences that could be added to the .tex file.

Present results as a prioritized list, most important first.
