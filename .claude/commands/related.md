Find potentially missing related work for a paper.

Find the main .tex file in the current project. If $ARGUMENTS specifies a file, use that instead.

Run:
```
python3 -m paperscope related <paper.tex>
```

This searches OpenAlex for papers semantically similar to yours that aren't already in your bibliography. Requires the PAPERSCOPE_EMAIL environment variable to be set.

After the command completes:

1. **Read the JSON output** with ranked missing references
2. **Filter for genuinely relevant papers** — remove false positives (papers with similar keywords but different domains)
3. **For each relevant missing reference**, explain:
   - What it's about (1 sentence)
   - Why it's relevant to this paper
   - Where in the paper it should be cited (specific section)
   - Whether it supports, contradicts, or extends the paper's claims
4. **Draft BibTeX entries** for the top 3-5 missing references
5. **Suggest specific citation sentences** that could be added to the .tex file

Present results as a prioritized list: most important missing references first.
