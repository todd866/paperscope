"""Regression tests for the permanent-library reference skeleton.

Exercises the real CLI surface (no network): import + dedup, the snapshot/restore
safety net, and the .gitignore rules. Guards two bugs found during development:
  1. snapshot staged nothing when .gitignore was absent (atomic `git add` failure);
  2. .gitignore patterns were dead because of trailing inline comments.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKEL = REPO / "examples" / "permanent-library"
LIB = SKEL / "library.py"
DEMO_PDF = REPO / "paper" / "paperscope.pdf"

pytestmark = pytest.mark.skipif(
    not DEMO_PDF.exists(), reason="demo PDF not present"
)


def _run(root: Path, *args):
    env = {
        "PAPERSCOPE_HOME": str(REPO),
        "PAPER_LIBRARY": str(root),
        "PATH": __import__("os").environ.get("PATH", ""),
        "HOME": __import__("os").environ.get("HOME", ""),
    }
    return subprocess.run(
        [sys.executable, str(LIB), *args],
        cwd=str(SKEL), env=env, capture_output=True, text=True,
    )


def test_import_dedup_snapshot_restore(tmp_path):
    root = tmp_path / "lib"

    # import a paper
    r = _run(root, "import", str(DEMO_PDF), "--doi", "10.9999/a", "--title", "X")
    assert r.returncode == 0, r.stderr
    assert "imported" in r.stdout

    # re-import the same DOI -> dedup, not a second row
    r = _run(root, "import", str(DEMO_PDF), "--doi", "10.9999/a", "--title", "dup")
    assert "have" in r.stdout

    r = _run(root, "stats")
    assert "papers:  1" in r.stdout

    # have / not-have exit codes
    assert _run(root, "have", "10.9999/a").returncode == 0
    assert _run(root, "have", "10.9999/nope").returncode == 1

    # snapshot must actually commit (bug #1) even though no .gitignore was copied
    assert _run(root, "snapshot", "first").returncode == 0
    log = subprocess.run(["git", "-C", str(root), "log", "--oneline"],
                         capture_output=True, text=True)
    assert "first" in log.stdout

    # tracked set is exactly the text dumps + ignore file
    tracked = subprocess.run(["git", "-C", str(root), "ls-files"],
                             capture_output=True, text=True).stdout.split()
    assert set(tracked) == {".gitignore", "catalog.sql", "catalog.jsonl"}

    # .gitignore patterns actually match (bug #2)
    ci = subprocess.run(
        ["git", "-C", str(root), "check-ignore",
         "catalog.db", "pdfs/x.pdf", "text/y.txt", "embeddings.npy"],
        capture_output=True, text=True,
    )
    assert ci.returncode == 0
    assert {"catalog.db", "pdfs/x.pdf", "text/y.txt", "embeddings.npy"} == set(
        ci.stdout.split()
    )

    # restore rebuilds the catalog from the text dump
    (root / "catalog.db").unlink()
    r = _run(root, "restore", "--yes")
    assert "restored 1 papers" in r.stdout
    assert "papers:  1" in _run(root, "stats").stdout
