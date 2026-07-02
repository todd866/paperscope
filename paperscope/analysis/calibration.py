#!/usr/bin/env python3
"""
Calibration harness for the forensic-statistics battery.

A *case* is a hand-built forensic scenario with a known answer: a table
spec and/or a chunk of prose whose errors were planted by construction,
plus an ``expected`` block asserting which checks MUST fire (sensitivity)
and which MUST stay silent (specificity).  Running the whole battery on
every change to the checks is the regression gate: it measures both that
the tools still catch real errors and — the cardinal rule of a forensic
tool — that they never brand valid data impossible (a false accusation is
the worst failure).

A case file is JSON at ``calibration/cases/<slug>.json``:

    {
      "meta": {"label": "...", "source": "synthetic" | "doi:10.xxx/yyy",
               "ground_truth": "why the expected findings are known",
               "notes": "..."},
      "table": { <run_table_checks schema> } | null,
      "text":  "<prose with reported inferential statistics>" | null,
      "expected": {
         "must_detect": [
             {"check": "grim", "target_contains": "treatment",
              "min_verdict": "FLAG"}
         ],
         "must_pass": [
             {"check": "grim", "target_contains": "control"}
         ]
      }
    }

Verdict ordering for ``min_verdict``: ``FAIL > FLAG > (PASS,
UNDETERMINED)``.  ``must_detect`` with ``min_verdict`` FLAG is satisfied by
a FAIL or a FLAG; ``min_verdict`` FAIL only by a FAIL.  A ``must_pass``
guards against over-flagging: it is satisfied only by a matching finding
whose verdict is exactly PASS — a FLAG/FAIL (a false accusation), an
UNDETERMINED, or no matching finding at all all fail the specificity gate.

Depends only on the standard library plus the two committed forensic
modules (``forensic_report`` and ``reported_stats``).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

# Built-in public case battery: repo-root/calibration/cases (this file is
# paperscope/analysis/calibration.py, so parents[2] is the repo root).
BUILTIN_CASES_DIR = Path(__file__).resolve().parents[2] / "calibration" / "cases"

# Verdict ranking for min_verdict comparisons.  PASS and UNDETERMINED tie
# at the bottom: neither is "bad news", so a must_detect asking for FLAG is
# never satisfied by either.
_RANK = {"UNDETERMINED": 0, "PASS": 0, "FLAG": 1, "FAIL": 2}


def _verdict_satisfies(verdict: str, min_verdict: str) -> bool:
    """Does ``verdict`` reach at least ``min_verdict`` (see _RANK)?"""
    return _RANK.get(verdict, 0) >= _RANK.get(min_verdict, 0)


def _matching(findings: List[dict], check: str, target_contains: str,
              target: Optional[str] = None) -> List[dict]:
    """Findings from ``check`` matching the target.

    If ``target`` is given it must equal the finding's target exactly;
    otherwise the finding's target must contain ``target_contains``.
    """
    out = []
    for f in findings:
        if f.get("check") != check:
            continue
        ftarget = str(f.get("target", ""))
        if target is not None:
            if ftarget == target:
                out.append(f)
        elif (target_contains or "") in ftarget:
            out.append(f)
    return out


# Known keys inside a case's ``expected`` block — anything else is a typo
# (e.g. ``must_deteect``) that would silently drop an assertion from the gate.
_EXPECTED_KEYS = {"must_detect", "must_pass"}


def validate_case(case: dict) -> List[str]:
    """Return a list of schema problems with a case (empty list = valid).

    A calibration case that asserts nothing, or whose ``expected`` block
    has a mistyped key, would pass the gate vacuously — the gate is the
    regression net, so these are hard errors, not warnings.
    """
    if case.get("_error"):
        return [str(case["_error"])]
    expected = case.get("expected")
    if not isinstance(expected, dict):
        return ["'expected' is missing or not an object"]
    errors: List[str] = []
    unknown = set(expected) - _EXPECTED_KEYS
    if unknown:
        errors.append(
            f"unknown key(s) in 'expected': {sorted(unknown)} "
            f"(typo? valid keys are must_detect / must_pass)")
    md = expected.get("must_detect") or []
    mp = expected.get("must_pass") or []
    if not md and not mp:
        errors.append(
            "case asserts nothing — needs at least one must_detect or "
            "must_pass entry (an empty 'expected' passes vacuously)")
    for i, e in enumerate(md):
        if not isinstance(e, dict) or not e.get("check"):
            errors.append(f"must_detect[{i}] is missing a 'check'")
    for i, e in enumerate(mp):
        if not isinstance(e, dict) or not e.get("check"):
            errors.append(f"must_pass[{i}] is missing a 'check'")
    return errors


def match_findings(findings: List[dict], expected: dict) -> dict:
    """
    Match a flat list of findings against a case's ``expected`` block.

    Returns ``{"hits": [...], "misses": [...], "false_passes": [...]}``:

      - a ``must_detect`` is a *hit* when some matching finding reaches its
        ``min_verdict`` (default FLAG), otherwise a *miss* (no matching
        finding, or none strong enough);
      - a ``must_pass`` is a specificity guard: it lands in nothing when a
        matching PASS finding exists, and in ``false_passes`` otherwise (a
        matching FLAG/FAIL — a false accusation — an UNDETERMINED, or no
        matching finding at all).

    Every entry is annotated with the best matching verdict actually seen
    so a mismatch report can say what went wrong.
    """
    expected = expected or {}
    hits: List[dict] = []
    misses: List[dict] = []
    false_passes: List[dict] = []

    for exp in expected.get("must_detect", []) or []:
        check = exp.get("check")
        sub = exp.get("target_contains", "")
        target = exp.get("target")
        min_verdict = exp.get("min_verdict", "FLAG")
        matches = _matching(findings, check, sub, target)
        best = max((f.get("verdict", "UNDETERMINED") for f in matches),
                   key=lambda v: _RANK.get(v, 0), default=None)
        # A planted-error assertion must identify its finding UNAMBIGUOUSLY:
        # zero matches can't confirm it, and >1 substring match (e.g.
        # "treatment" also hitting "pretreatment") could let an unrelated
        # FAIL satisfy the gate while the intended target is only PASS.
        # Require exactly one match (or an exact 'target'), then check it.
        if not matches:
            reason = "no finding matched"
            satisfied = False
        elif len(matches) > 1 and target is None:
            reason = (f"ambiguous: {len(matches)} findings matched "
                      f"target_contains {sub!r} — narrow it or use exact 'target'")
            satisfied = False
        else:
            satisfied = all(
                _verdict_satisfies(f.get("verdict", "UNDETERMINED"), min_verdict)
                for f in matches)
            reason = None if satisfied else (
                f"matched finding did not reach {min_verdict} (best {best})")
        record = {
            "check": check,
            "target_contains": sub,
            "min_verdict": min_verdict,
            "matched": len(matches),
            "best_verdict": best,
            "reason": reason,
        }
        (hits if satisfied else misses).append(record)

    for exp in expected.get("must_pass", []) or []:
        check = exp.get("check")
        sub = exp.get("target_contains", "")
        matches = _matching(findings, check, sub)
        best = max((f.get("verdict", "UNDETERMINED") for f in matches),
                   key=lambda v: _RANK.get(v, 0), default=None)
        passed = bool(matches) and all(
            f.get("verdict") == "PASS" for f in matches)
        if not passed:
            false_passes.append({
                "check": check,
                "target_contains": sub,
                "matched": len(matches),
                "best_verdict": best,
            })

    return {"hits": hits, "misses": misses, "false_passes": false_passes}


def load_cases(dirs: List[str]) -> List[dict]:
    """
    Read every ``*.json`` case file directly under each directory in
    ``dirs``.

    Non-JSON files are skipped, a missing directory is tolerated (nothing
    contributed), and an unreadable/invalid JSON file is skipped with its
    path recorded under the returned case's ``_error`` key so the harness
    surfaces it rather than crashing.  Each returned case carries a
    ``_path`` key with its source file.
    """
    cases: List[dict] = []
    for d in dirs:
        base = Path(d)
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.json")):
            try:
                case = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                cases.append({
                    "_path": str(path),
                    "_error": f"could not load ({type(exc).__name__}: {exc})",
                    "meta": {"label": path.name, "source": "?"},
                    "table": None, "text": None,
                    "expected": {"must_detect": [], "must_pass": []},
                })
                continue
            if not isinstance(case, dict):
                continue
            case.setdefault("_path", str(path))
            cases.append(case)
    return cases


def run_case(case: dict) -> dict:
    """
    Run one case's table through ``run_table_checks`` and its text through
    ``check_reported_tests`` (either may be null), match the combined
    findings against ``case['expected']``, and return a per-case result:

        {"label", "source", "findings", "hits", "misses",
         "false_passes", "ok"}

    ``ok`` is True only when every ``must_detect`` fired to at least its
    ``min_verdict`` and no ``must_pass`` was falsely flagged.
    """
    # Lazy imports: run_table_checks pulls in scipy via forensic_stats.
    from .forensic_report import run_table_checks
    from .reported_stats import check_reported_tests

    meta = case.get("meta") or {}
    findings: List[dict] = []

    # A load error or a schema problem makes the case unusable: fail it
    # loudly rather than let it pass the gate having asserted nothing.
    schema_errors = validate_case(case)
    if schema_errors:
        return {
            "label": meta.get("label", case.get("_path", "?")),
            "source": meta.get("source", "?"),
            "findings": [],
            "hits": [], "misses": [],
            "false_passes": [],
            "error": "; ".join(schema_errors),
            "ok": False,
        }

    table = case.get("table")
    if table is not None:
        findings.extend(run_table_checks(table, source=str(meta.get("label", "")))
                        ["findings"])

    text = case.get("text")
    if text is not None:
        findings.extend(check_reported_tests(text, source=str(meta.get("label", "")))
                        ["findings"])

    matched = match_findings(findings, case.get("expected") or {})
    ok = not matched["misses"] and not matched["false_passes"]
    return {
        "label": meta.get("label", case.get("_path", "?")),
        "source": meta.get("source", "?"),
        "findings": findings,
        "hits": matched["hits"],
        "misses": matched["misses"],
        "false_passes": matched["false_passes"],
        "ok": ok,
    }


def _blank_check_counts() -> dict:
    return {"detected": 0, "missed": 0,
            "correctly_passed": 0, "falsely_flagged": 0}


def calibrate(dirs: List[str]) -> dict:
    """
    Load and run every case under ``dirs`` and aggregate into a Report-ish
    dict:

        {"n_cases", "per_check": {check: {detected, missed,
              correctly_passed, falsely_flagged}},
         "totals": {detected, missed, correctly_passed, falsely_flagged},
         "sensitivity", "specificity",
         "cases": [run_case(...), ...],
         "mismatches": [{label, misses, false_passes, error?}, ...],
         "summary": "<one line>"}

    ``sensitivity = detected / (detected + missed)`` (are real errors
    caught?) and ``specificity = correctly_passed / (correctly_passed +
    falsely_flagged)`` (is valid data left alone?).  Both are ``None`` when
    their denominator is zero.
    """
    cases = load_cases(dirs)
    per_check: dict = {}
    totals = _blank_check_counts()
    case_results: List[dict] = []
    mismatches: List[dict] = []

    def bump(check: str, key: str) -> None:
        per_check.setdefault(check, _blank_check_counts())[key] += 1
        totals[key] += 1

    for case in cases:
        result = run_case(case)
        case_results.append(result)
        # must_detect outcomes: a hit is detected, a miss is missed
        for hit in result["hits"]:
            bump(hit["check"], "detected")
        for miss in result["misses"]:
            bump(miss["check"], "missed")
        # must_pass outcomes: derive correctly_passed vs falsely_flagged
        expected = case.get("expected") or {}
        flagged_keys = {(fp["check"], fp["target_contains"])
                        for fp in result["false_passes"]}
        for exp in expected.get("must_pass", []) or []:
            key = (exp.get("check"), exp.get("target_contains", ""))
            if key in flagged_keys:
                bump(exp.get("check"), "falsely_flagged")
            else:
                bump(exp.get("check"), "correctly_passed")
        if not result["ok"]:
            entry = {
                "label": result["label"],
                "misses": result["misses"],
                "false_passes": result["false_passes"],
            }
            if result.get("error"):
                entry["error"] = result["error"]
            mismatches.append(entry)

    det, miss = totals["detected"], totals["missed"]
    cp, ff = totals["correctly_passed"], totals["falsely_flagged"]
    sensitivity = det / (det + miss) if (det + miss) else None
    specificity = cp / (cp + ff) if (cp + ff) else None

    def _pct(x: Optional[float]) -> str:
        return "n/a" if x is None else f"{x:.0%}"

    summary = (
        f"{len(cases)} cases, {len(mismatches)} mismatch(es) | "
        f"sensitivity {_pct(sensitivity)} ({det}/{det + miss} must-detect) | "
        f"specificity {_pct(specificity)} ({cp}/{cp + ff} must-pass)"
    )

    return {
        "n_cases": len(cases),
        "per_check": per_check,
        "totals": totals,
        "sensitivity": sensitivity,
        "specificity": specificity,
        "cases": case_results,
        "mismatches": mismatches,
        "summary": summary,
    }
