#!/usr/bin/env python3
"""Rebuild catalog.db from the last catalog.sql snapshot. Thin wrapper."""
import argparse
import library


def main():
    ap = argparse.ArgumentParser(description="restore the catalog from catalog.sql")
    ap.add_argument("--yes", action="store_true", help="confirm overwrite of catalog.db")
    ap.add_argument("--root", type=library.Path, default=library.ROOT)
    args = ap.parse_args()
    return library.cmd_restore(args)


if __name__ == "__main__":
    raise SystemExit(main())
