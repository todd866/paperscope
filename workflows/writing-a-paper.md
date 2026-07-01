# Workflow: Writing a Paper

## Before Writing

1. **Extract citations** from any related papers you've already written:
   ```bash
   python3 -m paperscope extract /path/to/your/project
   ```

2. **Harvest recent literature** to check for new relevant work:
   ```bash
   python3 -m paperscope harvest
   ```

3. **Find related work** you may have missed:
   ```bash
   python3 -m paperscope related your_draft.tex
   ```
   Queries OpenAlex for papers semantically near your draft's claims that aren't yet in your bibliography.

## During Writing

- Use bibliography.json as ground truth for citation metadata
- When adding a new citation, check if it's already in the database
- Run pre-submit checks periodically to catch issues early

## Before Submission

1. **Run pre-submission checks**:
   ```bash
   python3 -m paperscope pre-submit your_paper.tex --bib /path/to/bibliography.json
   ```

2. **Resolve any missing DOIs**:
   ```bash
   python3 -m paperscope resolve /path/to/bibliography.json
   ```

3. **Verify DOIs** are correctly matched:
   ```bash
   python3 -m paperscope verify /path/to/bibliography.json
   ```

4. **Run the analysis suite** — `analyze` runs citation alignment + novelty + strength heatmap in one pass. Anything below the alignment / novelty / support thresholds is worth a manual look against the source paper before submitting:
   ```bash
   python3 -m paperscope analyze your_paper.tex --literature text/
   ```
