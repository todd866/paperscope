"""EZProxy queue generation for paywalled SR records.

Thin wrapper around `paperscope.ingest.browser_queue` that adapts to the SR
pipeline's record shape (`pmid` + `doi`) and writes the queue inside the
review's corpus directory.
"""

from __future__ import annotations

import json
from pathlib import Path

from paperscope.ingest.browser_queue import generate_ezproxy_urls


def write_ezproxy_queue(
    paywalled_records: list[dict],
    output_path: str | Path,
    *,
    ezproxy_host: str | None = None,
) -> int:
    """Write an EZProxy download queue for the paywalled records.

    Each record needs `pmid` and `doi`. The queue entries are dicts with
    `cite_key` (= pmid), `doi`, `title`, and `ezproxy_url`. The proxy host
    defaults to $PAPERSCOPE_EZPROXY_HOST; with neither set, queueing any
    record with a DOI raises RuntimeError.

    Returns the number of queued items.
    """
    # Adapt SR record shape to ingest.browser_queue's expected shape:
    # pmid → cite_key (the SR pipeline keys by PMID).
    adapted = [
        {
            "cite_key": r["pmid"],
            "doi": r.get("doi", ""),
            "title": r.get("title", ""),
        }
        for r in paywalled_records
        if r.get("doi")
    ]

    queue = generate_ezproxy_urls(adapted, ezproxy_host=ezproxy_host)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(queue, indent=2, ensure_ascii=False))
    return len(queue)
