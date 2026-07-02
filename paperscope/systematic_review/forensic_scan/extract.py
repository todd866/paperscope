"""Text-corpus extractors: p-values, effect-size+CI rows, mean+SD+n triples,
funding/COI statements, author surnames, cohort sizes.

All extractors are intentionally REGEX-based (no LLM). They return many false
positives — that's expected for corpus-scale aggregation, where the signal is
in the population distribution, not in any single hit. For per-paper
verification, pass the extracted rows through `paperscope.analysis.forensic_stats`
or have a sub-agent read the paper.

Known limitations are documented in the parent module (see
`forensic_scan/__init__.py`).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

P_VALUE_RE = re.compile(
    r"\b[pP][\s\-]?(?:value)?[\s\-]?([<>=≤≥])\s*(0?\.\d+|\d+\.\d+e[-+]?\d+|0\.0+1)",
    re.IGNORECASE,
)
T_RE = re.compile(r"\bt\s*\(\s*(\d+(?:\.\d+)?)\s*\)\s*[=≈]\s*(-?\d+\.\d+)", re.IGNORECASE)
F_RE = re.compile(r"\bF\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)\s*[=≈]\s*(\d+\.\d+)", re.IGNORECASE)
CHI2_RE = re.compile(
    r"(?:χ2|χ²|chi[\s-]?(?:square|squared|2|sq))\s*\(\s*(\d+)(?:,\s*N\s*=\s*\d+)?\s*\)\s*[=≈]\s*(\d+\.\d+)",
    re.IGNORECASE,
)
R_RE = re.compile(r"\br\s*\(\s*(\d+)\s*\)\s*[=≈]\s*(-?\d*\.\d+)", re.IGNORECASE)

EFFECT_CI_RE = re.compile(
    r"\b(HR|OR|RR|aHR|aOR|aRR)\b\s*[=:]?\s*"
    r"(\d+\.\d{1,3})\s*"
    r"[,;(\[\s]+(?:95\s*%?\s*CI?\s*[=:]?\s*)?"
    r"(\d+\.\d{1,3})\s*[-–to\s]+\s*(\d+\.\d{1,3})\s*[)\]]?",
    re.IGNORECASE,
)

TABLE_MEAN_SD_RE = re.compile(
    r"(?<![\w.])(\d{1,3}\.\d{1,3})\s*(?:\(|±|\[|\s)\s*(\d{1,3}\.\d{1,3})\s*\)?\]?"
)

N_REFERENCE_RE = re.compile(r"\bn\s*[=:]\s*(\d{2,4})\b", re.IGNORECASE)

FUNDING_PAT = re.compile(
    r"(?:funded by|funding|grant|sponsored by|supported by)[\s\S]{0,300}",
    re.IGNORECASE,
)
COI_PAT = re.compile(
    r"(?:competing interests?|conflicts? of interest|disclosures?|coi statement)[\s\S]{0,400}",
    re.IGNORECASE,
)
INDUSTRY_RE = re.compile(
    r"\b(biogen|cytokinetics|pfizer|roche|novartis|merck|astrazeneca|sanofi|"
    r"glaxosmithkline|gsk|amgen|takeda|denali|amylyx|orphazyme|treeway|"
    r"clene|annexon|ionis|wave\s+life|brainstorm|alector|prilenia|"
    r"pharmaceutical|pharmaceuticals|inc\.|llc|s\.a\.|sponsored|"
    r"industry|consulting fees|honoraria|advisory board)\b",
    re.IGNORECASE,
)

SIGNIFICANT_RE = re.compile(
    r"\b(?:statistically\s+)?significant(?:ly)?\b(?!\s*(?:lower|higher|different))",
    re.IGNORECASE,
)
NOT_SIGNIFICANT_RE = re.compile(
    r"\b(?:not\s+(?:statistically\s+)?significant|no\s+significant|non[- ]?significant|ns\b)",
    re.IGNORECASE,
)

AUTHOR_RE = re.compile(
    r"\b([A-Z][a-z]+(?:[-' ][A-Z][a-z]+)*),?\s+([A-Z]\.?\s*){1,3}",
    re.MULTILINE,
)

COHORT_N_RE = re.compile(r"\bn\s*=\s*(\d{2,4})\b", re.IGNORECASE)


def _find_nearby_stat(text: str, p_pos: int, window: int = 200):
    chunk = text[max(0, p_pos - window) : p_pos]
    last_match = None
    for m in T_RE.finditer(chunk):
        last_match = ("t", (float(m.group(1)), float(m.group(2))), m.end())
    for m in F_RE.finditer(chunk):
        end = m.end()
        if last_match is None or end > last_match[2]:
            last_match = ("F", (int(m.group(1)), int(m.group(2)), float(m.group(3))), end)
    for m in CHI2_RE.finditer(chunk):
        end = m.end()
        if last_match is None or end > last_match[2]:
            last_match = ("chi2", (int(m.group(1)), float(m.group(2))), end)
    for m in R_RE.finditer(chunk):
        end = m.end()
        if last_match is None or end > last_match[2]:
            last_match = ("r", (float(m.group(1)), float(m.group(2))), end)
    if last_match:
        return last_match[0], last_match[1]
    return None


def extract_pvalues(text: str, pmid: str = "") -> list[dict]:
    """Extract all reported p-values + adjacent test statistics. NOTE: papers
    in the target corpus rarely have adjacent test stats in APA format — expect
    a low extraction yield with adjacent stats (~3-5% in the demo corpus)."""
    rows = []
    for m in P_VALUE_RE.finditer(text):
        op, val_str = m.group(1), m.group(2)
        try:
            p_rep = float(val_str)
        except Exception:
            continue
        if p_rep <= 0 or p_rep > 1:
            continue
        row = {
            "pmid": pmid,
            "p_reported": p_rep,
            "p_str": val_str,  # preserves trailing zeros for last-digit analysis
            "op": op,
            "context_excerpt": text[max(0, m.start() - 60) : m.end() + 60].replace("\n", " "),
        }
        stat = _find_nearby_stat(text, m.start())
        if stat:
            row["test_type"], row["test_params"] = stat[0], list(stat[1])
        rows.append(row)
    return rows


def extract_effects(text: str, pmid: str = "") -> list[dict]:
    """Extract HR/OR/RR + 95% CI rows. Flags implausibly wide CIs (width > 5×
    point estimate) and CIs that don't contain the point estimate."""
    rows = []
    for m in EFFECT_CI_RE.finditer(text):
        kind = m.group(1)
        est, ci_lo, ci_hi = float(m.group(2)), float(m.group(3)), float(m.group(4))
        if ci_lo > ci_hi:
            ci_lo, ci_hi = ci_hi, ci_lo
        if est <= 0 or ci_lo <= 0 or ci_hi <= 0:
            continue
        excludes_null = (ci_lo > 1.0) or (ci_hi < 1.0)
        ci_consistent = ci_lo <= est <= ci_hi
        width = ci_hi - ci_lo
        rows.append({
            "pmid": pmid, "kind": kind, "estimate": est,
            "ci_lo": ci_lo, "ci_hi": ci_hi,
            "ci_consistent": bool(ci_consistent),
            "excludes_null": bool(excludes_null),
            "implausibly_wide": bool(width / max(est, 0.1) > 5.0),
            "width_over_est": round(width / max(est, 0.1), 2),
            "context_excerpt": text[max(0, m.start() - 60) : m.end() + 60].replace("\n", " "),
        })
    return rows


