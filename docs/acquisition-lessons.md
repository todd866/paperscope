# PDF acquisition: failure modes and hardening

Field notes from running acquisition at scale (MND review + cross-domain corpora,
2026-05). The theme: **a PDF that downloaded is not a PDF you can trust.** Every
shadow-library and Sci-Hub path silently returns the *wrong* paper often enough
that unverified acquisition quietly poisons a corpus.

A working, verification-gated reference implementation lives at
`~/PaperLibrary/library.py` (`pull`, `pdf_matches_title`, `extract_text`,
`_ocr_pages`, `_is_thin`). The notes below say what to port into
`paperscope/ingest/shadow_library.py` and why.

## Observed failure modes

- **SciDB DOI→MD5 collisions.** A DOI resolves to an unrelated file. Two
  different ALS DOIs once mapped to the *same* MD5 — a 2005 Platelets paper —
  and both were stored. Already mitigated by `resolve_doi_to_md5s` +
  `md5_landing_carries_doi` (the DOI landing-page guard). Good.
- **Sci-Hub returns the wrong paper / not a paper.** `acquire_shadow_pdfs`
  tries Sci-Hub *first* (Stage 3a) and explicitly does **not** guard it. In
  practice Sci-Hub returned a Portuguese literature journal for one Gold-Coast
  DOI, and HTML interstitials for others. **Gap: the unguarded first stage is
  the least trustworthy one.**
- **Scanned image-only PDFs.** Pre-~2000 papers (e.g. Brooks 1994; Ransohoff
  1978, an image-only NEJM archive scan) have no real text layer, so any
  content check sees nothing and false-rejects a correct file.
- **Watermark-only text layers.** Some scans carry a per-page boilerplate
  watermark ("Downloaded from nejm.org...") that repeats on every page. Raw
  text length clears a naive "is it scanned?" threshold while carrying ~zero
  real content, so OCR never triggers and garbage text gets stored.
- **Landing-page DOI ≠ delivered bytes.** The DOI guard checks the MD5 *landing
  page*, not the downloaded file. The libgen chain can still deliver a wrong or
  truncated PDF. Content-level verification is complementary, not redundant.

## Recommended hardening (port from `library.py`)

1. **Verify delivered PDF content, not just the landing page.** After any
   download (Sci-Hub *and* libgen), check the first ~2 pages' text against the
   expected title; accept only on a match ratio ≥ ~0.45. See
   `pdf_matches_title`. This is the single highest-value guard and it closes the
   unguarded-Sci-Hub hole. Requires carrying the expected `title` in each record.
2. **OCR fallback before rejecting.** When the text-layer match is low, OCR the
   first 2 pages (tesseract via PyMuPDF rasterization) and re-judge; only then
   reject. Store OCR'd text for scans so downstream charting isn't blank.
3. **Detect "thin" by *unique* tokens, not raw length** — so repeated
   watermarks don't mask an image-only PDF (`_is_thin`).
4. **Member `fast_download` (optional, fast path).** The libgen.li chain is
   slow and rate-limited (50 files / 300 s). With an Anna's membership key:
   `GET {base}/dyn/api/fast_download.json?md5=<md5>&key=<key>` → JSON
   `{download_url}`. Read the key from env only, never persist it.

## Working cascade order (most reliable first)

1. **Unpaywall / green-OA** (`open_access.acquire_oa_pdfs`) — legal, reliable;
   catches MDPI/BMC/PMC and repository copies (Aarhus `pure.au.dk`, Bologna IRIS).
2. **Anna's member `fast_download`** over *every* SciDB MD5 candidate, content-verified.
3. **libgen.li chain**, content-verified.
4. **Sci-Hub**, content-verified (do not trust unguarded).
5. **Institutional (USyd EZProxy) via a browser** — the tail route for genuinely
   paywalled papers. `https://doi-org.ezproxy.library.usyd.edu.au/<doi>` with a
   live OpenAthens session; fetch the PDF from inside the authenticated tab and
   blob-download it. Handles T&F, ScienceDirect (incl. 1994 supplements), etc.
   Out of scope for this requests-based module, but it's the documented escalation
   and it means "can't get it" is rare. Notes: same-origin `fetch(location.href)`
   inherits the session; ScienceDirect's `pdfft` link returns an interstitial to
   `fetch()` and must be opened (View PDF → new tab → fetch there); the browser
   tool blocks JS that returns cookie/query-string data, so don't return the
   tokenized URL — fetch and download inside the page and return only a status.
