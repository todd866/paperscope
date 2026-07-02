"""Storage tiering for the permanent library — keep it under a size cap by evicting the
PDFs of low-value entries while preserving their extracted plaintext.

Eviction is a CACHE EVICTION, not data loss: the PDF is deleted and `path` cleared
(`pdf_evicted=1`), but `text/<cite_key>.txt`, `doi`/`md5`, and metadata stay, so the PDF is
re-fetchable on demand (`storage.py restore <id>`, which re-runs the library's own `pull`).

Conventions match this skeleton: a library root (``--root`` or ``$PAPER_LIBRARY``, default
``~/paper-library``) holding ``catalog.db``, ``pdfs/<cite_key>.pdf``, ``text/<cite_key>.txt``.

CLI:
  python3 storage.py [--root DIR] status
  python3 storage.py [--root DIR] plan
  python3 storage.py [--root DIR] prune --apply
  python3 storage.py [--root DIR] restore <doi|pmid|md5|cite_key>
  python3 storage.py [--root DIR] pin <id> | unpin <id>
  python3 storage.py [--root DIR] migrate
"""
import os, sys, sqlite3, subprocess, datetime
from pathlib import Path

GB = 1024 ** 3
CAP = float(os.environ.get("STORAGE_CAP_GB", "200")) * GB
LOWWATER = float(os.environ.get("STORAGE_LOWWATER_GB", "180")) * GB
W_COLD = float(os.environ.get("W_COLD", "1.0"))
W_CHEAP = float(os.environ.get("W_CHEAP", "0.5"))
W_SIZE = float(os.environ.get("W_SIZE", "0.6"))
W_CITE = float(os.environ.get("W_CITE", "0.8"))

NEW_COLS = {
    "last_accessed": "TEXT", "access_count": "INTEGER DEFAULT 0",
    "pinned": "INTEGER DEFAULT 0", "pdf_evicted": "INTEGER DEFAULT 0",
    "cited_by_count": "INTEGER",
}


def _root(argv):
    r = None
    if "--root" in argv:
        r = argv[argv.index("--root") + 1]
    return Path(r or os.environ.get("PAPER_LIBRARY") or Path.home() / "paper-library")


def _con(root):
    return sqlite3.connect(root / "catalog.db")


def migrate(root):
    c = _con(root)
    have = {r[1] for r in c.execute("PRAGMA table_info(papers)")}
    added = [col for col in NEW_COLS if col not in have]
    for col in added:
        c.execute(f"ALTER TABLE papers ADD COLUMN {col} {NEW_COLS[col]}")
    c.commit(); c.close()
    print(f"migrate: added {added or 'nothing (already current)'}")


def _du(path):
    t = 0
    for r, _, fs in os.walk(path):
        for f in fs:
            try: t += os.path.getsize(os.path.join(r, f))
            except OSError: pass
    return t


def _age_days(ts):
    if not ts: return 1e9
    try:
        d = datetime.datetime.fromisoformat(ts)
        now = datetime.datetime.now(d.tzinfo) if d.tzinfo else datetime.datetime.now()
        return max(0.0, (now - d).total_seconds() / 86400.0)
    except Exception:
        return 1e9


def _candidates(root):
    c = _con(root); c.row_factory = sqlite3.Row
    rows = c.execute(
        "SELECT cite_key, doi, md5, path, added_at, last_accessed, "
        "COALESCE(cited_by_count,0) cby FROM papers "
        "WHERE path!='' AND (doi!='' OR md5!='') "
        "AND COALESCE(pinned,0)=0 AND COALESCE(pdf_evicted,0)=0"
    ).fetchall()
    c.close()
    out = []
    for r in rows:
        pdf = root / r["path"]
        txt = root / "text" / f"{r['cite_key']}.txt"
        if not pdf.exists() or not txt.exists():
            continue  # need a PDF to evict and text as the safety net
        out.append(dict(cite_key=r["cite_key"], doi=r["doi"], md5=r["md5"], pdf=pdf,
                        size=pdf.stat().st_size, cold=_age_days(r["last_accessed"] or r["added_at"]),
                        cheap=1.0 if r["doi"] else 0.5, cite=r["cby"]))
    return out


def _scored(cands):
    if not cands: return []
    def span(k):
        v = [c[k] for c in cands]; lo = min(v); return lo, (max(v) - lo) or 1.0
    cl, cr = span("cold"); sl, sr = span("size"); il, ir = span("cite")
    for c in cands:
        c["score"] = (W_COLD * (c["cold"]-cl)/cr + W_CHEAP * c["cheap"]
                      + W_SIZE * (c["size"]-sl)/sr - W_CITE * (c["cite"]-il)/ir)
    return sorted(cands, key=lambda c: -c["score"])


