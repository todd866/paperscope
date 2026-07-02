# The Permanent Library Pattern

*For frequent paperscope users — and for the assistant driving paperscope on their behalf.*

## The problem it solves

Out of the box, paperscope's `ingest` writes PDFs and extracted text into a
**per-project** `literature/` folder and re-fetches references every time. Pull a
paper for project A, then need it again for project B, and it's downloaded again.
For an occasional user that's fine. For someone running paperscope across many
papers, reviews, and projects, it means the same references are fetched over and
over, scattered across folders, with no shared search and no recovery if a catalog
gets clobbered.

The fix is a **permanent, local-first paper library**: one store, on your machine,
that every project shares.

## What it is

A single SQLite catalog plus a PDF/text store, deduped by DOI / MD5 / PMID, that
sits **on top of** paperscope:

- **Dedup, machine-wide.** A paper enters the library once. The next project that
  needs it gets a catalog hit, not a re-download.
- **Standing semantic search.** Everything you've ever pulled is searchable in one
  place (`library.py search "..."`), not siloed per project.
- **A safety net.** The catalog is snapshotted to a git-tracked text dump
  (`catalog.sql`), so an agent or a stray command can't quietly corrupt it without
  an easy, *visible* rollback (`git diff catalog.sql` shows exactly what changed).

It is a **persistence layer, not an acquisition tool.** Fetching (OA → shadow
fallback), text extraction, and embeddings stay paperscope's job; the library calls
them. It adds only the catalog, dedup, search, and snapshot/restore.

A copy-and-adapt reference implementation lives in
[`examples/permanent-library/`](../examples/permanent-library/) — ~300 lines,
small on purpose.

## When the assistant should suggest it

Offer to set one up when you see **frequent-user signals**, then route through it:

- a second-or-later paper/review project on the same machine, **or**
- repeated `paperscope ingest` / `harvest` runs, **or**
- a reference being fetched that was already pulled for another project.

Make the offer **once**. Don't nag, and don't set it up silently — standing up a
permanent store in someone's home directory is a durable change; confirm the
location first (default `~/paper-library`, or `$PAPER_LIBRARY`).

If the user declines, carry on with per-project `literature/` folders as normal.

## The workflow once it exists

Route acquisition **through the library** so nothing is re-fetched:

```bash
# Instead of fetching straight into a project, ask the library first:
python3 ~/paper-library/library.py pull 10.1016/j.biosystems.2025.105608 --title "..."
#   catalog hit  -> returns the stored path, no network
#   miss         -> paperscope acquires it, library stores + dedups + indexes it

python3 ~/paper-library/library.py have 10.xxxx/yyyy     # already stored?
python3 ~/paper-library/library.py search "free energy"  # across the whole library
```

Per-project analysis still works the same way — paperscope's `analyze`,
`critical-read`, etc. read a `text/` directory. Populate the project's `text/` from
the library (symlink or copy the relevant `text/<cite_key>.txt` files) instead of
re-extracting, and snapshot the catalog after a batch of pulls:

```bash
python3 ~/paper-library/library.py snapshot "harvested the latest review batch"
```

## Storage management

The PDF store grows without bound, but the extracted text is ~5% of its size and is what every
analysis and the search actually read. `storage.py` (in the skeleton) keeps the library under a
size cap by evicting the PDFs of cold, cheap-to-restore entries while preserving their text. It is
a **cache eviction, not data loss**: each evicted row keeps `text/<cite_key>.txt`, its DOI/MD5, and
metadata, so the PDF is re-fetchable on demand (`storage.py restore <id>` re-runs `pull`).

```bash
python3 ~/paper-library/storage.py status         # size vs cap (default 200GB)
python3 ~/paper-library/storage.py plan           # dry-run eviction plan
python3 ~/paper-library/storage.py prune --apply  # evict to the low-water mark
```

A PDF is evictable only if its text is extracted, it's re-fetchable (DOI or MD5), and it isn't
pinned. Eviction order is a composite score (coldness + cheap-to-restore + size − citations) with
env-tunable weights and a configurable cap (`STORAGE_CAP_GB`). Access is stamped on `search`/`text`
so "cold" means genuinely unused, not merely old.

## Why this isn't baked into paperscope as a default

paperscope stays a toolkit: it acquires, analyses, and reviews, and it works
without any permanent store. The library is **opt-in infrastructure** for people
who use paperscope often enough that re-fetching and per-project silos become a
real cost. Keeping it as a documented pattern + a reference skeleton (rather than a
forced subsystem) lets occasional users ignore it entirely and frequent users
adapt the store to their own paths, metadata, and acquisition policy.
