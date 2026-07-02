"""Generate EZProxy download queue for paywalled papers."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

# No institution is baked in: the proxy host comes from this env var or an
# explicit argument / CLI flag, and code that needs one fails loudly otherwise.
EZPROXY_HOST_ENV = "PAPERSCOPE_EZPROXY_HOST"


def resolve_ezproxy_host(ezproxy_host: Optional[str] = None) -> str:
    """Explicit host wins; otherwise fall back to $PAPERSCOPE_EZPROXY_HOST.

    Raises RuntimeError when neither is set.
    """
    host = (ezproxy_host or os.environ.get(EZPROXY_HOST_ENV, "")).strip()
    if not host:
        raise RuntimeError(
            "No EZProxy host configured: set PAPERSCOPE_EZPROXY_HOST or pass --ezproxy-host"
        )
    return host


def generate_ezproxy_urls(
    refs: List[Dict],
    ezproxy_host: Optional[str] = None,
) -> List[Dict]:
    """Generate EZProxy URLs for paywalled papers with DOIs.

    Returns list of dicts with cite_key, doi, ezproxy_url.
    """
    queue = []
    host = None

    for ref in refs:
        doi = ref.get("doi", "")
        if not doi:
            continue

        # Resolve lazily so an all-OA batch never demands a proxy host.
        if host is None:
            host = resolve_ezproxy_host(ezproxy_host)
        url = f"https://doi-org.{host}/{doi}"
        queue.append({
            "cite_key": ref["cite_key"],
            "doi": doi,
            "title": ref.get("title", ""),
            "ezproxy_url": url,
        })

    return queue


def write_queue(
    refs: List[Dict],
    output_path: Path,
    ezproxy_host: Optional[str] = None,
) -> int:
    """Write a download queue file for browser-automated acquisition.

    Args:
        refs: List of reference dicts (from bibliography.json)
        output_path: Path to write the queue JSON
        ezproxy_host: EZProxy hostname (default: $PAPERSCOPE_EZPROXY_HOST)

    Returns:
        Number of items in queue
    """
    queue = generate_ezproxy_urls(refs, ezproxy_host)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(queue, f, indent=2)

    return len(queue)
