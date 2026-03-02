Find the best-fit journals for a paper based on semantic similarity.

Find the main .tex file in the current project. If $ARGUMENTS specifies journals, use those. Otherwise, ask which journals to compare against.

Run:
```
python3 -m paperscope journal-fit <paper.tex> -j <journal1> <journal2> ...
```

After the command completes:

1. **Read the JSON output** with per-journal similarity scores
2. **Rank journals** from best to worst fit, with the similarity score
3. **For the top journal**, explain which sections of the paper align most strongly with that journal's recent publications
4. **For poor-fit journals** (similarity < 0.3), explain why — is the paper too theoretical? Too applied? Wrong domain?
5. **Suggest 1-2 additional journals** to check based on the paper's content, if the results suggest the initial list isn't ideal

Present results as a ranked table: journal name, similarity score, and a brief note on fit.
