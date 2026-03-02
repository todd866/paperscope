# Paperscope

**Slash commands for academic paper analysis in [Claude Code](https://docs.anthropic.com/en/docs/claude-code).**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## What This Is

Paperscope gives Claude Code a set of slash commands for analyzing LaTeX papers. It embeds your paper and its literature into a shared vector space, then measures distances to answer questions that normally require manual reading.

### Slash Commands

| Command | What it does |
|---------|-------------|
| `/analyze` | Citation alignment, novelty detection, argument strength |
| `/abstract-check` | Does the abstract cover all major sections? |
| `/journal-fit` | Rank journals by semantic similarity to your paper |
| `/revision-diff` | Semantic diff between two versions of a paper |
| `/related` | Find missing related work via OpenAlex |
| `/cite-check` | Verify all DOIs and reference metadata |

Type a slash command and Claude handles the rest -- runs the analysis, reads the output, identifies issues, and suggests specific fixes.

## Install

```bash
# Clone into your paper project
git clone https://github.com/todd866/paperscope.git .paperscope
pip install -r .paperscope/requirements.txt

# Copy slash commands into your project
cp -r .paperscope/.claude/commands/ .claude/commands/

# Set your email for API polite pools (CrossRef, OpenAlex, Unpaywall)
export PAPERSCOPE_EMAIL="you@university.edu"
```

Or install globally for all projects:

```bash
git clone https://github.com/todd866/paperscope.git ~/.paperscope
pip install -r ~/.paperscope/requirements.txt
cp -r ~/.paperscope/.claude/commands/ ~/.claude/commands/
```

## How It Works

1. **You write your paper** in LaTeX
2. **Type `/analyze`** in Claude Code
3. **Claude runs the analysis**, reads the JSON output, and tells you:
   - Which citations don't match the claims they're attached to
   - Which claims are novel (reviewers will scrutinize these)
   - Which paragraphs lack citation support
4. **Claude suggests specific fixes** -- replacement citations, additional references, abstract edits

### Example

```
You: /analyze

Claude: Running analysis on paper.tex against 47 literature files...

Citation alignment: 73% (11/15 contexts aligned)

Issues found:
1. Line 142: "cortical oscillations maintain coherence across regions"
   cites [zhang2019] but best match is [buzsaki2006] (similarity 0.82 vs 0.31)

2. Line 203: Claim flagged as novel (max literature similarity: 0.28)
   "dimensional collapse below d=3 forces discrete categorization"
   → This is your main contribution. Ensure strong justification in §4.

3. Paragraph at line 89: citation support 0.19 (weak)
   → Consider citing [tononi2016] which covers integrated information.
```

## What It Analyzes

**Citation alignment** -- For each sentence with a `\cite{}`, checks whether the cited papers are actually the closest semantic matches in your literature. Catches the most common AI-assisted writing failure: plausible-sounding but wrong citations.

**Novelty detection** -- Flags claims whose maximum similarity to any literature chunk falls below threshold. These are what reviewers will focus on.

**Abstract coverage** -- Embeds each section and the abstract, identifies sections that are underrepresented. Suggests specific additions.

**Journal targeting** -- Fetches recent abstracts from candidate journals via OpenAlex, ranks by semantic similarity to your paper. Replaces guesswork with measurement.

**Revision diff** -- Embeds two versions of the paper, measures semantic shift per section. Shows whether changes moved the paper toward or away from the literature.

**Related work radar** -- Searches OpenAlex for semantically similar papers not in your bibliography. Finds what you're missing before reviewers do.

**Plus**: reviewer probes, self-overlap detection, argument flow tracking, strength heatmaps, cross-paper consistency, argument graphs.

## CLI Reference

The slash commands wrap a Python CLI. You can also run commands directly:

```bash
python3 -m paperscope analyze paper.tex --literature text/
python3 -m paperscope abstract-check paper.tex
python3 -m paperscope journal-fit paper.tex -j "BioSystems" "PLOS ONE"
python3 -m paperscope revision-diff old.tex new.tex
python3 -m paperscope related paper.tex
```

### Bibliography pipeline

```bash
python3 -m paperscope extract /path/to/paper/
python3 -m paperscope resolve bibliography.json
python3 -m paperscope verify bibliography.json
python3 -m paperscope harvest --config config.yaml
python3 -m paperscope ingest /path/to/literature/
```

## Requirements

- Python 3.8+
- `numpy`, `requests`
- `sentence-transformers` (optional -- falls back to TF-IDF)
- `PyMuPDF` for PDF text extraction

## Paper

For the full technical description, see the [paper (PDF)](paper/paperscope.pdf).

## License

MIT -- see [LICENSE](LICENSE).
