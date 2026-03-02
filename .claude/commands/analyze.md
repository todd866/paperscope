Analyze a LaTeX paper for citation alignment, novelty, and argument strength.

Find the main .tex file in the current project. If $ARGUMENTS specifies a file, use that instead. Look for a literature directory containing .txt files (check `text/`, `literature/text/`, `literature/`, or `lit/`).

Run:
```
python3 -m paperscope analyze <paper.tex> --literature <literature_dir>
```

After the command completes:

1. **Read the JSON output** and identify the most actionable issues
2. **Citation alignment**: For any citation contexts with alignment below 0.4, read the relevant passage in the .tex file and check whether the citation is genuinely mismatched or just semantically indirect. Suggest specific replacement references if the bibliography contains better matches.
3. **Novelty detection**: For claims flagged as novel (similarity < 0.4), note which ones genuinely need stronger justification vs. which are appropriately novel contributions. Don't flag the paper's own thesis as a problem.
4. **Strength heatmap**: Identify the weakest paragraphs (citation support < 0.3) and suggest whether they need a citation, a literature connection, or are fine as-is (e.g., methodology descriptions don't need citations).
5. **Present a summary** with:
   - Top-3 citation alignment issues (with line numbers and suggested fixes)
   - Claims that need stronger justification
   - Weak paragraphs that would benefit from additional support
   - An overall assessment of paper readiness

If the literature directory is missing or empty, say so and suggest running `python3 -m paperscope ingest` first.
