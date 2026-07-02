#!/usr/bin/env python3
"""Permanent, local-first personal paper library — a thin layer on paperscope.

This is a *reference skeleton*, not a finished product: copy it to a permanent
path (default ``~/paper-library``), point it at paperscope, and adapt to taste.

What it adds on top of paperscope: a permanent SQLite catalog deduped by
DOI / MD5 / PMID, so a paper pulled for one project is never re-fetched for
another; standing semantic search over everything you've ever pulled; and a
git-backed snapshot/restore safety net for the catalog.

What it does NOT do: re-implement acquisition or embedding. Those are
paperscope's job. ``pull`` delegates to paperscope's OA + shadow acquisition,
text extraction, and embeddings:

    paperscope.ingest.open_access.acquire_oa_pdfs        # Stage 1: Unpaywall OA
    paperscope.ingest.shadow_library.acquire_shadow_pdfs # Stage 2: shadow fallback
    paperscope.ingest.extract_text.extract_text          # text layer (+ OCR fallback)
    paperscope.embed.embed_texts / cosine_sim            # vectors + similarity

Daily use:
    python3 library.py pull 10.1016/j.biosystems.2025.105608 --pmid 12345 --title "..."
    python3 library.py import /path/to/file.pdf --doi 10.x/y --title "..."
    python3 library.py have 10.1016/j.biosystems.2025.105608
    python3 library.py search "active inference free energy" -k 10
    python3 library.py stats
    python3 library.py snapshot "added 27 reframe-spine refs"
    python3 library.py restore --yes
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

# --- Library root -----------------------------------------------------------
# Override with $PAPER_LIBRARY or --root. Default keeps the store out of any
# single project so every project shares one deduped library.
ROOT = Path(os.environ.get("PAPER_LIBRARY", Path.home() / "paper-library")).expanduser()


def _paths(root: Path) -> dict:
    return {
        "root": root,
        "db": root / "catalog.db",
        "schema": Path(__file__).with_name("schema.sql"),
        "pdfs": root / "pdfs",
        "text": root / "text",
        "sql": root / "catalog.sql",
        "jsonl": root / "catalog.jsonl",
        "emb": root / "embeddings.npy",
        "emb_meta": root / "embeddings_meta.json",
    }


# --- paperscope bridge ------------------------------------------------------
def _import_paperscope():
    """Import paperscope, or exit with install guidance.

    paperscope must be importable: ``pip install -e /path/to/paperscope`` or set
    ``$PAPERSCOPE_HOME`` to the repo root.
    """
    try:
        import paperscope  # noqa: F401
        return
    except ImportError:
        home = os.environ.get("PAPERSCOPE_HOME")
        if home and (Path(home) / "paperscope").is_dir():
            sys.path.insert(0, home)
            try:
                import paperscope  # noqa: F401
                return
            except ImportError:
                pass
    sys.exit(
        "paperscope is not importable. Install it (`pip install -e /path/to/paperscope`)\n"
        "or set $PAPERSCOPE_HOME to the paperscope repo root."
    )


# --- catalog ----------------------------------------------------------------
def _connect(root: Path) -> sqlite3.Connection:
    p = _paths(root)
    p["pdfs"].mkdir(parents=True, exist_ok=True)
    p["text"].mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p["db"])
    conn.row_factory = sqlite3.Row
    conn.executescript(p["schema"].read_text())
    return conn


def _norm_doi(doi: str | None) -> str:
    if not doi:
        return ""
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _cite_key(doi: str, pmid: str, md5: str, fallback: str) -> str:
    if doi:
        return "doi-" + _slug(doi)
    if pmid:
        return "pmid-" + _slug(pmid)
    if md5:
        return "md5-" + md5[:16]
    return _slug(fallback) or "paper"


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _find(conn, doi="", pmid="", md5=""):
    """Return an existing row matching any provided identifier, else None."""
    for col, val in (("doi", _norm_doi(doi)), ("pmid", pmid.strip() if pmid else ""),
                     ("md5", md5)):
        if val:
            row = conn.execute(
                f"SELECT * FROM papers WHERE {col} = ?", (val,)
            ).fetchone()
            if row:
                return row
    return None


# --- embeddings (recompute-on-search; see README for the caching extension) -
def _embed_corpus(texts):
    """Return (matrix, backend) for a list of strings via paperscope.embed."""
    from paperscope.embed import embed_texts
    mat, info = embed_texts(texts, show_progress=False)
    return mat, info.get("backend", "?")


# --- commands ---------------------------------------------------------------
def cmd_pull(args) -> int:
    _import_paperscope()
    from paperscope.ingest.open_access import acquire_oa_pdfs
    from paperscope.ingest.shadow_library import acquire_shadow_pdfs
    from paperscope.ingest.extract_text import extract_text

    p = _paths(args.root)
    conn = _connect(args.root)
    doi = _norm_doi(args.doi)
    pmid = (args.pmid or "").strip()

    hit = _find(conn, doi=doi, pmid=pmid)
    if hit:
        print(f"have: {hit['cite_key']}  ({hit['source']})  {hit['path']}")
        return 0

    cite_key = args.cite_key or _cite_key(doi, pmid, "", doi or pmid or "paper")
    # title enables the content guard: acquire_oa_pdfs only verifies a
    # downloaded PDF against the paper when the ref carries a title
    ref = {"doi": doi, "cite_key": cite_key, "pmid": pmid,
           "title": (args.title or "").strip()}

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # Stage 1: open access (Unpaywall). Stage 2: shadow fallback.
        if doi:
            acquire_oa_pdfs([ref], tmp, verbose=False)
        got = tmp / f"{cite_key}.pdf"
        if not got.exists() and doi:
            acquire_shadow_pdfs([ref], tmp, id_key="cite_key", verbose=False)
        if not got.exists():
            print(f"could not acquire: {doi or '(no doi)'}")
            return 1
        source = "oa"  # best-effort label; refine via the acquisition reports if needed
        md5 = _md5(got)
        dup = _find(conn, md5=md5)
        if dup:  # same bytes already stored under a different identifier
            print(f"have (by md5): {dup['cite_key']}  {dup['path']}")
            return 0
        text = extract_text(got)
        dest = p["pdfs"] / f"{cite_key}.pdf"
        shutil.move(str(got), dest)

    (p["text"] / f"{cite_key}.txt").write_text(text or "")
    _insert(conn, doi=doi, md5=md5, pmid=pmid, title=args.title or "",
            cite_key=cite_key, path=f"pdfs/{cite_key}.pdf", source=source)
    conn.commit()
    print(f"stored: {cite_key}  ({len(text or '')} chars text)")
    return 0


def cmd_import(args) -> int:
    p = _paths(args.root)
    conn = _connect(args.root)
    src = Path(args.file).expanduser()
    if not src.exists():
        print(f"no such file: {src}")
        return 1
    md5 = _md5(src)
    dup = _find(conn, doi=_norm_doi(args.doi), pmid=(args.pmid or ""), md5=md5)
    if dup:
        print(f"have: {dup['cite_key']}  {dup['path']}")
        return 0
    doi, pmid = _norm_doi(args.doi), (args.pmid or "").strip()
    cite_key = args.cite_key or _cite_key(doi, pmid, md5, src.stem)
    dest = p["pdfs"] / f"{cite_key}.pdf"
    shutil.copy2(src, dest)
    text = ""
    try:
        _import_paperscope()
        from paperscope.ingest.extract_text import extract_text
        text = extract_text(dest) or ""
    except SystemExit:
        print("(paperscope unavailable: stored PDF without text extraction)")
    (p["text"] / f"{cite_key}.txt").write_text(text)
    _insert(conn, doi=doi, md5=md5, pmid=pmid, title=args.title or "",
            cite_key=cite_key, path=f"pdfs/{cite_key}.pdf", source="import")
    conn.commit()
    print(f"imported: {cite_key}  ({len(text)} chars text)")
    return 0


def _insert(conn, **kw):
    kw.setdefault("added_at", _dt.datetime.now().isoformat(timespec="seconds"))
    cols = ", ".join(kw)
    conn.execute(
        f"INSERT INTO papers ({cols}) VALUES ({', '.join('?' for _ in kw)})",
        tuple(kw.values()),
    )


def _touch(conn, cite_key) -> None:
    """Stamp an access for storage tiering (see storage.py). No-op if columns absent."""
    try:
        conn.execute(
            "UPDATE papers SET last_accessed=?, access_count=COALESCE(access_count,0)+1 "
            "WHERE cite_key=?",
            (_dt.datetime.now().isoformat(timespec="seconds"), cite_key),
        )
        conn.commit()
    except Exception:
        pass


def cmd_have(args) -> int:
    conn = _connect(args.root)
    ident = args.identifier
    row = _find(conn, doi=ident, pmid=ident, md5=ident)
    if row:
        print(f"{row['cite_key']}\t{row['doi']}\t{row['title']}\t{row['path']}")
        return 0
    print("not in library")
    return 1


def cmd_text(args) -> int:
    p = _paths(args.root)
    conn = _connect(args.root)
    row = _find(conn, doi=args.identifier, pmid=args.identifier, md5=args.identifier)
    if not row:
        print("not in library")
        return 1
    tp = p["text"] / f"{row['cite_key']}.txt"
    _touch(conn, row["cite_key"])
    print(str(tp) if tp.exists() else "(no extracted text)")
    return 0 if tp.exists() else 1


def cmd_search(args) -> int:
    _import_paperscope()
    from paperscope.embed import cosine_sim
    import numpy as np

    p = _paths(args.root)
    conn = _connect(args.root)
    rows = conn.execute("SELECT cite_key, title, doi FROM papers").fetchall()
    keys, texts = [], []
    for r in rows:
        tp = p["text"] / f"{r['cite_key']}.txt"
        if tp.exists():
            keys.append(r)
            texts.append(tp.read_text()[:20000])  # cap per-doc for speed
    if not texts:
        print("library has no extracted text yet")
        return 1
    # Recompute embeddings for query + corpus in one call so the backend
    # (sentence-transformers or TF-IDF) is consistent. See README for the
    # persistent embeddings.npy cache once the library grows large.
    mat, backend = _embed_corpus([args.query] + texts)
    q, docs = mat[0], mat[1:]
    sims = cosine_sim(q[None, :], docs)[0]
    order = np.argsort(-sims)[: args.k]
    print(f"top {len(order)} ({backend}):")
    for i in order:
        r = keys[i]
        _touch(conn, r["cite_key"])
        print(f"  {sims[i]:.3f}  {r['cite_key']}  {r['title'] or r['doi']}")
    return 0


def cmd_stats(args) -> int:
    conn = _connect(args.root)
    n = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    by_src = conn.execute(
        "SELECT source, COUNT(*) c FROM papers GROUP BY source ORDER BY c DESC"
    ).fetchall()
    n_doi = conn.execute("SELECT COUNT(*) FROM papers WHERE doi != ''").fetchone()[0]
    print(f"library: {args.root}")
    print(f"papers:  {n}  ({n_doi} with DOI)")
    for r in by_src:
        print(f"  {r['source'] or '(none)'}: {r['c']}")
    return 0


# --- snapshot / restore safety net ------------------------------------------
def _export_manifest(conn, jsonl: Path) -> None:
    rows = conn.execute(
        "SELECT doi, pmid, title, cite_key, source FROM papers ORDER BY id"
    ).fetchall()
    with open(jsonl, "w") as fh:
        for r in rows:
            fh.write(json.dumps(dict(r)) + "\n")


def cmd_snapshot(args) -> int:
    import subprocess
    p = _paths(args.root)
    conn = _connect(args.root)
    # Text dump = the diffable restore point (catalog.db itself is gitignored).
    with open(p["sql"], "w") as fh:
        for line in conn.iterdump():
            fh.write(line + "\n")
    _export_manifest(conn, p["jsonl"])
    # Ensure the ignore rules exist even if library.py was run from a non-copied
    # location, so a snapshot never accidentally tracks the large/binary stores.
    gitignore = args.root / ".gitignore"
    if not gitignore.exists():
        shutil.copy2(Path(__file__).with_name(".gitignore"), gitignore)
    root = str(args.root)
    if not (args.root / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=root, check=False)
    # Stage only files that exist: a missing pathspec would fail `git add`
    # atomically and stage nothing.
    to_add = [f for f in ("catalog.sql", "catalog.jsonl", ".gitignore")
              if (args.root / f).exists()]
    subprocess.run(["git", "add", *to_add], cwd=root, check=False)
    subprocess.run(["git", "commit", "-q", "-m", args.message], cwd=root, check=False)
    print(f"snapshot: {args.message}")
    return 0


def cmd_restore(args) -> int:
    p = _paths(args.root)
    if not p["sql"].exists():
        print("no catalog.sql to restore from")
        return 1
    if not args.yes:
        print("refusing to overwrite catalog.db without --yes")
        return 1
    if p["db"].exists():
        p["db"].unlink()
    conn = sqlite3.connect(p["db"])
    conn.executescript(p["sql"].read_text())
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    print(f"restored {n} papers from catalog.sql")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Permanent paper library (paperscope thin layer)")
    ap.add_argument("--root", type=lambda s: Path(s).expanduser(), default=ROOT,
                    help=f"library root (default {ROOT}; or $PAPER_LIBRARY)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("pull", help="acquire by DOI via paperscope, store + dedup")
    sp.add_argument("doi")
    sp.add_argument("--pmid", default="")
    sp.add_argument("--title", default="")
    sp.add_argument("--cite-key", default="")
    sp.set_defaults(func=cmd_pull)

    sp = sub.add_parser("import", help="store a local PDF you already have")
    sp.add_argument("file")
    sp.add_argument("--doi", default="")
    sp.add_argument("--pmid", default="")
    sp.add_argument("--title", default="")
    sp.add_argument("--cite-key", default="")
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("have", help="is this DOI/PMID/MD5 already stored?")
    sp.add_argument("identifier")
    sp.set_defaults(func=cmd_have)

    sp = sub.add_parser("text", help="path to a stored paper's extracted text")
    sp.add_argument("identifier")
    sp.set_defaults(func=cmd_text)

    sp = sub.add_parser("search", help="semantic search over stored text")
    sp.add_argument("query")
    sp.add_argument("-k", type=int, default=10)
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("stats", help="catalog summary")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("snapshot", help="git restore point for the catalog")
    sp.add_argument("message")
    sp.set_defaults(func=cmd_snapshot)

    sp = sub.add_parser("restore", help="rebuild catalog.db from catalog.sql")
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_restore)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
