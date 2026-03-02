Semantic diff between two versions of a paper.

$ARGUMENTS should specify the old and new .tex files. If not provided, look for files named with version indicators (e.g., `v1`, `old`, `original`, `revised`) or ask which files to compare.

Look for a literature directory containing .txt files (check `text/`, `literature/text/`, `literature/`, or `lit/`).

Run:
```
python3 -m paperscope revision-diff <old.tex> <new.tex> --literature <literature_dir>
```

If no literature directory exists, omit the `--literature` flag.

After the command completes:

1. **Read the JSON output** showing per-section semantic shifts
2. **Identify the sections that changed most** — present as a ranked list with magnitude
3. **For each major change**, explain the direction: did the revision move the paper toward or away from the literature?
4. **If reviewer comments are available** (check for a reviewer response file or ask), assess whether each change addresses the reviewer's concern
5. **Flag any regressions** — sections that got weaker (moved away from literature support without good reason)
6. **Summarize** with: sections improved, sections unchanged, sections that may need more work
