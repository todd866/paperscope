"""Generate EZProxy download queue for paywalled papers."""

import json
from pathlib import Path
from typing import Dict, List


def generate_ezproxy_urls(
    refs: List[Dict],
    ezproxy_host: str = "ezproxy.library.usyd.edu.au",
) -> List[Dict]:
    """Generate EZProxy URLs for paywalled papers with DOIs.

    Returns list of dicts with cite_key, doi, ezproxy_url.
    """
    queue = []

    for ref in refs:
        doi = ref.get("doi", "")
        if not doi:
            continue

        url = f"https://doi-org.{ezproxy_host}/{doi}"
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
    ezproxy_host: str = "ezproxy.library.usyd.edu.au",
) -> int:
    """Write a download queue file for browser-automated acquisition.

    Args:
        refs: List of reference dicts (from bibliography.json)
        output_path: Path to write the queue JSON
        ezproxy_host: EZProxy hostname

    Returns:
        Number of items in queue
    """
    queue = generate_ezproxy_urls(refs, ezproxy_host)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(queue, f, indent=2)

    return len(queue)
