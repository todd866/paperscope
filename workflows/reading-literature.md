# Workflow: Reading Literature

## Discovery

Find new papers matching your research profile:

```bash
python3 -m paperscope harvest --config config.yaml
```

Outputs a markdown digest at `~/Papers/harvester/inbox/YYYY-MM-DD/digest.md` summarising recent papers from OpenAlex / arXiv / bioRxiv. Triage there — keep what's relevant, archive the rest.

## Acquisition + text extraction

Once you have a `bibliography.json` (built by `extract` + `resolve`), pull PDFs and extract text in one pass:

```bash
python3 -m paperscope ingest /path/to/literature/
```

This:
1. Asks Unpaywall for open-access PDFs for every DOI and downloads what it can
2. Generates an EZProxy queue (`browser-queue.json`) for the paywalled tail — whatever browser automation you use walks it through institutional auth
3. Runs PyMuPDF on every PDF to produce `text/<cite_key>.txt`
4. Optionally uploads PDFs to B2 if `--upload-b2` and `B2_APPLICATION_KEY*` are set

You need a real `PAPERSCOPE_EMAIL` env var (Unpaywall rejects polite-pool calls without one).

## Depth-2 harvesting

Once your bibliography is built, you can harvest references-of-references:

```bash
python3 -m paperscope depth2 /path/to/literature/
```

For each DOI in `bibliography.json`, queries CrossRef for its reference list, adds new references as depth-2 entries, resolves their DOIs, and queues them for acquisition. Captures the extended intellectual neighbourhood (~10–15k refs for a typical paper program).

## Systematic-review reading

If you're running a scoping/systematic review rather than reading-for-a-paper, see `paperscope/systematic_review/`:

```bash
# For an SR with an included.jsonl set:
python3 -m paperscope.systematic_review acquire myreview.yaml
```

That runs the same OA pull + EZProxy queue logic but keyed on the SR's PMID-based identifiers, and slots PDFs/text into the review's corpus directory.