def _f(n): return f"{n/GB:.2f} GB"


def _plan(root):
    cur = _du(root / "pdfs") + _du(root / "books")
    if cur <= CAP:
        return cur, []
    need, plan, freed = cur - LOWWATER, [], 0
    for c in _scored(_candidates(root)):
        if freed >= need: break
        plan.append(c); freed += c["size"]
    return cur, plan


def status(root):
    cur = _du(root / "pdfs") + _du(root / "books")
    c = _con(root)
    tot = c.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    ev = c.execute("SELECT COUNT(*) FROM papers WHERE COALESCE(pdf_evicted,0)=1").fetchone()[0]
    c.close()
    print(f"{root}\ntotal {_f(cur)} / cap {_f(CAP)} (low-water {_f(LOWWATER)})")
    print("OVER by " + _f(cur-CAP) if cur > CAP else "under cap, headroom " + _f(CAP-cur))
    print(f"rows: {tot} | evictable {len(_candidates(root))} | evicted {ev}")


def plan(root, apply=False):
    cur, p = _plan(root)
    if not p:
        print(f"under cap ({_f(cur)} ≤ {_f(CAP)}); nothing to evict."); return
    freed = sum(c["size"] for c in p)
    print(f"{_f(cur)} > cap {_f(CAP)}; evicting {len(p)} PDFs to free {_f(freed)} → {_f(cur-freed)}")
    for c in p[:40]:
        print(f"  {c['score']:+.2f}  {_f(c['size']):>9}  cold {c['cold']:5.0f}d  "
              f"{'DOI' if c['doi'] else 'md5'}  {c['cite_key']}")
    if not apply:
        print("(dry run — prune --apply to evict)"); return
    c = _con(root)
    for x in p:
        try: x["pdf"].unlink()
        except OSError: pass
        c.execute("UPDATE papers SET path='', pdf_evicted=1 WHERE cite_key=?", (x["cite_key"],))
    c.commit(); c.close()
    print(f"evicted {len(p)} PDFs (~{_f(freed)}); text kept, re-fetch with restore <id>")


def restore(root, ident):
    c = _con(root); c.row_factory = sqlite3.Row
    row = c.execute("SELECT * FROM papers WHERE doi=? OR md5=? OR pmid=? OR cite_key=?",
                    (ident, ident, ident, ident)).fetchone()
    c.close()
    if not row:
        sys.exit(f"not in library: {ident}")
    if row["path"] and (root / row["path"]).exists():
        print("already present"); return
    if not row["doi"]:
        sys.exit("md5-only entry — re-fetch manually via paperscope shadow ingest")
    lib = Path(__file__).with_name("library.py")
    rc = subprocess.call([sys.executable, str(lib), "--root", str(root), "pull", row["doi"]])
    if rc == 0:
        cc = _con(root); cc.execute("UPDATE papers SET pdf_evicted=0 WHERE cite_key=?",
                                    (row["cite_key"],)); cc.commit(); cc.close()
        print("restored", row["cite_key"])
    else:
        print("restore failed for", row["cite_key"])


def _pin(root, ident, val):
    c = _con(root)
    n = c.execute("UPDATE papers SET pinned=? WHERE doi=? OR md5=? OR pmid=? OR cite_key=?",
                  (val, ident, ident, ident, ident)).rowcount
    c.commit(); c.close()
    print(("pinned " if val else "unpinned ") + ident if n else f"not in library: {ident}")


def main():
    argv = sys.argv[1:]
    root = _root(argv)
    if not (root / "catalog.db").exists():
        sys.exit(f"no catalog.db under {root} (set --root or $PAPER_LIBRARY)")
    migrate(root)
    # positional args = argv minus the --root flag (and its value) and --apply
    pos, skip = [], False
    for a in argv:
        if skip:
            skip = False; continue
        if a == "--root":
            skip = True; continue
        if a == "--apply":
            continue
        pos.append(a)
    cmd = pos[0] if pos else "status"
    arg = pos[1] if len(pos) > 1 else None
    if cmd == "status": status(root)
    elif cmd == "plan": plan(root, False)
    elif cmd == "prune": plan(root, "--apply" in argv)
    elif cmd == "restore" and arg: restore(root, arg)
    elif cmd == "pin" and arg: _pin(root, arg, 1)
    elif cmd == "unpin" and arg: _pin(root, arg, 0)
    elif cmd == "migrate": pass
    else: print(__doc__)


if __name__ == "__main__":
    main()