def extract_mean_sd_n_triples(text: str, pmid: str = "",
                              max_n: int = 2000, max_mean: float = 100.0,
                              line_window: int = 20) -> list[dict]:
    """Table-aware mean+SD+n extraction. Finds (mean, SD) pairs on any line,
    then scans ±`line_window` lines for n-references. Returns the best-match n
    per (mean, SD). Note: medical means are mostly CONTINUOUS, so GRIM-style
    integer-decomposition tests on these will mostly false-positive — pass
    the rows through `forensic_stats.grim` only if you've filtered for
    plausibly-integer-summed data (Likert scales, counts, etc.)."""
    rows = []
    lines = text.split("\n")
    line_starts = [0]
    for ln in lines[:-1]:
        line_starts.append(line_starts[-1] + len(ln) + 1)
    n_refs = []
    for li, ln in enumerate(lines):
        for m in N_REFERENCE_RE.finditer(ln):
            try:
                nval = int(m.group(1))
                if 5 <= nval <= max_n:
                    n_refs.append((li, nval))
            except Exception:
                pass

    seen = set()
    for m in TABLE_MEAN_SD_RE.finditer(text):
        mean_str, sd_str = m.group(1), m.group(2)
        try:
            mean, sd = float(mean_str), float(sd_str)
        except Exception:
            continue
        if mean > max_mean or mean < 0:
            continue
        decimals = len(mean_str.split(".", 1)[1]) if "." in mean_str else 0
        if decimals < 1:
            continue
        char_pos = m.start()
        line_idx = next((i for i, s in enumerate(line_starts) if s > char_pos), len(line_starts)) - 1
        candidates = [n for li, n in n_refs if abs(li - line_idx) <= line_window]
        if not candidates:
            continue
        n_used = candidates[0]
        key = (pmid, mean, sd, n_used)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "pmid": pmid,
            "mean": mean,
            "sd": sd,
            "n_candidates": list(set(candidates)),
            "n_used": n_used,
            "decimals": decimals,
            "context_excerpt": text[max(0, m.start() - 80) : m.end() + 80].replace("\n", " "),
        })
    return rows


