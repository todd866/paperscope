---
name: cite-check
description: Verify citation DOIs and reference metadata in a LaTeX paper. Use when checking bibliography accuracy, resolving missing DOIs, validating references before submission, or cleaning up a .bib file.
user-invocable: true
argument-hint: "[path/to/paper/]"
---

# Citation Verification

Check that all references have valid DOIs and correct metadata.

## When to use this skill

- Before submission to verify bibliography accuracy
- After adding new references
- When a user asks to clean up or check their .bib file

## Process

1. Find the .bib file(s) in the current project. If $ARGUMENTS specifies a path, use that.

2. Extract citations:
```bash
python3 -m paperscope extract <path>
```

3. Verify DOIs against CrossRef metadata:
```bash
python3 -m paperscope verify bibliography.json
```

4. Report DOI coverage: how many references have DOIs vs. missing.

5. Flag verification failures: references where DOI metadata doesn't match the .bib entry (wrong title, wrong year, wrong authors).

6. For missing DOIs, run:
```bash
python3 -m paperscope resolve bibliography.json
```

7. Present a fix list with specific edits to the .bib file.

8. Check for duplicates: references under different cite keys that are the same paper.

If the bibliography is clean, say so. Don't invent problems.
