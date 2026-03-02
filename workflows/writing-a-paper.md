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

3. **Query the embedding space** (if built) for papers related to your topic:
   ```bash
   # In Python
   from paperscope.embed.query import find_gaps
   result = find_gaps("your claim here", embeddings, index)
   ```

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

4. **Audit citation usage** — compare what you cited papers for against what they actually say.
