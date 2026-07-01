"""Overclaiming detection: hedge erosion and scope expansion between paper sections.

Detects when a paper's conclusions are stronger than its results justify via
two strategies:

1. **Hedge erosion** -- hedging language present in results disappears by the
   time claims reach the abstract or conclusions.
2. **Scope expansion** -- conclusion sentences are semantically distant from
   any result sentence, indicating the paper concludes about things it did not
   directly test.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..embed.embed_claims import embed_texts
from ..embed.similarity import cosine_sim
from ..text.parsing import split_sentences

# ---------------------------------------------------------------------------
# Lexical strength taxonomy
# ---------------------------------------------------------------------------

HEDGE_WEAKENERS: List[str] = [
    "may",
    "might",
    "could",
    "possibly",
    "potentially",
    "appears to",
    "suggests",
    "is consistent with",
    "we hypothesize",
    "it is possible that",
    "tends to",
    "seems to",
    "is likely",
    "not inconsistent with",
]

STRENGTH_AMPLIFIERS: List[str] = [
    "demonstrates",
    "proves",
    "shows",
    "establishes",
    "confirms",
    "we show",
    "our results demonstrate",
    "this establishes",
    "is not",
    "rules out",
    "excludes",
    "definitively",
]

CAUSAL_CLAIMS: List[str] = [
    "causes",
    "drives",
    "determines",
    "leads to",
    "results in",
    "is responsible for",
    "underlies",
    "explains",
]

# Pre-compile regex patterns for performance (word-boundary matching,
# case-insensitive).  Multi-word phrases are matched literally; single words
# get \b guards so "may" doesn't match "mayor".

def _compile_patterns(phrases: List[str]) -> List[re.Pattern]:
    """Compile a list of phrases into word-boundary-guarded regexes."""
    patterns = []
    for p in phrases:
        # Escape regex metacharacters, then wrap with word boundaries
        escaped = re.escape(p)
        patterns.append(re.compile(rf"\b{escaped}\b", re.IGNORECASE))
    return patterns


_HEDGE_PATTERNS = _compile_patterns(HEDGE_WEAKENERS)
_AMP_PATTERNS = _compile_patterns(STRENGTH_AMPLIFIERS)
_CAUSAL_PATTERNS = _compile_patterns(CAUSAL_CLAIMS)

# ---------------------------------------------------------------------------
# Section splitting for plain-text (extracted PDF) input
# ---------------------------------------------------------------------------

# Common heading patterns found in extracted PDFs and plain-text manuscripts.
_HEADING_RE = re.compile(
    r"(?:^|\n)"                       # start of line
    r"(?:"
    r"#{1,3}\s+"                      # markdown: ## Results
    r"|(?:\d+\.?\s+)?"               # optional numbering: 3. or 3
    r")"
    r"(abstract|introduction|background|methods|materials\s+and\s+methods"
    r"|experimental\s+(?:methods|procedures|section)"
    r"|results|results\s+and\s+discussion|discussion"
    r"|conclusions?|summary|concluding\s+remarks"
    r"|supplementary|acknowledgements?|references)"
    r"\s*\n",
    re.IGNORECASE | re.MULTILINE,
)

# Fallback: ALL-CAPS headings without numbering (common in PDFs)
_HEADING_CAPS_RE = re.compile(
    r"(?:^|\n)"
    r"(ABSTRACT|INTRODUCTION|BACKGROUND|METHODS"
    r"|MATERIALS\s+AND\s+METHODS|EXPERIMENTAL\s+(?:METHODS|PROCEDURES|SECTION)"
    r"|RESULTS|RESULTS\s+AND\s+DISCUSSION|DISCUSSION"
    r"|CONCLUSIONS?|SUMMARY|CONCLUDING\s+REMARKS"
    r"|SUPPLEMENTARY|ACKNOWLEDGEMENTS?|REFERENCES)"
    r"\s*\n",
    re.MULTILINE,
)

# Canonical section names we map detected headings to.
_SECTION_ALIASES: Dict[str, str] = {
    "abstract": "abstract",
    "introduction": "introduction",
    "background": "introduction",
    "methods": "methods",
    "materials and methods": "methods",
    "experimental methods": "methods",
    "experimental procedures": "methods",
    "experimental section": "methods",
    "results": "results",
    "results and discussion": "results_and_discussion",
    "discussion": "discussion",
    "conclusion": "conclusions",
    "conclusions": "conclusions",
    "concluding remarks": "conclusions",
    "summary": "conclusions",
    "supplementary": "supplementary",
    "acknowledgement": "acknowledgements",
    "acknowledgements": "acknowledgements",
    "references": "references",
}


def _normalise_heading(heading: str) -> str:
    """Map a detected heading to a canonical section name."""
    key = heading.strip().lower()
    # Try exact match first, then prefix match
    if key in _SECTION_ALIASES:
        return _SECTION_ALIASES[key]
    for alias, canonical in _SECTION_ALIASES.items():
        if key.startswith(alias) or alias.startswith(key):
            return canonical
    return key


def split_sections(text: str) -> Dict[str, str]:
    """Split paper text into sections by heading detection.

    Tries numbered/markdown headings first, then falls back to ALL-CAPS
    headings.  Returns a dict mapping canonical section names to their
    body text.  If no headings are detected, returns ``{"full_text": text}``.
    """
    # Try primary pattern first, fall back to caps-only
    matches = list(_HEADING_RE.finditer(text))
    if len(matches) < 2:
        matches = list(_HEADING_CAPS_RE.finditer(text))
    if len(matches) < 2:
        return {"full_text": text}

    sections: Dict[str, str] = {}

    # Text before the first heading -- might contain abstract or preamble
    preamble = text[: matches[0].start()].strip()
    if preamble and len(preamble.split()) > 30:
        sections["preamble"] = preamble

    for i, m in enumerate(matches):
        heading = _normalise_heading(m.group(1))
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            # If the same canonical section appears twice (e.g. a paper with
            # separate "Results" and "Results and Discussion"), append.
            if heading in sections:
                sections[heading] += "\n\n" + body
            else:
                sections[heading] = body

    return sections


# ---------------------------------------------------------------------------
# Sentence-level claim strength scoring
# ---------------------------------------------------------------------------

def _count_matches(sentence: str, patterns: List[re.Pattern]) -> int:
    """Count distinct pattern matches in a sentence."""
    return sum(1 for p in patterns if p.search(sentence))


def _claim_strength(sentence: str) -> float:
    """Compute a claim-strength score for a single sentence.

    Returns a value in [0, 1] where 0 = maximally hedged, 1 = maximally
    strong.  The raw signal is (amplifiers + causal - hedges) normalised
    by total marker count plus a length penalty.
    """
    n_hedge = _count_matches(sentence, _HEDGE_PATTERNS)
    n_amp = _count_matches(sentence, _AMP_PATTERNS)
    n_causal = _count_matches(sentence, _CAUSAL_PATTERNS)
    total_markers = n_hedge + n_amp + n_causal

    if total_markers == 0:
        # No markers -- assign a neutral-to-moderate score.
        # Longer sentences without hedging are slightly stronger claims.
        word_count = len(sentence.split())
        return min(0.5, 0.3 + 0.01 * word_count)

    # Raw score: amplifiers and causal markers increase strength,
    # hedges decrease it.
    raw = (n_amp + n_causal - n_hedge) / total_markers  # in [-1, 1]
    # Map to [0, 1]
    return (raw + 1.0) / 2.0


def _section_strength(
    text: str,
) -> Tuple[List[Dict], Dict]:
    """Score every sentence in a section and return per-sentence details + summary.

    Returns:
        ``(sentence_details, summary_dict)``
    """
    sentences = split_sentences(text)
    details: List[Dict] = []
    strengths: List[float] = []
    total_hedges = 0
    total_amps = 0
    total_causal = 0

    for sent in sentences:
        strength = _claim_strength(sent)
        n_h = _count_matches(sent, _HEDGE_PATTERNS)
        n_a = _count_matches(sent, _AMP_PATTERNS)
        n_c = _count_matches(sent, _CAUSAL_PATTERNS)
        total_hedges += n_h
        total_amps += n_a
        total_causal += n_c
        strengths.append(strength)
        details.append({
            "sentence": sent,
            "strength": strength,
            "hedges": n_h,
            "amplifiers": n_a,
            "causal": n_c,
        })

    mean_str = float(np.mean(strengths)) if strengths else 0.0
    summary = {
        "mean_strength": mean_str,
        "hedge_count": total_hedges,
        "amplifier_count": total_amps,
        "causal_count": total_causal,
        "sentence_count": len(sentences),
    }
    return details, summary


# ---------------------------------------------------------------------------
# Hedge escalation detection
# ---------------------------------------------------------------------------

def _find_escalation_flags(
    section_details: Dict[str, List[Dict]],
    section_order: List[str],
    threshold: float,
) -> List[Dict]:
    """Find sentences where hedging drops between an earlier and later section.

    Compares each sentence in a later section against all sentences in
    earlier sections.  If the later sentence is substantially stronger
    (strength delta > threshold) and semantically related, flag it.
    """
    flags: List[Dict] = []

    for late_idx in range(1, len(section_order)):
        late_name = section_order[late_idx]
        late_sents = section_details.get(late_name, [])
        if not late_sents:
            continue

        # Pool all sentences from earlier sections
        earlier_sents: List[Dict] = []
        for early_idx in range(late_idx):
            early_name = section_order[early_idx]
            earlier_sents.extend(section_details.get(early_name, []))
        if not earlier_sents:
            continue

        for late_s in late_sents:
            if late_s["strength"] < 0.5:
                # Not a strong claim -- nothing to flag
                continue
            for early_s in earlier_sents:
                delta = late_s["strength"] - early_s["strength"]
                if delta >= threshold:
                    flags.append({
                        "result_sentence": early_s["sentence"][:200],
                        "conclusion_sentence": late_s["sentence"][:200],
                        "result_strength": round(early_s["strength"], 3),
                        "conclusion_strength": round(late_s["strength"], 3),
                        "strength_delta": round(delta, 3),
                        "early_section": section_order[0],
                        "late_section": late_name,
                        "flag": "hedge_dropped",
                    })

    # Sort by delta descending and deduplicate (keep top flags)
    flags.sort(key=lambda x: x["strength_delta"], reverse=True)
    return flags[:30]


# ---------------------------------------------------------------------------
# Scope expansion via embeddings
# ---------------------------------------------------------------------------

def _scope_expansion(
    result_sentences: List[str],
    conclusion_sentences: List[str],
    scope_threshold: float,
    model=None,
) -> Tuple[List[Dict], float]:
    """Detect conclusion sentences that are semantically distant from all results.

    Returns:
        ``(gaps, mean_support)``
    """
    if not result_sentences or not conclusion_sentences:
        return [], 0.0

    all_texts = result_sentences + conclusion_sentences
    n_res = len(result_sentences)

    emb, _backend = embed_texts(all_texts, model=model, show_progress=False)
    res_emb = emb[:n_res]
    conc_emb = emb[n_res:]

    # For each conclusion sentence, find its nearest result sentence
    sims = cosine_sim(conc_emb, res_emb)  # (n_conc, n_res)
    best_idx = np.argmax(sims, axis=1)
    best_sim = np.max(sims, axis=1)

    gaps: List[Dict] = []
    for i, sim_val in enumerate(best_sim):
        if sim_val < scope_threshold:
            gaps.append({
                "conclusion": conclusion_sentences[i][:200],
                "nearest_result": result_sentences[int(best_idx[i])][:200],
                "similarity": round(float(sim_val), 3),
                "flag": "scope_expansion",
            })

    gaps.sort(key=lambda x: x["similarity"])
    mean_support = float(np.mean(best_sim)) if len(best_sim) > 0 else 0.0
    return gaps, mean_support


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_overclaiming(
    sections: Dict[str, str],
    hedge_threshold: float = 0.3,
    scope_threshold: float = 0.4,
    model=None,
) -> Dict:
    """Detect hedge erosion and scope expansion between paper sections.

    Args:
        sections: Mapping of section name to body text.  Expected keys
            include some subset of ``"results"``, ``"discussion"``,
            ``"abstract"``, ``"conclusions"``.  Can be produced by
            :func:`split_sections` or passed directly.
        hedge_threshold: Minimum strength delta to flag hedge erosion.
        scope_threshold: Flag conclusions with best-match result similarity
            below this value.
        model: Pre-loaded embedding model (optional).

    Returns:
        Dict with ``hedge_analysis``, ``scope_analysis``,
        ``overall_overclaiming_score``, and ``flags`` list.
    """
    # ---- Resolve available sections ----
    # Priority order for "early" (evidence) sections
    evidence_keys = ["results", "results_and_discussion"]
    # Priority order for "late" (claim) sections
    claim_keys = ["abstract", "conclusions", "discussion"]

    available_evidence = [k for k in evidence_keys if k in sections]
    available_claims = [k for k in claim_keys if k in sections]

    # Build the section ordering for hedge analysis:
    # evidence sections first, then discussion, then conclusions, then abstract
    analysis_order: List[str] = []
    for k in ["results", "results_and_discussion", "discussion", "conclusions", "abstract"]:
        if k in sections:
            analysis_order.append(k)

    # ---- Hedge analysis ----
    section_details: Dict[str, List[Dict]] = {}
    section_summaries: Dict[str, Dict] = {}

    for sec_name in analysis_order:
        details, summary = _section_strength(sections[sec_name])
        section_details[sec_name] = details
        section_summaries[sec_name] = summary

    escalation_flags = _find_escalation_flags(
        section_details, analysis_order, hedge_threshold
    )

    hedge_analysis: Dict = {
        "by_section": section_summaries,
        "escalation_flags": escalation_flags,
    }

    # ---- Scope analysis ----
    # Collect result sentences and conclusion/abstract sentences
    result_sentences: List[str] = []
    for k in available_evidence:
        result_sentences.extend(split_sentences(sections[k]))

    conclusion_sentences: List[str] = []
    for k in available_claims:
        conclusion_sentences.extend(split_sentences(sections[k]))

    gaps, mean_support = _scope_expansion(
        result_sentences, conclusion_sentences, scope_threshold, model=model
    )

    scope_analysis: Dict = {
        "conclusion_result_gaps": gaps,
        "mean_conclusion_support": round(mean_support, 3),
    }

    # ---- Overall score ----
    # Combine hedge erosion and scope expansion into a single 0-1 score.
    #
    # Hedge component: fraction of strong escalation flags relative to
    # total late-section sentences, weighted by mean delta.
    n_late_sentences = sum(
        section_summaries.get(k, {}).get("sentence_count", 0)
        for k in available_claims
    )
    hedge_score = 0.0
    if n_late_sentences > 0 and escalation_flags:
        flag_fraction = min(1.0, len(escalation_flags) / max(n_late_sentences, 1))
        mean_delta = float(np.mean([f["strength_delta"] for f in escalation_flags]))
        hedge_score = flag_fraction * mean_delta

    # Scope component: 1 - mean_support (low support = high overclaiming)
    scope_score = 1.0 - mean_support if mean_support > 0 else 0.0

    # Weighted combination
    overall = 0.5 * min(hedge_score * 2, 1.0) + 0.5 * min(scope_score, 1.0)
    overall = round(float(np.clip(overall, 0.0, 1.0)), 3)

    # ---- Summary flags ----
    summary_flags: List[str] = []

    # Check for hedge erosion between specific section pairs
    for early_k in available_evidence:
        for late_k in available_claims:
            early_mean = section_summaries.get(early_k, {}).get("mean_strength", 0.5)
            late_mean = section_summaries.get(late_k, {}).get("mean_strength", 0.5)
            if late_mean - early_mean > hedge_threshold:
                summary_flags.append(
                    f"hedge_erosion_{early_k}_to_{late_k}"
                )

    if gaps:
        summary_flags.append("scope_expansion_in_conclusions")

    return {
        "hedge_analysis": hedge_analysis,
        "scope_analysis": scope_analysis,
        "overall_overclaiming_score": overall,
        "flags": summary_flags,
    }
