-- Permanent paper library catalog.
-- One row per stored paper. Deduped on any of doi / md5 / pmid: a paper pulled
-- for one project is never fetched again for another.
CREATE TABLE IF NOT EXISTS papers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doi        TEXT,
    md5        TEXT,        -- md5 of the stored PDF bytes (content identity)
    pmid       TEXT,
    title      TEXT,
    authors    TEXT,
    year       INTEGER,
    journal    TEXT,
    cite_key   TEXT,        -- stable slug; the PDF/text are named <cite_key>
    path       TEXT,        -- pdfs/<cite_key>.pdf, relative to the library root ('' if PDF evicted)
    source     TEXT,        -- how acquired: oa | shadow | import
    added_at   TEXT,        -- ISO 8601 timestamp
    -- storage tiering (see storage.py): evict the PDF of cold/cheap entries, keep text/<cite_key>.txt
    last_accessed  TEXT,              -- ISO 8601; stamped on search/text access
    access_count   INTEGER DEFAULT 0,
    pinned         INTEGER DEFAULT 0, -- 1 = never evict
    pdf_evicted    INTEGER DEFAULT 0, -- 1 = PDF deleted, text kept, re-fetchable
    cited_by_count INTEGER            -- optional; lowers eviction score if known
);

-- Dedup keys. Partial uniqueness so the many DOI-less imports don't collide on ''.
CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_doi  ON papers(doi)  WHERE doi  IS NOT NULL AND doi  != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_md5  ON papers(md5)  WHERE md5  IS NOT NULL AND md5  != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_pmid ON papers(pmid) WHERE pmid IS NOT NULL AND pmid != '';
