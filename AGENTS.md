# Paperscope — Codex Instructions

When working on LaTeX papers (.tex files), you have access to paperscope analysis tools via the CLI. Use them proactively when relevant.

## When to run analysis

- **After drafting or revising a paper**: run `analyze` to check citations, novelty, and argument strength
- **Before submission**: run `abstract-check` to verify coverage, `cite-check` to verify references
- **When choosing journals**: run `journal-fit` with candidate journal names
- **After revision**: run `revision-diff` to verify changes addressed concerns
- **When reviewing bibliography**: run `related` to find missing related work

## Commands

```bash
# Full analysis: citation alignment, novelty, strength heatmap
python3 -m paperscope analyze paper.tex --literature text/

# Abstract coverage check
python3 -m paperscope abstract-check paper.tex

# Journal semantic fit ranking
python3 -m paperscope journal-fit paper.tex -j "Journal Name 1" "Journal Name 2"

# Semantic diff between revisions
python3 -m paperscope revision-diff old.tex new.tex --literature text/

# Find missing related work (requires PAPERSCOPE_EMAIL env var)
python3 -m paperscope related paper.tex

# Citation verification pipeline
python3 -m paperscope extract .
python3 -m paperscope verify bibliography.json
python3 -m paperscope resolve bibliography.json
```

## Interpreting output

All commands produce JSON output. After running a command:

1. **Citation alignment**: Flag contexts with alignment below 0.4. Check whether the citation is genuinely wrong or just semantically indirect. Suggest replacement references from the bibliography.
2. **Novelty detection**: Claims with max literature similarity below 0.4 are novel. The paper's thesis being novel is expected — flag claims that are novel but lack justification.
3. **Strength heatmap**: Paragraphs with citation support below 0.3 may need references. Methodology and transition paragraphs are exceptions.
4. **Abstract check**: Sections with below-median similarity to the abstract are underrepresented. Suggest specific 1-sentence additions.

## Literature directory

Analysis commands need a directory of .txt files extracted from reference papers. Check for: `text/`, `literature/text/`, `literature/`, `lit/`. If missing, suggest running `python3 -m paperscope ingest` first.
