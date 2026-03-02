---
name: journal-fit
description: Rank journals by semantic similarity to a paper. Use when choosing where to submit a paper, comparing journal fit, or deciding between target venues for an academic manuscript.
user-invocable: true
argument-hint: "[paper.tex] -j Journal1 Journal2"
---

# Journal Targeting

Rank candidate journals by semantic similarity to your paper.

## When to use this skill

- When deciding where to submit a paper
- When a user asks which journal fits their work
- After a rejection, to find better-fit venues

## Process

1. Find the main .tex file. If $ARGUMENTS specifies a file and journals, use those. Otherwise ask which journals to compare against.

2. Run the analysis:
```bash
python3 -m paperscope journal-fit <paper.tex> -j <journal1> <journal2> ...
```

This queries OpenAlex for recent abstracts from each journal and compares them to the paper. Requires the PAPERSCOPE_EMAIL environment variable.

3. Read the JSON output with per-journal similarity scores.

4. Rank journals from best to worst fit with similarity scores.

5. For the top journal, explain which sections align most strongly.

6. For poor-fit journals (similarity < 0.3), explain why.

7. Suggest 1-2 additional journals to check if results suggest the initial list isn't ideal.

Present results as a ranked table: journal name, similarity score, brief note on fit.
