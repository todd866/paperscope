#!/usr/bin/env python3
"""Block private/confidential content from entering this public repo.

Runs over the git-tracked files (what would be published) and fails if any carry
paywall-service references, unpublished-review statistics, private home paths,
real-author forensic naming, or the private constellation map. Wired as a git
pre-commit hook (scripts/install_hooks.sh) and runnable in CI.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = "scripts/check_public_safe.py"

# (label, regex) — case-insensitive. These must never appear in a public commit.
FORBIDDEN = [
    ("paywall service", r"annas[- ]?archive|sci[-_]?hub|scidb|libgen"),
    ("unpublished review stats", r"\b13,?058\b|\b6,?721\b|\b2,?210\b|\b1,?464\b|67\.5%|96\.7%"),
    ("private home path", r"/Users/[A-Za-z0-9._-]+"),
    ("private project path", r"Desktop/medicine|md-project"),
    ("real forensic author", r"rajizadeh|haghighian|fallah|azhar|demo_magnesium"),
    ("private constellation map", r"PROJECT-MAP|GLOBAL_PROJECT_MAP|highdimensional"),
]
COMPILED = [(label, re.compile(pat, re.I)) for label, pat in FORBIDDEN]
TEXT_EXT = re.compile(r"\.(py|md|txt|json|ts|tsx|js|mjs|yml|yaml|toml|cfg|sh|tex|bib)$", re.I)


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [f for f in out.splitlines() if f]
    except Exception:
        return [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
                if p.is_file() and ".git/" not in str(p) and "__pycache__" not in str(p)]


def main() -> int:
    problems: list[str] = []
    for rel in tracked_files():
        if rel == SELF or not TEXT_EXT.search(rel):
            continue
        try:
            text = (ROOT / rel).read_text(errors="ignore")
        except OSError:
            continue
        for label, rx in COMPILED:
            m = rx.search(text)
            if m:
                problems.append(f"{rel}: {label} -> {m.group(0)!r}")
    if problems:
        print("check_public_safe FAILED — refusing (do not commit/publish):", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 1
    print(f"check_public_safe: ok ({len(tracked_files())} files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
