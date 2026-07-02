"""MEDLINE harvest via NCBI E-utilities. Keyless, polite-pool, no auth.

Generic port of the source review's `harvest_corpus.py`: takes a SearchConfig with
named query blocks + filters and produces a records.jsonl. The block
composition is C1 (population) AND (C2_* OR C3_* OR ...) — i.e. the population
is required, the rest is a permissive OR. This is the standard structure for
the JBI scoping-review searches the module was extracted from.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from paperscope.systematic_review.config import SearchConfig

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
POLITE_DELAY_S = 0.4  # ~2.5 req/s — well inside NCBI's 3/s anonymous limit


def compose_query(search: SearchConfig) -> str:
    """Compose the full Boolean from named blocks.

    The first block (by key prefix `C1_`) is treated as the population
    requirement; all other blocks are OR-ed and ANDed against it. If
    `search.full_query` is non-empty, it is returned as-is.
    """
    if search.full_query.strip():
        return search.full_query
    blocks = search.query_blocks
    if not blocks:
        raise ValueError("SearchConfig has neither full_query nor query_blocks")
    pop_keys = [k for k in blocks if k.startswith("C1") or k.lower().startswith("c1")]
    if not pop_keys:
        # No explicit population block — treat the first block as population
        pop_keys = [next(iter(blocks))]
    pop = " OR ".join(blocks[k] for k in pop_keys)
    rest_keys = [k for k in blocks if k not in pop_keys]
    if rest_keys:
        rest = " OR ".join(blocks[k] for k in rest_keys)
        body = f"({pop}) AND ({rest})"
    else:
        body = f"({pop})"
    filters = search.filters.strip()
    if not filters and len(search.date_range) == 2:
        # If the caller didn't put a year filter in `filters`, fall back to
        # the declarative `date_range`. If both are set, `filters` wins (date_range
        # is ignored) so the explicit string is always canonical.
        a, b = search.date_range
        filters = f"{a}:{b}[pdat]"
    if filters:
        body = f"{body} AND {filters}"
    return body


def _get(url: str, retries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed after {retries + 1} attempts: {last}")


def esearch(term: str, *, usehistory: bool = False) -> dict:
    params: dict = {"db": "pubmed", "term": term, "retmode": "json", "retmax": 0}
    if usehistory:
        params["usehistory"] = "y"
    url = f"{EUTILS}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    data = json.loads(_get(url))
    time.sleep(POLITE_DELAY_S)
    return data["esearchresult"]


def block_counts(search: SearchConfig) -> dict[str, int]:
    """Per-concept-block counts (each AND population AND filters).

    Useful for seeing where corpus volume is coming from before harvesting.
    Returns a dict of block_name → record count. Requires `query_blocks` —
    a `full_query`-only config cannot be decomposed into blocks.
    """
    blocks = search.query_blocks
    if not blocks:
        raise ValueError(
            "block_counts requires SearchConfig.query_blocks; "
            "a full_query-only config has no blocks to count."
        )
    pop_keys = [k for k in blocks if k.startswith("C1") or k.lower().startswith("c1")]
    if not pop_keys:
        pop_keys = [next(iter(blocks))]
    pop = " OR ".join(blocks[k] for k in pop_keys)
    counts: dict[str, int] = {}
    for name, block in blocks.items():
        if name in pop_keys:
            continue
        term = f"({pop}) AND ({block})"
        if search.filters.strip():
            term += f" AND {search.filters}"
        counts[name] = int(esearch(term)["count"])
    return counts


def _parse_article(art: ET.Element) -> dict | None:
    medline = art.find(".//MedlineCitation")
    if medline is None:
        return None
    pmid_el = medline.find("PMID")
    article = medline.find("Article")
    if pmid_el is None or article is None:
        return None
    pmid = pmid_el.text or ""

    title_el = article.find("ArticleTitle")
    title = "".join(title_el.itertext()).strip() if title_el is not None else ""

    abstract_parts: list[str] = []
    for ab in article.findall(".//Abstract/AbstractText"):
        label = ab.get("Label")
        txt = "".join(ab.itertext()).strip()
        abstract_parts.append(f"{label}: {txt}" if label else txt)
    abstract = " ".join(abstract_parts)

    journal_el = article.find(".//Journal/Title")
    journal = journal_el.text if journal_el is not None else ""

    year_el = article.find(".//JournalIssue/PubDate/Year")
    if year_el is None:
        md = article.find(".//JournalIssue/PubDate/MedlineDate")
        year = md.text[:4] if md is not None and md.text else ""
    else:
        year = year_el.text or ""

    authors: list[str] = []
    for a in article.findall(".//AuthorList/Author"):
        last = a.find("LastName")
        init = a.find("Initials")
        if last is not None:
            authors.append(
                f"{last.text} {init.text}" if init is not None else (last.text or "")
            )

    doi = ""
    # The article's OWN doi only: ELocationID first, then the article's own
    # ArticleIdList (a direct child of PubmedData). A recursive .//ArticleIdList
    # ALSO matches every cited reference's ArticleIdList under PubmedData/
    # ReferenceList, whose DOI would clobber the article's own and silently
    # mis-DOI ~1 in 4 records (those whose PubMed record carries reference DOIs).
    for el in article.findall("ELocationID"):
        if el.get("EIdType") == "doi" and el.text:
            doi = el.text
            break
    if not doi:
        idlist = art.find("PubmedData/ArticleIdList")
        if idlist is not None:
            for aid in idlist.findall("ArticleId"):
                if aid.get("IdType") == "doi" and aid.text:
                    doi = aid.text
                    break

    pubtypes = [
        pt.text
        for pt in article.findall(".//PublicationTypeList/PublicationType")
        if pt.text
    ]
    mesh = [
        mh.find("DescriptorName").text  # type: ignore[union-attr]
        for mh in medline.findall(".//MeshHeadingList/MeshHeading")
        if mh.find("DescriptorName") is not None
    ]

    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "journal": journal,
        "year": year,
        "authors": authors,
        "doi": doi,
        "pub_types": pubtypes,
        "mesh": mesh,
    }


def harvest(
    search: SearchConfig,
    out_path: str | Path,
    *,
    batch_size: int = 200,
    progress: bool = True,
) -> int:
    """Run the full broadened query, efetch in batches, write records.jsonl.

    Returns the number of unique records written.
    """
    term = compose_query(search)
    res = esearch(term, usehistory=True)
    total = int(res["count"])
    webenv, qkey = res["webenv"], res["querykey"]

    records: dict[str, dict] = {}
    for start in range(0, total, batch_size):
        params = {
            "db": "pubmed",
            "query_key": qkey,
            "WebEnv": webenv,
            "retstart": start,
            "retmax": batch_size,
            "retmode": "xml",
        }
        url = f"{EUTILS}/efetch.fcgi?{urllib.parse.urlencode(params)}"
        xml_bytes = _get(url)
        root = ET.fromstring(xml_bytes)
        for art in root.findall(".//PubmedArticle"):
            rec = _parse_article(art)
            if rec and rec["pmid"]:
                records[rec["pmid"]] = rec
        if progress:
            print(f"  {min(start + batch_size, total):>7,} / {total:,}", end="\r")
        time.sleep(POLITE_DELAY_S)
    if progress:
        print()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for pmid in sorted(records, key=lambda p: int(p) if p.isdigit() else 10**18):
            f.write(json.dumps(records[pmid], ensure_ascii=False) + "\n")
    return len(records)