def extract_funding_coi(text: str, pmid: str = "") -> dict:
    """Classify a paper's funding/COI declaration as one of:
        'industry_linked', 'public_disclosed', 'partial', 'none_stated'."""
    funding_blocks = list(FUNDING_PAT.finditer(text))
    coi_blocks = list(COI_PAT.finditer(text))
    has_funding = bool(funding_blocks)
    has_coi = bool(coi_blocks)
    industry = (
        any(INDUSTRY_RE.search(text[m.start() : m.start() + 500]) for m in funding_blocks)
        or any(INDUSTRY_RE.search(text[m.start() : m.start() + 500]) for m in coi_blocks)
    )
    if industry:
        cls = "industry_linked"
    elif has_funding and has_coi:
        cls = "public_disclosed"
    elif has_funding or has_coi:
        cls = "partial"
    else:
        cls = "none_stated"
    return {
        "pmid": pmid,
        "has_funding_statement": bool(has_funding),
        "has_coi_statement": bool(has_coi),
        "industry_linked": bool(industry),
        "classification": cls,
    }


def extract_authors(text: str, max_authors: int = 12) -> set[str]:
    """Best-effort author-surname extraction from first ~3000 chars of front
    matter. Returns a set of candidate surnames. Useful for cross-paper
    author-overlap salami screening but NOT for definitive author identity."""
    head = text[:3000]
    authors = set()
    for m in AUTHOR_RE.finditer(head):
        surname = m.group(1)
        if len(surname) >= 3 and surname.lower() not in {"abstract", "article", "introduction"}:
            authors.add(surname)
        if len(authors) >= max_authors:
            break
    return authors


def extract_cohort_size(text: str) -> int | None:
    """Best-effort: largest plausible n in first 5K chars."""
    candidates = []
    for m in COHORT_N_RE.finditer(text[:5000]):
        try:
            n = int(m.group(1))
            if 20 <= n <= 5000:
                candidates.append(n)
        except Exception:
            pass
    return max(candidates) if candidates else None


def extract_positivity_mentions(text: str) -> dict:
    """Count 'significant' vs 'not significant' mentions; return positivity ratio."""
    sig = len(SIGNIFICANT_RE.findall(text))
    not_sig = len(NOT_SIGNIFICANT_RE.findall(text))
    total = sig + not_sig
    return {
        "n_significant_mentions": sig,
        "n_not_significant_mentions": not_sig,
        "positivity_ratio": sig / total if total else None,
    }
