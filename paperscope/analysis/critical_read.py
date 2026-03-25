"""Critical read orchestrator — structured critique of an external paper.

Combines author profiling, method resolution analysis, missing methods
detection, and overclaiming detection into a single report.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional


def critical_read(
    paper_text: str,
    author_names: List[str] = None,
    methods_used: List[str] = None,
    question_resolution: List[str] = None,
    output_dir: Optional[Path] = None,
    skip_author_lookup: bool = False,
) -> Dict:
    """Run full critical-read analysis on extracted paper text.

    Args:
        paper_text: Full text of the paper (from PDF extraction or .tex).
        author_names: List of author names. Auto-extracted if None.
        methods_used: List of method names used. Auto-detected if None.
        question_resolution: Resolution levels the paper's question requires.
        output_dir: Directory to write JSON output. None = skip file output.
        skip_author_lookup: Skip OpenAlex author lookup (for offline use).

    Returns:
        Combined results dict with all four analyses.
    """
    from .overclaiming import detect_overclaiming, split_sections
    from .method_resolution import check_resolution_match
    from .missing_methods import check_missing_methods, detect_methods
    from .author_profile import profile_authors

    print("=" * 60)
    print("  PAPERSCOPE CRITICAL READ")
    print("=" * 60)

    # --- Section splitting ---
    print("\nSplitting sections...")
    sections = split_sections(paper_text)
    section_names = [k for k, v in sections.items() if v.strip()]
    print(f"  Found sections: {', '.join(section_names)}")

    # --- Auto-detect methods if not provided ---
    if methods_used is None:
        print("\nDetecting methods...")
        methods_used = detect_methods(paper_text)
        print(f"  Detected: {', '.join(methods_used) if methods_used else 'none'}")

    # --- Author profiling ---
    author_result = {}
    if author_names and not skip_author_lookup:
        print(f"\nProfiling {len(author_names)} authors...")
        try:
            author_result = profile_authors(
                author_names,
                paper_methods=methods_used,
            )
            _print_author_summary(author_result)
        except Exception as e:
            print(f"  Author profiling failed: {e}")
            author_result = {"error": str(e)}
    elif author_names:
        print(f"\n  Skipping author lookup (offline mode)")
        author_result = {"skipped": True, "authors_provided": author_names}

    # --- Method resolution ---
    print("\nChecking method-conclusion resolution match...")
    method_text = sections.get("methods", "") or sections.get("materials and methods", "")
    conclusion_text = (sections.get("abstract", "") + "\n" +
                       sections.get("conclusions", "") +
                       sections.get("discussion", ""))
    results_text = sections.get("results", "")

    resolution_result = check_resolution_match(
        method_text=method_text,
        conclusions_text=conclusion_text,
        results_text=results_text,
    )
    _print_resolution_summary(resolution_result)

    # --- Missing methods ---
    print("\nChecking for missing complementary methods...")
    missing_result = check_missing_methods(
        methods_used=methods_used,
        question_resolution=question_resolution,
    )
    _print_missing_summary(missing_result)

    # --- Overclaiming ---
    print("\nDetecting overclaiming...")
    overclaiming_result = detect_overclaiming(sections)
    _print_overclaiming_summary(overclaiming_result)

    # --- Combined result ---
    result = {
        "sections_found": section_names,
        "methods_detected": methods_used,
        "author_profile": author_result,
        "resolution_analysis": resolution_result,
        "missing_methods": missing_result,
        "overclaiming": overclaiming_result,
    }

    # --- Verdict ---
    verdict = _compute_verdict(result)
    result["verdict"] = verdict
    _print_verdict(verdict)

    # --- Write output ---
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "critical_read.json"
        out_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"\nFull results: {out_path}")

    return result


def extract_author_names(text: str) -> List[str]:
    """Attempt to extract author names from paper text.

    Simple heuristic: look for lines near the top with comma-separated
    names, or lines between title-like text and abstract.
    """
    lines = text.split("\n")[:50]
    candidates = []

    # Keywords that indicate non-author lines
    skip_keywords = [
        "abstract", "introduction", "university", "department", "institute",
        "keywords", "correspondence", "email", "faculty", "school of",
        "college of", "center for", "centre for", "hospital", "clinic",
        "received", "accepted", "published", "doi:", "http", "orcid", "@",
        "sydney", "melbourne", "london", "new york", "berlin", "tokyo",
        "australia", "usa", "united states", "united kingdom",
        "nsw", "vic", "qld",  # state abbreviations
    ]

    for line in lines:
        line = line.strip()
        # Skip very short or very long lines
        if len(line) < 5 or len(line) > 500:
            continue
        # Skip lines with LaTeX commands (likely affiliations)
        if "\\\\" in line or "\\texttt" in line or "\\href" in line:
            continue
        # Skip lines that look like titles, abstracts, affiliations, or addresses
        if any(kw in line.lower() for kw in skip_keywords):
            continue
        # Skip lines that are mostly numbers/punctuation (addresses, phone numbers)
        alpha_ratio = sum(1 for c in line if c.isalpha()) / max(len(line), 1)
        if alpha_ratio < 0.6:
            continue
        # Look for lines with multiple names (commas or "and")
        if ("," in line or " and " in line) and not line.endswith("."):
            # Check if words are mostly capitalized (name-like)
            words = [w for w in line.split() if len(w) > 1]
            if not words:
                continue
            cap_ratio = sum(1 for w in words if w[0].isupper()) / len(words)
            # Names should be 2-6 words per person, so total < 40 words
            # and at least 2 words (first + last name)
            if cap_ratio > 0.5 and 2 <= len(words) < 40:
                candidates.append(line)

    if not candidates:
        return []

    # Take the best candidate and split into names
    best = candidates[0]
    # Split on comma or "and"
    parts = re.split(r",\s*|\s+and\s+", best)
    names = [p.strip() for p in parts if len(p.strip()) > 2]
    return names


def _compute_verdict(result: Dict) -> Dict:
    """Compute overall verdict from component analyses."""
    flags = []
    severity = "low"
    analysis_gaps = []

    # Check for analysis failures (insufficient text extracted)
    res = result.get("resolution_analysis", {})
    if res.get("error"):
        analysis_gaps.append(f"resolution analysis failed: {res['error']}")
    oc = result.get("overclaiming", {})
    if oc.get("error"):
        analysis_gaps.append(f"overclaiming analysis failed: {oc['error']}")

    if analysis_gaps:
        flags.append(f"incomplete analysis ({len(analysis_gaps)} modules failed)")
        if severity == "low":
            severity = "incomplete"

    # Resolution mismatch
    mismatch = res.get("mismatch", {})
    if mismatch.get("detected"):
        sev = mismatch.get("severity", "low")
        flags.append(f"resolution_mismatch ({sev})")
        if sev == "high":
            severity = "high"
        elif sev == "medium" and severity != "high":
            severity = "medium"

    # Missing methods
    missing = result.get("missing_methods", {})
    high_priority = [m for m in missing.get("missing_complementary", [])
                     if m.get("priority") == "high"]
    if high_priority:
        flags.append(f"{len(high_priority)} high-priority missing methods")
        if severity != "high":
            severity = "medium"

    # Overclaiming
    oc = result.get("overclaiming", {})
    oc_score = oc.get("overall_overclaiming_score", 0)
    if oc_score > 0.6:
        flags.append("significant overclaiming")
        severity = "high"
    elif oc_score > 0.3:
        flags.append("moderate overclaiming")
        if severity == "low":
            severity = "medium"

    # Author COI
    auth = result.get("author_profile", {})
    team = auth.get("team_assessment", {})
    if team.get("self_validation_risk") == "high":
        flags.append("self-validation risk")

    return {
        "overall_severity": severity,
        "flags": flags,
        "n_flags": len(flags),
    }


def _print_author_summary(result: Dict) -> None:
    """Print author profiling summary."""
    team = result.get("team_assessment", {})
    if team.get("self_validation_risk") in ("medium", "high"):
        print(f"  ⚠ Self-validation: {team.get('self_validation_risk')}")
    if team.get("institutional_concentration"):
        print(f"  ⚠ {team['institutional_concentration']}")
    shared = team.get("shared_prior_works", [])
    if shared:
        print(f"  ⚠ {len(shared)} shared prior works among authors")


def _print_resolution_summary(result: Dict) -> None:
    """Print method-resolution summary."""
    if result.get("error"):
        print(f"  ⚠ Resolution analysis failed: {result['error']}")
        return
    mismatch = result.get("mismatch", {})
    if mismatch.get("detected"):
        sev = mismatch.get("severity", "unknown")
        print(f"  ❌ RESOLUTION MISMATCH (severity: {sev})")
        method = result.get("method_resolution", {})
        conclusion = result.get("conclusion_resolution", {})
        print(f"     Method resolves: {method.get('detected_level', '?')}")
        print(f"     Conclusion requires: {conclusion.get('detected_level', '?')}")
        for blind_spot in mismatch.get("method_blind_spots", [])[:3]:
            print(f"     • {blind_spot}")
    else:
        print(f"  ✓ No resolution mismatch detected")


def _print_missing_summary(result: Dict) -> None:
    """Print missing methods summary."""
    missing = result.get("missing_complementary", [])
    if missing:
        for m in missing[:5]:
            priority = m.get("priority", "?")
            marker = "⚠" if priority == "high" else "○"
            print(f"  {marker} {m['name']} ({m['ecosystem']}) — {priority} priority")
            if m.get("why_relevant"):
                print(f"    {m['why_relevant']}")
    else:
        print(f"  ✓ No missing complementary methods detected")

    gaps = result.get("resolution_coverage", {}).get("gaps", [])
    if gaps:
        print(f"  Resolution gaps: {', '.join(gaps)}")


def _print_overclaiming_summary(result: Dict) -> None:
    """Print overclaiming summary."""
    score = result.get("overall_overclaiming_score", 0)
    label = "low" if score < 0.3 else "moderate" if score < 0.6 else "significant"
    print(f"  Overclaiming score: {score:.2f} ({label})")

    hedge = result.get("hedge_analysis", {})
    escalation = hedge.get("escalation_flags", [])
    if escalation:
        print(f"  Hedge escalation flags: {len(escalation)}")
        for e in escalation[:3]:
            print(f"    • \"{e.get('result_sentence', '?')[:60]}...\"")
            print(f"      → \"{e.get('conclusion_sentence', '?')[:60]}...\"")

    scope = result.get("scope_analysis", {})
    gaps = scope.get("conclusion_result_gaps", [])
    scope_flags = [g for g in gaps if g.get("flag")]
    if scope_flags:
        print(f"  Scope expansion flags: {len(scope_flags)}")


def _print_verdict(verdict: Dict) -> None:
    """Print final verdict."""
    print(f"\n{'=' * 60}")
    print(f"  VERDICT: {verdict['overall_severity'].upper()} concern")
    print(f"{'=' * 60}")
    if verdict["flags"]:
        for f in verdict["flags"]:
            print(f"  • {f}")
    else:
        print(f"  No significant issues detected")
    print(f"{'=' * 60}")
