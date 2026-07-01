"""Journal targeting: rank journals by semantic fit to a paper."""

from __future__ import annotations

import time
from typing import Dict, List, Optional

import numpy as np
import requests

from ..text import clean_latex
from ..text.parsing import extract_paragraphs
from ..embed import embed_texts
from ..embed.similarity import cosine_sim


OPENALEX_BASE = "https://api.openalex.org"
RATE_LIMIT_DELAY = 0.15


def fetch_journal_abstracts(
    journal_query: str,
    n: int = 100,
    email: str = "paperscope@example.com",
) -> List[str]:
    """Fetch recent abstracts from a journal via OpenAlex.

    Args:
        journal_query: Journal name or OpenAlex source ID (e.g. "S12345678").
        n: Number of abstracts to fetch (max 200).
        email: Email for polite pool.

    Returns:
        List of abstract strings.
    """
    # First resolve journal name to source ID if needed
    if not journal_query.startswith("S"):
        source_id = _resolve_journal(journal_query, email)
        if not source_id:
            return []
    else:
        source_id = journal_query

    # Fetch recent works from this source
    abstracts: List[str] = []
    per_page = min(n, 200)
    params = {
        "filter": f"primary_location.source.id:{source_id},has_abstract:true",
        "per_page": per_page,
        "sort": "publication_date:desc",
        "mailto": email,
    }
    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        for work in results:
            abstract = _reconstruct_abstract(work)
            if abstract and len(abstract.split()) >= 20:
                abstracts.append(abstract)
    except requests.RequestException:
        pass
    return abstracts


def _resolve_journal(name: str, email: str) -> Optional[str]:
    """Resolve a journal name to an OpenAlex source ID."""
    params = {
        "search": name,
        "per_page": 5,
        "mailto": email,
    }
    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(f"{OPENALEX_BASE}/sources", params=params, timeout=30)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if results:
            return results[0]["id"].split("/")[-1]
    except requests.RequestException:
        pass
    return None


def _reconstruct_abstract(work: dict) -> str:
    """Reconstruct abstract from OpenAlex inverted index format."""
    inverted = work.get("abstract_inverted_index")
    if not inverted:
        return ""
    # Build word list from inverted index
    word_positions: List[tuple] = []
    for word, positions in inverted.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def journal_fit(
    tex_text: str,
    journal_queries: List[str],
    n_per_journal: int = 100,
    email: str = "paperscope@example.com",
    model=None,
) -> Dict:
    """Rank journals by semantic similarity to a paper.

    Embeds paper sections and journal abstracts, computes centroid
    distances.

    Args:
        tex_text: Raw LaTeX source of the paper.
        journal_queries: Journal names or OpenAlex IDs.
        n_per_journal: Abstracts to fetch per journal.
        email: Email for OpenAlex polite pool.
        model: Pre-loaded embedding model.

    Returns:
        Dict with ``rankings`` (sorted by fit) and ``per_section`` breakdown.
    """
    # Extract paper sections
    paras = extract_paragraphs(tex_text)
    if not paras:
        return {"error": "No paragraphs found"}
    paper_texts = [p["text"][:500] for p in paras]
    paper_emb, backend = embed_texts(paper_texts, model=model, show_progress=False)
    paper_centroid = np.mean(paper_emb, axis=0, keepdims=True)

    # Fetch and embed journal abstracts
    rankings: List[Dict] = []
    for journal in journal_queries:
        print(f"  Fetching abstracts for: {journal}")
        abstracts = fetch_journal_abstracts(journal, n=n_per_journal, email=email)
        if not abstracts:
            rankings.append({
                "journal": journal,
                "n_abstracts": 0,
                "fit_score": 0.0,
                "error": "No abstracts found",
            })
            continue

        journal_emb, _ = embed_texts(abstracts, model=model, show_progress=False)
        journal_centroid = np.mean(journal_emb, axis=0, keepdims=True)

        # Overall fit: centroid similarity
        fit = float(cosine_sim(paper_centroid, journal_centroid)[0, 0])

        # Per-paragraph fit distribution
        para_sims = cosine_sim(paper_emb, journal_centroid)[:, 0]
        rankings.append({
            "journal": journal,
            "n_abstracts": len(abstracts),
            "fit_score": fit,
            "min_paragraph_fit": float(np.min(para_sims)),
            "max_paragraph_fit": float(np.max(para_sims)),
            "std_paragraph_fit": float(np.std(para_sims)),
        })

    rankings.sort(key=lambda x: x.get("fit_score", 0), reverse=True)

    return {
        "rankings": rankings,
        "n_paper_paragraphs": len(paras),
        "backend": backend,
    }
