# PDF acquisition: failure modes and hardening

Field notes from running acquisition at scale. The theme: **a PDF that downloaded
is not a PDF you can trust.** Any acquisition route — even a legitimate publisher
mirror — silently returns the *wrong* paper, or something that is not a paper at
all, often enough that unverified acquisition quietly poisons a corpus.

The public build ships open-access acquisition plus a content-verification gate;
last-resort ("shadow") acquisition is a stub you fill in yourself (see
[`ACQUISITION.md`](ACQUISITION.md)). These notes explain the failure modes the gate
exists to catch, and the verification-gated cascade any provider you add should
follow.

## Observed failure modes

- **Wrong paper / not a paper.** A source hands back an unrelated file, or an HTML
  interstitial (a login wall, a captcha, a "not found" page) served with a PDF
  content-type. The bytes download cleanly and pass every transport-level check;
  only their *content* gives them away.
- **Identifier → file collisions.** A DOI resolves to the wrong file, or two
  distinct DOIs map to the *same* bytes. Once, two unrelated DOIs both resolved to
  a single decades-old paper and both were stored. Checking the identifier's
  landing page does not catch this — the delivered bytes must be checked too.
- **Scanned image-only PDFs.** Pre-~2000 papers are often archive scans with no
  real text layer, so any naive content check sees nothing and false-rejects a
  *correct* file.
- **Watermark-only text layers.** Some scans carry a per-page boilerplate watermark
  ("Downloaded from ...") that repeats on every page. Raw text length clears a
  naive "is it scanned?" threshold while carrying ~zero real content, so a length
  test never triggers OCR and garbage text gets stored.
- **Landing-page metadata ≠ delivered bytes.** Verifying the landing page (its DOI,
  its title) does not guarantee the file behind the download link is the same
  paper, or complete. Content-level verification is complementary to any
  landing-page guard, not redundant with it.

## The content gate (what ships)

`paperscope.ingest.shadow_library.pdf_matches_title` closes these holes by checking
the *delivered bytes* rather than the transport:

1. **Content verification, not just the landing page.** `pdf_matches_title` matches
   the downloaded file's own text (first ~2 pages) against the expected title; a
   non-match deletes the file and records `title_mismatch`. It is wired into
   `acquire_shadow_pdfs(verify_title=True)` after every fetch, so any provider you
   supply runs through it. It is **opt-in per record**: a record with no `title`
   is not content-checked, so existing callers are unaffected.
2. **OCR fallback before rejecting.** When the text-layer match is low,
   `pdf_matches_title` OCRs the first pages (`_ocr_pdf_text`, tesseract via PyMuPDF)
   and re-judges on the higher ratio — so scanned and watermark-only PDFs aren't
   false-rejected. It degrades gracefully to text-layer-only when tesseract is
   absent.
3. **Acronym/gene-aware tokenization.** `_content_tokens` keeps alphanumeric tokens
   of length ≥ 2 (so short acronyms, gene symbols such as `SOD1` or `TDP-43`, and
   numbers survive) minus a small stopword set. A "4+ letters only" rule would
   discard exactly the tokens that identify a short biomedical title.
4. **Guards surfaced in the report.** The acquisition report carries
   `doi_mismatch` and `title_mismatch` counters, so the wrong-paper failures these
   guards catch are visible, not silently dropped.

## Verification-gated cascade (most reliable first)

Order acquisition routes most-reliable-first, and run **every** route's output
through the content gate:

1. **Open access / green-OA** (`open_access.acquire_oa_pdfs`) — legal, reliable;
   catches publisher OA (MDPI, BMC, PMC) and institutional-repository copies. This
   is the primary path and covers a large share of the literature on its own.
2. **Institutional access via your authenticated session** — the sanctioned route
   for the genuinely-paywalled tail. The pipeline writes an EZProxy work queue so
   those DOIs can be fetched through your institution's session.
3. **Bring-your-own last-resort provider** — opt-in only
   (`enable_shadow_library=True`), not shipped, and reached only for records the
   earlier phases did not satisfy. Whatever you implement, verify content and be
   recall-preserving: a mismatch on one route should fall through to the next
   candidate, and a record becomes `title_mismatch` only if *no* route yields the
   right paper.

The lesson underneath all of it: acquisition and verification are one step, not
two. A downloaded file is a *candidate* until its own content says otherwise.
