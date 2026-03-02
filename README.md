# Paperscope

**A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin for academic paper analysis.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## What This Does

Paperscope gives Claude the ability to analyze your LaTeX papers. It embeds your paper and its literature into a shared vector space, then measures distances to catch problems that normally require manual reading.

Claude will automatically use these skills when relevant -- you don't need to remember commands.

### Skills

| Skill | Claude uses it when... |
|-------|----------------------|
| **analyze** | You're reviewing a paper, checking citations, or preparing for submission |
| **abstract-check** | You're finalizing a paper or checking abstract completeness |
| **journal-fit** | You're choosing where to submit |
| **revision-diff** | You're comparing paper versions or checking reviewer response |
| **related** | You're looking for missing related work |
| **cite-check** | You're verifying bibliography accuracy or cleaning up .bib files |

### What it catches

- **Citation misalignment** -- a sentence cites Reference A, but Reference B is the actual semantic match
- **Unsupported claims** -- paragraphs with no citation support that reviewers will flag
- **Novel claims without justification** -- your new contributions that need stronger backing
- **Abstract gaps** -- sections of the paper not represented in the abstract
- **Missing related work** -- papers you should cite but don't know about yet
- **Bad metadata** -- DOIs that don't match, missing DOIs, duplicate references

## Install

```bash
# Clone the plugin
git clone https://github.com/todd866/paperscope.git ~/.paperscope

# Install Python dependencies
pip install -r ~/.paperscope/requirements.txt

# Set your email for API polite pools (CrossRef, OpenAlex)
export PAPERSCOPE_EMAIL="you@university.edu"

# Launch Claude Code with the plugin
claude --plugin-dir ~/.paperscope
```

## Example

```
You: I've finished revising section 3, can you check the citations?

Claude: I'll run a citation analysis on your paper.
        [uses paperscope:analyze automatically]

        Citation alignment: 73% (11/15 contexts aligned)

        3 issues found:

        1. Line 142: "cortical oscillations maintain coherence"
           cites [zhang2019] but best match is [buzsaki2006]
           → Suggest replacing citation

        2. Line 203: Novel claim (max similarity: 0.28)
           "dimensional collapse below d=3 forces categorization"
           → This is your main contribution. Justification in §4 looks solid.

        3. Line 89: Weak paragraph (citation support: 0.19)
           → Consider citing [tononi2016] on integrated information.
```

## How It Works

1. **Text processing** -- LaTeX is cleaned to plain text, split into ~200-word overlapping chunks
2. **Embedding** -- Chunks encoded using sentence-transformers (all-MiniLM-L6-v2, 384-dim). Falls back to TF-IDF if the model isn't installed
3. **Similarity** -- Cosine similarity matrices between your paper chunks and literature chunks power all 12 analysis tools

For the full technical description, see the [paper (PDF)](paper/paperscope.pdf).

## CLI

The skills wrap a Python CLI. You can also run commands directly:

```bash
python3 -m paperscope analyze paper.tex --literature text/
python3 -m paperscope abstract-check paper.tex
python3 -m paperscope journal-fit paper.tex -j "BioSystems" "PLOS ONE"
python3 -m paperscope revision-diff old.tex new.tex
python3 -m paperscope related paper.tex
python3 -m paperscope extract . && python3 -m paperscope verify bibliography.json
```

## Requirements

- Python 3.8+
- `numpy`, `requests`
- `sentence-transformers` (optional -- falls back to TF-IDF)
- `PyMuPDF` for PDF text extraction

## License

MIT -- see [LICENSE](LICENSE).
