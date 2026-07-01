# Workflow: Auditing Citations

## Why Audit

AI-assisted writing has a specific failure mode: citing real papers for claims they don't make. This workflow catches that before reviewers do.

## Steps

1. **Extract all citations** from your manuscript:
   ```bash
   python3 -m paperscope extract /path/to/project
   ```

2. **Resolve DOIs** for all references:
   ```bash
   python3 -m paperscope resolve literature/bibliography.json
   ```

3. **Verify DOIs** against CrossRef:
   ```bash
   python3 -m paperscope verify literature/bibliography.json
   ```
   This catches: title mismatches, year discrepancies, retracted papers.

4. **Acquire paper texts** — download OA papers and extract text for cited works:
   ```bash
   python3 -m paperscope ingest /path/to/literature/
   ```

5. **Check citation alignment** — for each citation context, compare it semantically against the cited paper's content:
   ```bash
   python3 -m paperscope analyze your_paper.tex --literature literature/text/
   ```
   The `citation_alignment` block flags citations whose context is semantically distant from anything in the cited paper. Low scores are candidates for misattribution; check those by hand.

6. **Pre-submit checklist** — final pass over the bibliography:
   ```bash
   python3 -m paperscope pre-submit your_paper.tex --bib literature/bibliography.json
   ```

## What to Look For

- **Ghost citations**: Papers cited that don't exist (DOI resolves to nothing)
- **Misattributed claims**: Paper exists but doesn't say what you cited it for
- **Retracted papers**: Cited work has been retracted
- **Year/title mismatches**: You may be conflating two different papers
