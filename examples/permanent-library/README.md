# Permanent Paper Library — reference skeleton

A permanent, local-first personal paper store, deduped by DOI / MD5 / PMID, that
sits **on top of** paperscope. Every paper pulled for any project lands here once
and is never re-fetched. This is a **template to copy and adapt**, not a finished
product — it is intentionally small.

> **This is the persistence layer, not an acquisition tool.** Fetching, text
> extraction, and embeddings are paperscope's job; this skeleton only catalogs,
> dedups, searches, and protects. See [`../../docs/permanent-library.md`](../../docs/permanent-library.md)
> for the full pattern and when an assistant should suggest standing one up.

## Setup

```bash
# 1. Copy this folder to a permanent location, outside any single project:
cp -r examples/permanent-library ~/PaperLibrary && cd ~/PaperLibrary

# 2. Make paperscope importable (either is fine):
pip install -e /path/to/paperscope          # preferred
export PAPERSCOPE_HOME=/path/to/paperscope  # or point at the repo root

# 3. (optional) override the default location ~/PaperLibrary:
export PAPER_LIBRARY=~/research/papers
```

## Daily use

```bash
python3 library.py pull 10.1016/j.biosystems.2025.105608 --pmid 12345 --title "..."
python3 library.py import /path/to/file.pdf --doi 10.x/y --title "..."
python3 library.py have 10.1016/j.biosystems.2025.105608   # exit 0 if stored
python3 library.py search "active inference free energy" -k 10
python3 library.py stats
```

`pull` checks the catalog first; on a miss it delegates acquisition to paperscope
(OA → shadow fallback), extracts text, dedups by content MD5, and stores. So the
second project that needs a paper gets a catalog hit, not a re-download.

## The safety net

```bash
python3 library.py snapshot "added 27 reframe-spine refs"   # git restore point
python3 library.py restore --yes                            # rebuild db from catalog.sql
```

`catalog.sql` and `catalog.jsonl` are tracked text dumps; `catalog.db`, `pdfs/`,
`text/`, and embeddings are gitignored because they're large and reproducible. The
point of the git history is to *see and undo* an agent's (or a bad command's)
damage to the catalog — `git diff catalog.sql` shows exactly what changed.

## Layout

| File | Role |
|------|------|
| `library.py` | catalog + dedup + the `pull`/`import`/`have`/`text`/`search`/`stats`/`snapshot`/`restore` commands |
| `schema.sql` | catalog schema (papers table + partial-unique dedup indexes) |
| `snapshot.py` / `restore.py` | thin wrappers over the same functions |
| `catalog.db` | live SQLite catalog *(gitignored)* |
| `catalog.sql` / `catalog.jsonl` | tracked text dump + readable manifest |
| `pdfs/`, `text/` | PDF store + extracted text *(gitignored, reproducible)* |

## Adapting it

This skeleton recomputes embeddings on every `search` (correct under both the
sentence-transformers and TF-IDF backends, but O(corpus) per query). Once your
library grows past a few hundred papers, add a persistent `embeddings.npy` +
`embeddings_meta.json` cache and append incrementally on `pull`/`import` — that is
the one obvious extension and the only piece this skeleton deliberately omits.

Other natural additions: a `backfill` step (CrossRef metadata for DOI-only rows),
ebook extraction, and a `--like <cite_key>` "more like this" search mode.
