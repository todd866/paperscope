Check whether the abstract covers all major sections of the paper.

Find the main .tex file in the current project. If $ARGUMENTS specifies a file, use that instead.

Run:
```
python3 -m paperscope abstract-check <paper.tex>
```

After the command completes:

1. **Read the JSON output** showing per-section similarity to the abstract
2. **Identify underrepresented sections** — any section with below-median similarity to the abstract
3. **For each underrepresented section**, read that section of the .tex file and draft a 1-sentence addition to the abstract that would cover it
4. **Present suggestions** as concrete edits: "Add to abstract: [sentence]" with the specific location in the abstract where it fits best
5. **Check abstract length** — if adding coverage would make it too long (>250 words for most journals), suggest what to trim

Keep suggestions minimal. The goal is coverage, not rewriting the abstract.
