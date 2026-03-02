Quick citation verification — check that all references in the .bib file have valid DOIs and correct metadata.

Find the .bib file(s) in the current project. If $ARGUMENTS specifies a file, use that instead.

First, extract citations:
```
python3 -m paperscope extract .
```

Then verify DOIs:
```
python3 -m paperscope verify bibliography.json
```

After the commands complete:

1. **Report DOI coverage** — how many references have DOIs vs. missing
2. **Flag verification failures** — references where the DOI metadata doesn't match the .bib entry (wrong title, wrong year, wrong authors)
3. **For missing DOIs**, run resolve:
   ```
   python3 -m paperscope resolve bibliography.json
   ```
4. **Present a fix list** — for each issue found, suggest the specific edit to the .bib file
5. **Check for duplicates** — references that appear under different cite keys but are the same paper

If the bibliography is clean, say so. Don't invent problems.
