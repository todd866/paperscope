"""JSONL helpers — the data layer for the SR pipeline.

The whole pipeline keeps records, screening decisions, and charted extractions
in JSONL (one JSON object per line). This makes everything diff-able, git-
friendly, and trivially streamable for large corpora.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator


def load_jsonl(path: str | Path) -> list[dict]:
    """Load a JSONL file into a list of dicts. Skips blank lines."""
    path = Path(path)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def iter_jsonl(path: str | Path) -> Iterator[dict]:
    """Stream a JSONL file as dicts — for large corpora where load_jsonl would
    eat memory."""
    path = Path(path)
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def dump_jsonl(
    rows: Iterable[dict], path: str | Path, *, sort_key: str | None = None
) -> int:
    """Write rows to JSONL. Returns the number written. If `sort_key` is given,
    sort by that key first (numeric if the value parses as int, else string)."""
    rows = list(rows)
    if sort_key is not None:
        def _key(r: dict):
            v = r.get(sort_key, "")
            try:
                return (0, int(v))
            except (TypeError, ValueError):
                return (1, str(v))

        rows.sort(key=_key)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def record_id(record: dict) -> str:
    """The stable identifier for a record/decision. Prefers `record_id`, falling
    back to `pmid` then `id`, so the pipeline is not bound to MEDLINE/PMID and
    works for Embase/CINAHL or any source with its own identifier."""
    return str(record.get("record_id") or record.get("pmid") or record.get("id") or "")
