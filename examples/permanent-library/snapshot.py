#!/usr/bin/env python3
"""Make a git restore point for the catalog. Thin wrapper over library.py."""
import argparse
import library


def main():
    ap = argparse.ArgumentParser(description="snapshot the catalog")
    ap.add_argument("message")
    ap.add_argument("--root", type=library.Path, default=library.ROOT)
    args = ap.parse_args()
    return library.cmd_snapshot(args)


if __name__ == "__main__":
    raise SystemExit(main())
