"""PDF acquisition for systematic-review included sets.

A thin SR-side wrapper around `paperscope.ingest` that:
  1. Reads the review's included.jsonl (or records.jsonl)
  2. Pulls open-access PDFs via Unpaywall (`ingest.open_access.acquire_oa_pdfs`)
  3. Writes an EZProxy queue for the paywalled tail
  4. Reports coverage: N OA / N queued / N no-DOI / N cached

Stores PDFs as `<corpus_dir>/papers/<pmid>.pdf` and extracted text as
`<corpus_dir>/text/<pmid>.txt`. Same shape as paperscope's per-paper library
but keyed by PMID (the SR pipeline's natural identifier) instead of cite_key.

## Two-stage workflow

`acquire` is deliberately split from the browser-driving stage.

Stage 1 (this module, fully automated):
    python -m paperscope.systematic_review acquire myreview.yaml
    -> downloads OA PDFs, writes `<corpus>/ezproxy-queue.json`, reports
       coverage. Idempotent — safe to re-run; already-acquired PDFs are
       skipped, text extraction picks up any new files.

Stage 2 (browser-driving, NOT in this module):
    The EZProxy queue is a plain JSON list of
        {"cite_key", "doi", "title", "ezproxy_url"}
    objects. Walk it with whatever browser automation suits — your own
    playwright/selenium harness, an AI agent driving Chrome, or by hand.
    Drop the downloaded PDFs into `<corpus>/papers/<cite_key>.pdf`. Re-run
    Stage 1 to extract text from them.

    Paperscope does not embed its own browser driver — paywalled access
    requires institutional auth (e.g. OpenAthens), which is a one-click
    human gate in practice. Whatever drives the browser handles that gate;
    paperscope stays a pure queue producer + report-er.
"""

from paperscope.systematic_review.acquire.pipeline import (
    acquire,
    AcquireResult,
    record_to_ref,
    load_ezproxy_queue,
    filter_queue_for_missing,
)
from paperscope.systematic_review.acquire.ezproxy import write_ezproxy_queue

__all__ = [
    "acquire",
    "AcquireResult",
    "record_to_ref",
    "write_ezproxy_queue",
    "load_ezproxy_queue",
    "filter_queue_for_missing",
]
