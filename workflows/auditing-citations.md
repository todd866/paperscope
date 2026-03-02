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

4. **Acquire paper texts** — download OA papers and extract text for cited works.

5. **Run citation audit** — for each citation in your manuscript, compare the claimed use against the actual paper content.

## What to Look For

- **Ghost citations**: Papers cited that don't exist (DOI resolves to nothing)
- **Misattributed claims**: Paper exists but doesn't say what you cited it for
- **Retracted papers**: Cited work has been retracted
- **Year/title mismatches**: You may be conflating two different papers
