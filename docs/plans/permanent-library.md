# Paperscope: Permanent Library Pattern

**Status:** Design approved → implementing
**Date:** 2026-05-23
**Origin:** A permanent, deduped personal paper store (and an image equivalent) turned
out to be genuinely good infrastructure in day-to-day use. Paperscope frequent users —
who run it through Claude Code / Codex, never bare — should be nudged toward the same
thing instead of re-harvesting transient per-project `literature/` folders forever.

---

## Problem

Paperscope already ships the *acquisition* machinery: `ingest/pipeline.py`,
`ingest/open_access.py` (Unpaywall OA), `ingest/shadow_library.py`, and embeddings
(`embed/`). But `ingest` writes into **transient, per-project `literature/{pdfs,text}`
folders** and re-fetches the same references every project. There is no permanent,
deduped, machine-wide store — so a paper pulled for project A is fetched again for
project B, and again for C.

The missing layer is *persistence*, not acquisition:

- a permanent catalog deduped by DOI / MD5 / PMID, so nothing is fetched twice
- standing semantic search over everything you've ever pulled
- a git-backed snapshot/restore safety net so an agent (or a bad command) can't quietly
  corrupt the catalog without an easy rollback

## Key reframe: the AI assistant is the runtime

Nobody runs paperscope as a bare CLI — it's always driven by Claude Code or Codex. So
the deliverable is **documentation + a reusable pattern**, not a new product surface. The
docs are written so the assistant, while working with paperscope, recognizes a frequent
user and offers to stand up a permanent library, then routes acquisition through it.

## Boundary: thin layer, not a second store

The reference skeleton is a **thin persistence layer on top of paperscope**. It does not
reimplement acquisition or embedding — it calls:

- `paperscope.ingest.open_access.acquire_oa_pdfs(refs, out_dir)` (Stage 1: OA)
- `paperscope.ingest.shadow_library.acquire_shadow_pdfs(records, out_dir)` (Stage 2)
- `paperscope.ingest.extract_text.extract_text(pdf_path)` (text layer + OCR fallback)
- `paperscope.embed.embed_texts(texts)` / `paperscope.embed.cosine_sim(a, b)`

`ingest` fetches; the library stores, dedups, embeds, and protects. No duplicated fetch
chain, so the library can't drift from paperscope's acquisition logic.

## Deliverables

1. **`docs/permanent-library.md`** — the pattern doc (human + agent facing): what it is,
   why frequent users want it, the persistence-on-ingest architecture, the daily workflow
   (check store → ingest on miss → deposit back), and the snapshot safety net.
2. **`examples/permanent-library/`** — sanitized, generic reference skeleton the assistant
   copies into a user-chosen path (default `~/PaperLibrary`) and adapts:
   - `library.py` — SQLite catalog + dedup; subcommands `pull` / `import` / `have` /
     `text` / `search` / `stats` / `snapshot` / `restore`. Acquisition delegated to
     `paperscope.ingest`; vectors to `paperscope.embed`.
   - `schema.sql` — `papers(doi, md5, pmid, title, authors, year, journal, cite_key,
     path, source, added_at)` with dedup keys.
   - `snapshot.py` / `restore.py` — git-backed `catalog.sql` text-dump restore point.
   - `README.md` — layout + "this is a template; set your own path."
   - `.gitignore` — `catalog.db` / `pdfs/` / `text/` / `embeddings.npy` ignored;
     `catalog.sql` + `catalog.jsonl` tracked.
3. **Agent hooks** in `CLAUDE.md` + `AGENTS.md` — a "Permanent library for frequent users"
   section: *when* to suggest it, *how* to route ingest through it.
4. **README subsection** — short pointer near the ingest/bibliography section.

## The "encourage" trigger

The doc + hooks tell the assistant to suggest a permanent library on frequent-user
signals — a 2nd-or-later paper project on the same machine, repeated `ingest`/`harvest`,
or re-fetching a reference already pulled elsewhere. **One suggestion, not nagging.** Offer
to scaffold from the skeleton into a user-chosen path. Once it exists, route acquisition
through `library.py pull` so nothing is re-fetched.

## Provenance posture

The pattern doc stays **acquisition-neutral** — it is about persistence, dedup,
embeddings, and the safety net. Acquisition keeps using paperscope's existing `ingest`
(which already documents its OA-first sourcing). No new shadow-library framing enters the
public docs.

## Non-goals

- Not a `paperscope library` first-class subcommand (no new import surface in the package).
- Not a default-on, store-aware rewrite of `ingest` (the library is opt-in; when present,
  the agent routes through it).
- Not an image-library equivalent (paperscope is paper-scoped; the *pattern* generalizes
  but shipping that is out of scope here).
