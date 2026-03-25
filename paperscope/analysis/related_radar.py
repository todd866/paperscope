"""Related radar: find potentially missing related work via OpenAlex."""

from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Set

import numpy as np
import requests

from ..text import clean_latex, extract_cite_keys
from ..text.parsing import extract_paragraphs
from ..embed import embed_texts
from ..embed.similarity import cosine_sim


OPENALEX_BASE = "https://api.openalex.org"
RATE_LIMIT_DELAY = 0.15


def _extract_keywords_from_embeddings(
    tex_text: str,
    model=None,
    n_keywords: int = 8,
) -> List[str]:
    """Extract key phrases from the paper for search queries.

    Uses section titles + frequent noun phrases from the abstract.
    """
    keywords: List[str] = []

    # Section titles
    for m in re.finditer(r"\\section\*?\{([^}]+)\}", tex_text):
        title = clean_latex(m.group(1))
        if len(title.split()) <= 5:
            keywords.append(title)

    # Abstract keywords
    abstract_m = re.search(
        r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex_text, re.DOTALL
    )
    if abstract_m:
        abstract = clean_latex(abstract_m.group(1))
        # Simple keyword extraction: 2-3 word phrases
        words = abstract.split()
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i + 1]}"
            if len(bigram) > 8 and bigram[0].islower():
                keywords.append(bigram)

    # Title
    title_m = re.search(r"\\title\{([^}]+)\}", tex_text)
    if title_m:
        keywords.insert(0, clean_latex(title_m.group(1)))

    return keywords[:n_keywords]


def _search_openalex(
    query: str,
    n: int = 25,
    email: str = "paperscope@example.com",
) -> List[Dict]:
    """Search OpenAlex for works matching a query."""
    params = {
        "search": query,
        "per_page": min(n, 200),
        "sort": "relevance_score:desc",
        "filter": "has_abstract:true",
        "mailto": email,
    }
    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except requests.RequestException:
        return []


def _reconstruct_abstract(work: dict) -> str:
    """Reconstruct abstract from OpenAlex inverted index."""
    inverted = work.get("abstract_inverted_index")
    if not inverted:
        return ""
    word_positions = []
    for word, positions in inverted.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def related_radar(
    tex_text: str,
    literature_dir: Optional[str] = None,
    n_results: int = 50,
    email: str = "paperscope@example.com",
    model=None,
) -> Dict:
    """Find potentially missing related work by searching OpenAlex.

    Extracts keywords from the paper, searches for similar works,
    filters out papers already in the bibliography, and ranks by
    semantic similarity.

    Args:
        tex_text: Raw LaTeX source.
        literature_dir: Optional path to check for already-downloaded texts.
        n_results: Target number of candidate papers.
        email: Email for OpenAlex polite pool.
        model: Pre-loaded embedding model.

    Returns:
        Dict with ``candidates`` (ranked missing references),
        ``keywords_used``, and ``stats``.
    """
    def _normalize_doi(doi: str) -> str:
        """Normalize DOI to bare form (no URL prefix)."""
        d = doi.lower().strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if d.startswith(prefix):
                d = d[len(prefix):]
        return d

    # Get existing bibliography keys
    existing_keys: Set[str] = set(extract_cite_keys(tex_text))

    # Build set of already-known DOIs from literature_dir if provided
    known_dois: Set[str] = set()
    known_titles: Set[str] = set()
    if literature_dir:
        from pathlib import Path
        lit_path = Path(literature_dir)
        # Check for bibliography.json
        bib_path = lit_path / "bibliography.json"
        if not bib_path.exists():
            bib_path = lit_path.parent / "bibliography.json"
        if bib_path.exists():
            import json
            try:
                with open(bib_path) as f:
                    bib_data = json.load(f)
                refs = bib_data.get("references", bib_data) if isinstance(bib_data, dict) else bib_data
                for ref in refs:
                    if ref.get("doi"):
                        known_dois.add(_normalize_doi(ref["doi"]))
                    if ref.get("title"):
                        known_titles.add(ref["title"].lower().strip()[:80])
            except (json.JSONDecodeError, KeyError):
                pass
        # Also count text files as known
        text_dir = lit_path / "text" if (lit_path / "text").is_dir() else lit_path
        for txt in text_dir.glob("*.txt"):
            existing_keys.add(txt.stem)

    # Extract search keywords
    keywords = _extract_keywords_from_embeddings(tex_text, model=model)
    if not keywords:
        return {"error": "No keywords extracted"}

    # Search OpenAlex
    all_works: Dict[str, dict] = {}  # DOI -> work
    for kw in keywords:
        print(f"  Searching: {kw}")
        works = _search_openalex(kw, n=n_results // len(keywords) + 5, email=email)
        for w in works:
            doi = w.get("doi", "")
            if doi and doi not in all_works:
                all_works[doi] = w

    if not all_works:
        return {"error": "No results from OpenAlex", "keywords_used": keywords}

    # Build candidate list with abstracts
    candidates: List[Dict] = []
    candidate_abstracts: List[str] = []
    for doi, work in all_works.items():
        abstract = _reconstruct_abstract(work)
        if not abstract or len(abstract.split()) < 20:
            continue

        title = work.get("title", "")
        year = work.get("publication_year")

        # Check if already known by DOI (normalize to handle URL-form OpenAlex DOIs)
        if _normalize_doi(doi) in known_dois:
            continue

        # Check if already known by title
        if title and title.lower().strip()[:80] in known_titles:
            continue

        # Check if already cited by cite key match
        title_lower = title.lower() if title else ""
        already_cited = any(
            key.lower().replace("_", " ") in title_lower
            for key in existing_keys
            if len(key) > 5
        )
        if already_cited:
            continue

        candidates.append({
            "title": title,
            "doi": doi,
            "year": year,
            "authors": _format_authors(work),
            "source": work.get("primary_location", {}).get("source", {}).get("display_name", ""),
        })
        candidate_abstracts.append(abstract)

    if not candidates:
        return {
            "candidates": [],
            "keywords_used": keywords,
            "stats": {"n_searched": len(all_works), "n_after_filter": 0},
        }

    # Embed paper and candidates
    paras = extract_paragraphs(tex_text)
    paper_texts = [p["text"][:500] for p in paras] if paras else [clean_latex(tex_text)[:2000]]
    all_texts = paper_texts + candidate_abstracts
    emb, backend = embed_texts(all_texts, model=model, show_progress=False)
    paper_emb = emb[: len(paper_texts)]
    cand_emb = emb[len(paper_texts) :]

    # Rank by max similarity to any paper paragraph
    paper_centroid = np.mean(paper_emb, axis=0, keepdims=True)
    sims = cosine_sim(paper_centroid, cand_emb)[0]

    for i, cand in enumerate(candidates):
        cand["relevance_score"] = float(sims[i])

    candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
    candidates = candidates[:n_results]

    return {
        "candidates": candidates,
        "keywords_used": keywords,
        "stats": {
            "n_searched": len(all_works),
            "n_after_filter": len(candidate_abstracts),
            "n_returned": len(candidates),
        },
        "backend": backend,
    }


def _format_authors(work: dict) -> str:
    """Format author list from OpenAlex work."""
    authorships = work.get("authorships", [])
    names = []
    for a in authorships[:3]:
        author = a.get("author", {})
        name = author.get("display_name", "")
        if name:
            names.append(name)
    result = ", ".join(names)
    if len(authorships) > 3:
        result += f" et al. ({len(authorships)} authors)"
    return result
