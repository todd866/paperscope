"""Method resolution analysis: detect mismatches between method resolving power and conclusions.

The core question: does the method have the resolving power to distinguish
the hypotheses the paper claims to address?  A genome-wide selection scan
cannot speak to site-specific manipulation; an aggregate demographic model
cannot ground claims about individual trajectories.  This module flags such
gaps using keyword-based resolution scoring and embedding-based grounding
checks.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..text import clean_latex, split_sentences
from ..embed import embed_texts
from ..embed.similarity import cosine_sim


# ---------------------------------------------------------------------------
# Resolution taxonomy
# ---------------------------------------------------------------------------

RESOLUTION_LEVELS = {
    "genome_wide": {"scope": "entire genome/dataset", "granularity": "aggregate", "level": 1},
    "gene_wide": {"scope": "per gene/region", "granularity": "regional", "level": 2},
    "site_specific": {"scope": "individual sites/positions", "granularity": "fine", "level": 3},
    "aggregate": {"scope": "population/group level", "granularity": "aggregate", "level": 1},
    "subgroup": {"scope": "subpopulation level", "granularity": "regional", "level": 2},
    "individual": {"scope": "individual level", "granularity": "fine", "level": 3},
    "temporal_coarse": {"scope": "epoch/era", "granularity": "aggregate", "level": 1},
    "temporal_medium": {"scope": "year/generation", "granularity": "regional", "level": 2},
    "temporal_fine": {"scope": "day/event", "granularity": "fine", "level": 3},
}


# ---------------------------------------------------------------------------
# Keyword lexicons for resolution detection
# ---------------------------------------------------------------------------

AGGREGATE_INDICATORS: List[str] = [
    "genome-wide", "global", "overall", "distribution", "average",
    "aggregate", "population-level", "mean", "systematic", "general",
    "across all", "whole-genome", "net effect", "broad-scale",
    "summary statistic", "bulk", "pooled", "composite", "index",
    "parameter", "proportion", "frequency", "prevalence",
    "epoch", "era", "macro", "trend",
]

SPECIFIC_INDICATORS: List[str] = [
    "site-specific", "individual", "particular", "specific mutation",
    "single nucleotide", "insertion", "deletion", "indel", "position",
    "residue", "codon", "targeted", "engineered", "designed",
    "particular site", "specific change", "point mutation",
    "substitution", "amino acid", "nucleotide", "base pair",
    "locus", "allele", "variant", "haplotype",
    "case-level", "patient-level", "per-subject", "single-cell",
    "event-level", "time-point", "instantaneous",
]

# Additional method-specific keywords that signal aggregate resolution
METHOD_AGGREGATE_SIGNALS: List[str] = [
    "single parameter", "one parameter", "K parameter", "omega ratio",
    "dN/dS", "dn/ds", "selection intensity distribution",
    "mean-field", "regression coefficient", "correlation",
    "principal component", "factor analysis", "clustering",
    "logistic regression", "Cox model", "survival curve",
    "ANOVA", "t-test", "chi-square", "Kolmogorov",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_sentences(text: str) -> List[str]:
    """Split text into sentences, handling both LaTeX and plain text."""
    cleaned = clean_latex(text) if "\\" in text else text
    # Split on sentence boundaries
    sents = split_sentences(cleaned)
    # Further split very long "sentences" that may be multi-sentence paragraphs
    result: List[str] = []
    for s in sents:
        if len(s.split()) > 60:
            sub = re.split(r"(?<=[.!?])\s+", s)
            result.extend(part.strip() for part in sub if part.strip())
        else:
            if s.strip():
                result.append(s.strip())
    return result


def _keyword_score(
    text: str,
    keywords: List[str],
) -> Tuple[float, List[str]]:
    """Score how many keywords from a list appear in text.

    Returns (score_0_to_1, list_of_matched_phrases).
    """
    text_lower = text.lower()
    matched: List[str] = []
    for kw in keywords:
        if kw.lower() in text_lower:
            matched.append(kw)
    # Normalize: saturate at 5 matches for a score of 1.0
    score = min(len(matched) / 5.0, 1.0) if keywords else 0.0
    return score, matched


def _resolution_scores(sentences: List[str]) -> Dict:
    """Compute aggregate and specific resolution scores across sentences.

    Returns dict with aggregate_score, specific_score, detected_level,
    key_phrases.
    """
    all_text = " ".join(sentences)
    agg_score, agg_phrases = _keyword_score(
        all_text, AGGREGATE_INDICATORS + METHOD_AGGREGATE_SIGNALS
    )
    spec_score, spec_phrases = _keyword_score(all_text, SPECIFIC_INDICATORS)

    # Determine detected level
    if spec_score > agg_score + 0.1:
        detected = _best_level("fine")
    elif agg_score > spec_score + 0.1:
        detected = _best_level("aggregate")
    else:
        detected = _best_level("regional")

    return {
        "aggregate_score": round(float(agg_score), 3),
        "specific_score": round(float(spec_score), 3),
        "detected_level": detected,
        "key_phrases": list(set(agg_phrases + spec_phrases)),
    }


def _best_level(granularity: str) -> str:
    """Return the first RESOLUTION_LEVELS key matching a granularity."""
    for name, info in RESOLUTION_LEVELS.items():
        if info["granularity"] == granularity:
            return name
    return "aggregate"


def _level_number(level_name: str) -> int:
    """Return the numeric level (1=coarse, 3=fine) for a resolution level."""
    return RESOLUTION_LEVELS.get(level_name, {}).get("level", 1)


def _severity(method_level: int, conclusion_level: int) -> str:
    """Determine mismatch severity from numeric levels."""
    gap = conclusion_level - method_level
    if gap <= 0:
        return "none"
    elif gap == 1:
        return "medium"
    else:
        return "high"


def _generate_blind_spots(
    method_sentences: List[str],
    conclusion_sentences: List[str],
    method_res: Dict,
    conclusion_res: Dict,
) -> List[str]:
    """Identify specific blind spots: things the conclusion claims that
    the method cannot resolve."""
    blind_spots: List[str] = []
    conc_text = " ".join(conclusion_sentences).lower()
    meth_text = " ".join(method_sentences).lower()

    # Indel detection
    if any(w in conc_text for w in ["insertion", "deletion", "indel"]):
        if not any(w in meth_text for w in ["insertion", "deletion", "indel", "gap"]):
            blind_spots.append(
                "Cannot detect insertions/deletions (indels)"
            )

    # Site-specific vs genome-wide
    if any(w in conc_text for w in ["site-specific", "specific site", "particular site",
                                     "individual site"]):
        if method_res["aggregate_score"] > 0.3:
            blind_spots.append(
                "Cannot resolve individual site changes against genome-wide background"
            )

    # Individual vs population
    if any(w in conc_text for w in ["individual", "case-level", "patient", "per-subject"]):
        if any(w in meth_text for w in ["population", "aggregate", "cohort", "pooled"]):
            blind_spots.append(
                "Population-level method cannot ground individual-level claims"
            )

    # Temporal precision
    if any(w in conc_text for w in ["event", "time-point", "instantaneous", "moment"]):
        if any(w in meth_text for w in ["epoch", "era", "trend", "longitudinal"]):
            blind_spots.append(
                "Temporal resolution too coarse for event-level conclusions"
            )

    # Causal claims from correlational methods
    causal_words = ["caused", "causes", "causal", "driving", "drove", "led to",
                    "resulted in", "produced", "generated"]
    correlational_words = ["correlation", "associated", "regression", "covariate",
                           "observational", "cross-sectional"]
    if any(w in conc_text for w in causal_words):
        if any(w in meth_text for w in correlational_words):
            blind_spots.append(
                "Correlational/observational method cannot ground causal conclusions"
            )

    # Selection direction from rate ratio
    if any(w in conc_text for w in ["manipulation", "engineered", "designed",
                                     "laboratory", "gain-of-function"]):
        if any(w in meth_text for w in ["dn/ds", "omega", "selection intensity",
                                         "selection pressure"]):
            blind_spots.append(
                "Selection-rate methods detect pressure direction, "
                "not mechanism (natural vs engineered)"
            )

    return blind_spots


def _build_explanation(
    method_res: Dict,
    conclusion_res: Dict,
    mismatch_severity: str,
) -> str:
    """Generate a human-readable explanation of the mismatch."""
    if mismatch_severity == "none":
        return "Method resolution appears adequate for the conclusions drawn."

    method_phrases = ", ".join(method_res["key_phrases"][:3]) or "unspecified"
    conc_phrases = ", ".join(conclusion_res["key_phrases"][:3]) or "unspecified"

    return (
        f"Method operates at {method_res['detected_level'].replace('_', '-')} "
        f"resolution ({method_phrases}) but conclusions address "
        f"{conclusion_res['detected_level'].replace('_', '-')} questions "
        f"({conc_phrases})"
    )


# ---------------------------------------------------------------------------
# Section extraction helpers
# ---------------------------------------------------------------------------

def _extract_section(text: str, heading_patterns: List[str]) -> str:
    """Extract a section from a LaTeX document by heading pattern.

    Searches for section commands matching any of the patterns and returns
    the text up to the next section command or end of document.
    """
    for pattern in heading_patterns:
        regex = (
            r"\\(?:section|subsection)\*?\{" + pattern + r"\}"
            r"(.*?)"
            r"(?=\\(?:section|subsection)\*?\{|\\bibliography\{|"
            r"\\begin\{thebibliography\}|\Z)"
        )
        m = re.search(regex, text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def _extract_abstract(text: str) -> str:
    """Extract abstract from LaTeX source."""
    m = re.search(
        r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.DOTALL
    )
    return m.group(1) if m else ""


def _extract_methods(text: str) -> str:
    """Extract methods/methodology section."""
    return _extract_section(text, [
        r"[Mm]ethod[s]?",
        r"[Mm]aterials?\s+and\s+[Mm]ethods?",
        r"[Mm]ethodology",
        r"[Aa]nalytical?\s+[Ff]ramework",
        r"[Aa]pproach",
        r"[Mm]odel(?:ing|ling)?",
        r"[Ss]tatistical\s+[Aa]nalysis",
        r"[Cc]omputational\s+[Mm]ethods?",
    ])


def _extract_conclusions(text: str) -> str:
    """Extract conclusion/discussion section."""
    return _extract_section(text, [
        r"[Cc]onclusion[s]?",
        r"[Dd]iscussion",
        r"[Ss]ummary",
        r"[Dd]iscussion\s+and\s+[Cc]onclusion[s]?",
        r"[Cc]oncluding\s+[Rr]emarks?",
    ])


def _extract_results(text: str) -> str:
    """Extract results section."""
    return _extract_section(text, [
        r"[Rr]esults?",
        r"[Ff]indings?",
        r"[Rr]esults?\s+and\s+[Dd]iscussion",
    ])


# ---------------------------------------------------------------------------
# Main API
# ---------------------------------------------------------------------------

def check_resolution_match(
    method_text: str,
    conclusions_text: str,
    results_text: Optional[str] = None,
    mismatch_threshold: float = 0.35,
    model=None,
) -> Dict:
    """Detect resolution mismatches between methods and conclusions.

    Combines keyword-based resolution scoring with embedding-based grounding
    checks to flag conclusions that the method cannot support at the
    required resolution.

    Args:
        method_text: Methods section text (LaTeX or plain text).
        conclusions_text: Abstract + conclusions text (LaTeX or plain text).
        results_text: Optional results text for additional grounding context.
        mismatch_threshold: Cosine similarity below which a conclusion is
            flagged as ungrounded in the methods.
        model: Pre-loaded sentence-transformers model (optional).

    Returns:
        Dict with ``method_resolution``, ``conclusion_resolution``,
        ``mismatch``, ``grounding_check``, and
        ``overall_resolution_mismatch_score``.
    """
    # --- Sentence extraction ---
    method_sents = _to_sentences(method_text)
    conclusion_sents = _to_sentences(conclusions_text)

    if not method_sents:
        return {"error": "No method sentences extracted"}
    if not conclusion_sents:
        return {"error": "No conclusion sentences extracted"}

    # Optional: incorporate results text into method grounding pool
    grounding_sents = list(method_sents)
    if results_text:
        grounding_sents.extend(_to_sentences(results_text))

    # --- Keyword-based resolution scoring ---
    method_res = _resolution_scores(method_sents)
    conclusion_res = _resolution_scores(conclusion_sents)

    # --- Resolution mismatch ---
    method_level = _level_number(method_res["detected_level"])
    conclusion_level = _level_number(conclusion_res["detected_level"])
    mismatch_severity = _severity(method_level, conclusion_level)
    detected = mismatch_severity != "none"

    blind_spots = _generate_blind_spots(
        method_sents, conclusion_sents, method_res, conclusion_res
    )
    explanation = _build_explanation(method_res, conclusion_res, mismatch_severity)

    # --- Embedding-based grounding check ---
    # Embed conclusion sentences and grounding (method + results) sentences
    all_texts = conclusion_sents + grounding_sents
    embeddings, backend = embed_texts(
        all_texts, model=model, show_progress=False
    )
    n_conc = len(conclusion_sents)
    conc_emb = embeddings[:n_conc]
    ground_emb = embeddings[n_conc:]

    sims = cosine_sim(conc_emb, ground_emb)  # (n_conc, n_ground)

    grounding_results: List[Dict] = []
    ungrounded_count = 0
    for i, sent in enumerate(conclusion_sents):
        # Skip very short or generic sentences
        if len(sent.split()) < 6:
            continue
        best_j = int(np.argmax(sims[i]))
        best_sim = float(sims[i, best_j])
        grounded = best_sim >= mismatch_threshold
        if not grounded:
            ungrounded_count += 1
        grounding_results.append({
            "conclusion": sent[:200],
            "nearest_method": grounding_sents[best_j][:200],
            "similarity": round(best_sim, 3),
            "grounded": grounded,
        })

    # --- Overall mismatch score ---
    # Combine keyword-based mismatch with embedding-based ungrounding
    keyword_mismatch = 0.0
    if detected:
        level_gap = conclusion_level - method_level
        keyword_mismatch = min(level_gap / 2.0, 1.0)

    grounding_frac = (
        ungrounded_count / len(grounding_results)
        if grounding_results else 0.0
    )
    # Weighted combination: keyword mismatch matters more if strong,
    # but grounding fraction catches subtler issues
    overall = 0.6 * keyword_mismatch + 0.4 * grounding_frac
    overall = round(min(overall, 1.0), 3)

    return {
        "method_resolution": method_res,
        "conclusion_resolution": conclusion_res,
        "mismatch": {
            "detected": detected,
            "severity": mismatch_severity,
            "explanation": explanation,
            "method_blind_spots": blind_spots,
        },
        "grounding_check": grounding_results,
        "overall_resolution_mismatch_score": overall,
        "backend": backend,
    }


def check_resolution_from_tex(
    tex_text: str,
    mismatch_threshold: float = 0.35,
    model=None,
) -> Dict:
    """Convenience wrapper: extract sections from LaTeX and run the check.

    Args:
        tex_text: Full LaTeX source of the paper.
        mismatch_threshold: Similarity threshold for grounding check.
        model: Pre-loaded embedding model.

    Returns:
        Same dict as :func:`check_resolution_match`, with an additional
        ``sections_found`` field listing which sections were located.
    """
    abstract = _extract_abstract(tex_text)
    methods = _extract_methods(tex_text)
    conclusions = _extract_conclusions(tex_text)
    results = _extract_results(tex_text)

    sections_found = {
        "abstract": bool(abstract),
        "methods": bool(methods),
        "conclusions": bool(conclusions),
        "results": bool(results),
    }

    # Build the inputs
    method_text = methods
    if not method_text:
        # Fallback: some papers embed methods in other sections
        return {
            "error": "No methods section found",
            "sections_found": sections_found,
        }

    conclusions_text = " ".join(filter(None, [abstract, conclusions]))
    if not conclusions_text.strip():
        return {
            "error": "No abstract or conclusions section found",
            "sections_found": sections_found,
        }

    result = check_resolution_match(
        method_text=method_text,
        conclusions_text=conclusions_text,
        results_text=results or None,
        mismatch_threshold=mismatch_threshold,
        model=model,
    )
    result["sections_found"] = sections_found
    return result
