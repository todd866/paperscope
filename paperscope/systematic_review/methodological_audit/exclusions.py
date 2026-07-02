"""Detect papers unfit for audit: dupes, non-English, corrupted text,
content-vs-metadata mismatches, boilerplate-only extractions, off-topic.

Designed to be run on the text-extracted corpus BEFORE the audit pipeline, so
sample() can filter excluded pmids out at every level. Detection is staged:

  v0.1 heuristics — high-precision rules:
    - byte-identical de-duplication (sha1 grouping)
    - English stopword ratio (multiple body chunks)
    - corrupted-text symbol-run signature (Caesar-shift fonts, glyph-encoding bugs)

  v0.2 heuristics — added after sub-agent audit findings:
    - title-in-text vs metadata-title fuzzy match (best across first 200 lines
      + 2/3-line sliding windows; threshold tunable; 0.30 strict / 0.50 lax)
    - boilerplate-only line-uniqueness (catches "Downloaded by:" stamp PDFs)
    - keyword absence (e.g., target-vocabulary absence flags abbreviation collisions)

Known limitations:
  - Title fuzzy-match is corpus-dependent (some source PDFs split
    titles across multiple lines; the sliding-window catches most). Tune the
    threshold by validating against a known-good and known-bad set per corpus.
  - The corrupted-text regex only catches symptom A (Caesar-shift caps); other
    PDF font-encoding bugs need their own detectors.

Usage:
    from paperscope.systematic_review.methodological_audit.exclusions import (
        detect_exclusions, run_v0_2_detector,
    )
    exclusions = detect_exclusions(text_dir="text/", records_jsonl="corpus/records.jsonl")
    # exclusions: list of {"pmid": ..., "reason": ..., "details": ...}
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

STOPS = {
    "the", "of", "and", "in", "to", "a", "is", "that", "with", "for",
    "were", "was", "we", "this", "are", "as", "be", "on", "or", "by",
    "from", "an", "at", "have", "had", "has", "these", "their",
    "which", "between", "patients", "study", "results", "methods",
}

PAGE_MARK = re.compile(r"^---\s*page\s+\d+\s*---$", re.IGNORECASE)


def find_duplicate_groups(text_dir: str | Path) -> dict[str, list[str]]:
    """Returns sha1 → [pmids] groups of byte-identical text files (≥2)."""
    text_dir = Path(text_dir)
    groups: dict[str, list[str]] = defaultdict(list)
    for p in text_dir.glob("*.txt"):
        h = hashlib.sha1(p.read_bytes()).hexdigest()
        groups[h].append(p.stem)
    return {h: pmids for h, pmids in groups.items() if len(pmids) >= 2}


def is_non_english_or_corrupted(text: str) -> tuple[str | None, float]:
    """Inspect 4 body chunks; if max English-stopword ratio < 0.08, flag.
    Distinguishes non-English (no special structure) from corrupted-glyph
    (all-caps non-vowel runs)."""
    n = len(text)
    if n < 3000:
        return None, 1.0
    chunks = [text[i * n // 5 : i * n // 5 + 3000].lower() for i in range(1, 5)]
    max_ratio = 0.0
    for c in chunks:
        words = re.findall(r"[a-z]+", c)
        if len(words) < 50:
            continue
        ratio = sum(1 for w in words if w in STOPS) / len(words)
        max_ratio = max(max_ratio, ratio)
    if max_ratio >= 0.08:
        return None, max_ratio
    if re.search(r"[B-DF-HJ-NP-TV-Z]{8,}", text[:5000]):
        return "corrupted_text", max_ratio
    return "non_english", max_ratio


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def title_in_text_max_similarity(text: str, meta_title: str) -> tuple[float, str | None]:
    """Best-match across first 200 lines + 2/3-line sliding windows.
    Returns (max_sim, best_match)."""
    meta_norm = _norm_text(meta_title)
    if len(meta_norm) < 10:
        return (0.0, None)
    lines = [l.strip() for l in text.split("\n")[:200]]
    candidates: list[str] = []
    for i, ln in enumerate(lines):
        if not ln or len(ln) < 5 or len(ln) > 400:
            continue
        candidates.append(ln)
        if i + 1 < len(lines) and lines[i + 1]:
            candidates.append(ln + " " + lines[i + 1])
        if i + 2 < len(lines) and lines[i + 1] and lines[i + 2]:
            candidates.append(ln + " " + lines[i + 1] + " " + lines[i + 2])
    best_sim = 0.0
    best_match = None
    for cand in candidates:
        sim = difflib.SequenceMatcher(None, _norm_text(cand), meta_norm).ratio()
        if sim > best_sim:
            best_sim = sim
            best_match = cand
    return (best_sim, best_match)


def boilerplate_score(text: str) -> tuple[float, int]:
    """Returns (meaningful-content ratio, total-lines). Filters page markers,
    blanks, repeated lines. Low ratio = boilerplate-only extraction."""
    raw_lines = [l.strip() for l in text.split("\n")]
    non_empty = [l for l in raw_lines if l]
    if len(non_empty) < 5:
        return (0.0, len(raw_lines))
    meaningful = [l for l in non_empty
                  if not PAGE_MARK.match(l)
                  and not l.isdigit()
                  and len(l) > 3]
    counts = Counter(meaningful)
    unique_lines = [l for l, c in counts.items() if c == 1]
    if not meaningful:
        return (0.0, len(raw_lines))
    return (len(unique_lines) / len(meaningful), len(raw_lines))


def has_any_keyword(text: str, keywords: set[str], scan_chars: int = 20000) -> bool:
    body = text.lower()[:scan_chars]
    return any(kw in body for kw in keywords)


def detect_exclusions(
    *,
    text_dir: str | Path,
    records_jsonl: str | Path | None = None,
    title_sim_threshold: float = 0.50,
    domain_keywords: set[str] | None = None,
) -> list[dict]:
    """Run all v0.1 + v0.2 detectors and return a candidates list of
    {pmid, reason, details, flagged_at} rows.

    `records_jsonl` is used for title-vs-text fuzzy matching when available.
    `domain_keywords` is used for keyword-absence flagging (optional)."""
    text_dir = Path(text_dir)
    flagged_at = datetime.now().isoformat(timespec="seconds")
    titles: dict[str, str] = {}
    if records_jsonl and Path(records_jsonl).exists():
        with Path(records_jsonl).open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                    pmid = str(r.get("pmid", ""))
                    if pmid and r.get("title"):
                        titles[pmid] = r["title"]
                except Exception:
                    pass

    out: list[dict] = []
    seen: set[str] = set()

    # 1. Byte-identical duplicates
    for h, pmids in find_duplicate_groups(text_dir).items():
        for pmid in pmids:
            out.append({"pmid": pmid, "reason": "duplicate_content",
                        "details": f"sha1={h[:12]}, group_size={len(pmids)}",
                        "flagged_at": flagged_at})
            seen.add(pmid)

    # 2. Non-English / corrupted; 3. Boilerplate; 4. Title mismatch; 5. Keyword absence
    for p in sorted(text_dir.glob("*.txt")):
        pmid = p.stem
        if pmid in seen:
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        n = len(text)

        # Non-English / corrupted
        reason, _ratio = is_non_english_or_corrupted(text)
        if reason:
            out.append({"pmid": pmid, "reason": reason,
                        "details": f"english_stopword_ratio<0.08",
                        "flagged_at": flagged_at})
            seen.add(pmid)
            continue

        # Boilerplate-only
        unique_ratio, _ = boilerplate_score(text)
        if n < 8000 and unique_ratio < 0.30:
            out.append({"pmid": pmid, "reason": "boilerplate_only",
                        "details": f"unique_line_ratio={unique_ratio:.2f}, size={n}",
                        "flagged_at": flagged_at})
            seen.add(pmid)
            continue

        # Title mismatch
        meta_title = titles.get(pmid)
        if meta_title and n >= 1000:
            sim, match = title_in_text_max_similarity(text, meta_title)
            if sim < title_sim_threshold:
                out.append({"pmid": pmid, "reason": "metadata_content_mismatch",
                            "details": f"max_sim={sim:.2f}, meta={meta_title[:60]!r}",
                            "flagged_at": flagged_at})
                seen.add(pmid)
                continue

        # Domain-keyword absence
        if domain_keywords and n > 4000 and not has_any_keyword(text, domain_keywords):
            out.append({"pmid": pmid, "reason": "domain_keyword_absent",
                        "details": f"no domain-vocabulary keyword in first 20K chars",
                        "flagged_at": flagged_at})
            seen.add(pmid)

    return out


def write_exclusions(exclusions: list[dict], out_path: str | Path) -> None:
    """Append exclusions to a JSONL (preserves any existing entries)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a") as f:
        for e in exclusions:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def load_into_db(con, exclusions_jsonl: str | Path) -> int:
    """Load all rows from exclusions JSONL into audit.exclusions table.
    Returns count loaded. INSERT OR REPLACE — idempotent."""
    path = Path(exclusions_jsonl)
    if not path.exists():
        return 0
    n = 0
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                con.execute(
                    """INSERT OR REPLACE INTO audit_exclusions
                       (pmid, reason, details, flagged_at)
                       VALUES (?, ?, ?, ?)""",
                    (e["pmid"], e["reason"], e.get("details", ""), e.get("flagged_at", "")),
                )
                n += 1
            except Exception:
                pass
    con.commit()
    return n
