# PDF acquisition: what ships, and the shadow boundary

paperscope acquires PDFs in ordered phases, most-reliable first. The **open-access
phases ship and work out of the box.** The optional last-resort ("shadow") phase is
**intentionally not part of the public build** — you bring your own provider.

## What ships and works

- **Open-access acquisition** — `paperscope.ingest.open_access.acquire_oa_pdfs`.
  Resolves a DOI through Unpaywall, follows publisher open-access / green-OA and
  repository copies, and downloads the PDF. This is the primary path and covers a
  large share of the biomedical literature on its own.
- **Content verification** — `paperscope.ingest.shadow_library.pdf_matches_title`.
  A downloaded PDF is not automatically a PDF you can trust; any source can
  occasionally hand back an unrelated paper or an HTML error page. This helper
  matches the delivered bytes' own text (with an OCR fallback for scanned files)
  against the expected title. It ships, and every acquisition path — including any
  provider you supply — should run its output through it.
- **Institutional escalation (EZProxy)** — the pipeline writes an EZProxy work
  queue for the genuinely-paywalled tail so those DOIs can be fetched through your
  institution's authenticated session. This is the sanctioned route for papers
  that have no legal open copy.

Together these cover the overwhelming majority of retrievable papers.

## What does NOT ship: shadow acquisition

Some papers have no open-access copy and no institutional route. A "shadow"
last-resort provider is where a pipeline would go next. **The public build ships no
such provider.** The seam exists, but the implementation does not:

```python
from paperscope.ingest.shadow_library import acquire_shadow_pdfs

acquire_shadow_pdfs(...)   # raises NotImplementedError in this build
```

This is a deliberate boundary, not an oversight or a TODO. The public project stops
at open, legal acquisition. If you have a lawful reason and route to go further,
that is your call to make and your code to write.

## Bringing your own provider

The pipeline only reaches shadow acquisition when you explicitly opt in
(`enable_shadow_library=True`), and only for records the open-access phase did not
already satisfy. To fill in the last-resort phase, implement a drop-in replacement
for `acquire_shadow_pdfs` and point the pipeline at it.

**Interface.** Implement a callable with this shape:

```python
def acquire_shadow_pdfs(
    records,          # iterable of dicts; each has at least a "doi", and a
                      # "title" (used for the content gate) and an id field
    out_dir,          # pathlib.Path; write "<id>.pdf" here on success
    id_key="pmid",    # which record field names the output file
    pace_s=0.0,       # polite delay between fetches
    log_path=None,    # optional JSONL fetch log
    verify_title=True,# run pdf_matches_title on delivered bytes; delete non-matches
    verbose=False,
):
    ...
    return report      # object exposing the counters below
```

Return a report object exposing these integer counters (the pipeline copies them
into its run report):

- `fetched` — PDFs successfully written and (if `verify_title`) content-verified
- `no_md5` / `no_pdf` — records the provider could not resolve or download
- `doi_mismatch` / `title_mismatch` — records rejected by the guards
- `already_have` — records skipped because the file already existed

**Obligations of a well-behaved provider:**

1. **Only touch what you're allowed to.** Acquire lawfully; respect the source's
   terms and any rate limits. Read credentials from the environment; never persist
   or commit them.
2. **Verify content, don't trust the transport.** Run `pdf_matches_title` on the
   downloaded bytes and delete anything that fails, so a wrong-paper delivery can't
   poison the corpus. Record it as `title_mismatch` rather than storing it.
3. **Be recall-preserving.** A mismatch on one route should fall through to the
   next candidate, not terminate the record.
4. **Fail closed.** If you have no provider configured, leave the stub in place —
   `NotImplementedError` is the correct behaviour, and the open-access phases work
   without it.

Wire your implementation in wherever the pipeline imports
`acquire_shadow_pdfs` (see `paperscope/systematic_review/acquire/pipeline.py`,
Phase 1.5). Field notes on acquisition failure modes and the content gate live in
`docs/acquisition-lessons.md`.
