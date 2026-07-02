#!/usr/bin/env python3
"""
Shared Finding/Report contract for forensic-statistics tooling, plus the
table-mode check runner.

Both the table-driven forensic runner (``run_table_checks``, this module)
and the reported-statistics text parser (``reported_stats``) emit the same
plain-dict shapes, assembled through the helpers here so the pieces
compose.

A Finding is a plain dict:
    {"check": "<function name, e.g. grim>",
     "verdict": "PASS" | "FLAG" | "FAIL" | "UNDETERMINED",
     "target": "<human label, e.g. 'Q-scale / treatment group'>",
     "inputs": {<numbers fed in>},
     "detail": "<one-line explanation>",
     "ref": "<citation shorthand, e.g. 'Brown & Heathers 2017'>",
     optional "anchor": "<exact source text matched>",
     optional "page": <int, 1-based>}

A Report is:
    {"source": "<input path>", "mode": "table" | "text",
     "counts": {"PASS": n, "FLAG": n, "FAIL": n, "UNDETERMINED": n},
     "findings": [Finding, ...],
     "summary": "<one line>"}

Verdict semantics (cardinal rule of a forensic tool): FAIL means
arithmetically impossible as reported; FLAG means suspicious or
inconsistent but not proven impossible; UNDETERMINED is never bad news.
A parsing or input problem must never produce FAIL — when unsure,
verdicts soften, never harden.

Table-mode input schema (all sections optional — missing sections are
fine, unknown keys are ignored; means/SDs are best passed as *strings*
so trailing zeros survive for decimal-place inference):

    {
      "meta": {"paper": "...", "table": "..."},
      "scale": {"lo": 1, "hi": 7, "granularity": 1},
      "variables": [
        {"name": "Q-scale", "dp": 2,                # dp optional (else inferred
                                                # column-wise from strings)
         "groups": [{"name": "treatment", "n": 22,
                     "mean": "18.72", "sd": "9.41"}, ...],
         "baseline_p": 0.83}                    # collected for Carlisle
      ],
      "percentages": [
        {"name": "female", "group": "treatment", "n": 25,
         "percentage": 53.2, "dp": 1}
      ],
      "tests": [
        {"type": "ttest_independent", "target": "...",
         "mean1": .., "sd1": .., "n1": .., "mean2": .., "sd2": .., "n2": ..,
         "reported_p": 0.003},
        {"type": "ttest_paired", "target": "...",
         "mean_change": .., "sd_change": .., "n": .., "reported_p": ..},
        {"type": "anova_oneway", "target": "...",
         "means": [..], "sds": [..], "ns": [..],
         "reported_f": .., "reported_p": ..},
        {"type": "chi_squared", "target": "...", "table": [[..], [..]],
         "reported_chi2": .., "reported_p": ..}
      ],
      "pre_post": [{"name": "...", "sd_pre": .., "sd_post": ..,
                    "sd_change": ..}],
      "changes": [{"name": "...", "baseline": .., "end": ..,
                   "reported_change": ..}]
    }

Checks wired per section: variables -> grim + grimmer per group (plus
quick_sd_check when "scale" gives bounds, and variance_ratio_test across
a variable's groups), Carlisle-Stouffer-Fisher across ALL collected
baseline_p when there are >= 3; percentages -> grim_percentage; tests ->
the matching check_* recalculation; pre_post -> correlation_bound;
changes -> check_change_arithmetic.
"""

from __future__ import annotations

from typing import Callable, List, Optional

VERDICTS = ("PASS", "FLAG", "FAIL", "UNDETERMINED")

# Citation shorthand per check (see the forensic_stats docstrings for DOIs)
CHECK_REFS = {
    "grim": "Brown & Heathers 2017",
    "grim_percentage": "Brown & Heathers 2017",
    "grimmer": "Anaya 2016",
    "sprite": "Heathers et al. 2018",
    "quick_sd_check": "Heathers 2025",
    "variance_ratio_test": "Heathers 2025",
    "carlisle_stouffer_fisher": "Carlisle 2017",
    "check_ttest_independent": "Heathers 2025",
    "check_ttest_paired": "Heathers 2025",
    "check_anova_oneway": "Heathers 2025",
    "check_chi_squared": "Heathers 2025",
    "correlation_bound": "Jane 2024",
    "check_change_arithmetic": "Heathers 2025",
}


def verdict_of(result: dict) -> str:
    """
    Map a forensic_stats result dict to a Finding verdict.

    Recognised shapes (checked in this order):
      - 'possible' / 'plausible' tri-state:
            True -> PASS, False -> FAIL, None -> UNDETERMINED
      - 'consistent' tri-state (recalculation checks): a mismatch is a
            reporting discrepancy, not proven impossibility:
            True -> PASS, False -> FLAG, None -> UNDETERMINED
      - 'suspicious' bool (carlisle_stouffer_fisher):
            True -> FLAG, False -> PASS
      - 'flags' list (quick_sd_check etc.): non-empty -> FLAG, hardened
            to FAIL only when a flag itself says IMPOSSIBLE; empty -> PASS

    Cardinal-rule refinement: when a boolean key is False, the check's
    own detail prefix (vetted in forensic_stats) overrides the default —
    a False 'plausible' whose detail says "FLAG: ..." (e.g. a t-test
    p-value mismatch, suspicious but not proven impossible) softens to
    FLAG, and a False 'consistent' whose detail says "FAIL: ..." (e.g.
    End - Baseline contradicting the reported Change) is a genuine FAIL.

    Anything unrecognised (e.g. a SKIP / insufficient-data result) maps
    to UNDETERMINED — never harden on an unknown shape.
    """
    detail = str(result.get('detail', ''))
    for key, default in (('possible', 'FAIL'), ('plausible', 'FAIL'),
                         ('consistent', 'FLAG')):
        if key in result:
            value = result[key]
            if value is None:
                return 'UNDETERMINED'
            # bool(), not identity: comparisons inside forensic_stats can
            # yield numpy bools, and np.True_ is not the True singleton
            if bool(value):
                return 'PASS'
            # value is falsy: trust the check's own PASS/FLAG/FAIL label
            # when it gives one, otherwise fall back to the default
            if detail.startswith('FLAG'):
                return 'FLAG'
            if detail.startswith('FAIL'):
                return 'FAIL'
            return default
    if 'suspicious' in result:
        return 'FLAG' if result['suspicious'] else 'PASS'
    if 'flags' in result:
        flags = result.get('flags') or []
        if not flags:
            return 'PASS'
        if any('IMPOSSIBLE' in str(flag).upper() for flag in flags):
            return 'FAIL'
        return 'FLAG'
    return 'UNDETERMINED'


def verdict_from_result(result: dict) -> str:
    """Alias for verdict_of() — one canonical mapping, two entry names."""
    return verdict_of(result)


def make_finding(check: str, verdict: str, target: str, inputs: dict,
                 detail: str, ref: str,
                 anchor: Optional[str] = None,
                 page: Optional[int] = None) -> dict:
    """Assemble a Finding dict (see module docstring for the contract)."""
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict: {verdict!r}")
    finding = {
        'check': check,
        'verdict': verdict,
        'target': target,
        'inputs': inputs,
        'detail': detail,
        'ref': ref,
    }
    if anchor is not None:
        finding['anchor'] = anchor
    if page is not None:
        finding['page'] = page
    return finding


def finding_from_result(check: str, result: dict, target: str, inputs: dict,
                        ref: Optional[str] = None,
                        anchor: Optional[str] = None,
                        page: Optional[int] = None) -> dict:
    """
    Build a Finding straight from a raw check result: the verdict comes
    from verdict_of(), the detail is the check's own detail string, and
    the ref defaults to the CHECK_REFS shorthand for the check.
    """
    return make_finding(
        check,
        verdict_of(result),
        target,
        inputs,
        str(result.get('detail', '')),
        ref if ref is not None else CHECK_REFS.get(check, ''),
        anchor=anchor,
        page=page,
    )


def build_report(source: str, mode: str, findings: List[dict]) -> dict:
    """Assemble a Report dict with verdict counts and a one-line summary."""
    counts = {verdict: 0 for verdict in VERDICTS}
    for finding in findings:
        counts[finding['verdict']] += 1
    summary = (
        f"{len(findings)} checks: {counts['FAIL']} impossible, "
        f"{counts['FLAG']} flagged, {counts['PASS']} passed, "
        f"{counts['UNDETERMINED']} undetermined"
    )
    return {
        'source': source,
        'mode': mode,
        'counts': counts,
        'findings': findings,
        'summary': summary,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Table-mode runner
# ═══════════════════════════════════════════════════════════════════════════════

def _as_str(v) -> str:
    """Preserve strings (trailing zeros!); render numbers the same way
    forensic_stats' own dp inference does."""
    return v if isinstance(v, str) else f"{v}"


def _num(v) -> Optional[float]:
    """Coerce to float, or None if not a number."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v) -> Optional[int]:
    """Coerce to int (accepting exact floats like 22.0 and numeric
    strings like "22"), or None.  Parsing a string n matters: an
    unparsed n silently disables the n-aware sample-SD bound."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v) if v.is_integer() else None
    if isinstance(v, str):
        try:
            f = float(v.strip())
        except (ValueError, AttributeError):
            return None
        return int(f) if f.is_integer() else None
    return None


def _entries(table: dict, key: str) -> List[dict]:
    """A section's entries, tolerating a missing/None/non-list section."""
    section = table.get(key)
    if not isinstance(section, list):
        return []
    return [e for e in section if isinstance(e, dict)]


def _safe(check: str, fn: Callable, target: str, inputs: dict,
          **kwargs) -> dict:
    """
    Run one check and wrap it into a Finding.  Any exception (missing or
    malformed inputs) yields an UNDETERMINED finding — a parsing or input
    problem must never produce a FAIL.
    """
    try:
        result = fn(**kwargs)
    except Exception as exc:
        result = {
            'detail': (f"UNDETERMINED: could not run {check} "
                       f"({type(exc).__name__}: {exc}) — cannot test"),
        }
    if isinstance(result, list):
        # carlisle_stouffer_fisher auto-splits typed p-values into a list;
        # table mode only passes plain floats, but guard anyway by taking
        # the combined (last) entry rather than crashing
        result = result[-1] if result else {'detail': "UNDETERMINED: empty result"}
    if not isinstance(result, dict):
        result = {'detail': f"UNDETERMINED: {check} returned no result dict"}
    return finding_from_result(check, result, target, inputs)


def run_table_checks(table: dict, source: str = '') -> dict:
    """
    Run every applicable forensic check over a table spec (see module
    docstring for the schema) and return a Report dict.

    Missing sections are fine; unknown keys are ignored.  A non-dict
    input raises ValueError; per-entry input problems yield UNDETERMINED
    findings, never FAIL.
    """
    # Heavy import stays local to the runner: forensic_stats pulls in scipy
    from .forensic_stats import (
        carlisle_stouffer_fisher,
        check_anova_oneway,
        check_change_arithmetic,
        check_chi_squared,
        check_ttest_independent,
        check_ttest_paired,
        correlation_bound,
        grim,
        grim_percentage,
        grimmer,
        infer_column_dp,
        quick_sd_check,
        variance_ratio_test,
        _dp_from_str,
    )

    if not isinstance(table, dict):
        raise ValueError(
            "table-mode input must be a JSON object (dict) — see the "
            "forensic_report module docstring for the expected schema"
        )

    findings: List[dict] = []

    scale_spec = table.get("scale") if isinstance(table.get("scale"), dict) else {}
    granularity = _num(scale_spec.get("granularity")) or 1
    lo = _num(scale_spec.get("lo"))
    hi = _num(scale_spec.get("hi"))
    have_bounds = lo is not None and hi is not None

    # ── variables: GRIM + GRIMMER per group, quick SD check, variance ratio ──
    baseline_ps: List[float] = []
    for var in _entries(table, "variables"):
        vname = str(var.get("name", "variable"))
        groups = [g for g in (var.get("groups") or []) if isinstance(g, dict)]

        # Column-level dp: papers drop trailing zeros ("26.9" alongside
        # "11.26"), so when the variable doesn't state a dp, infer the
        # maximum across the column — separately for means and SDs
        mean_strs = [_as_str(g["mean"]) for g in groups
                     if g.get("mean") is not None]
        sd_strs = [_as_str(g["sd"]) for g in groups if g.get("sd") is not None]
        dp = _int(var.get("dp"))
        dp_mean = dp if dp is not None else (
            infer_column_dp(mean_strs) if mean_strs else None)
        dp_sd = dp if dp is not None else (
            infer_column_dp(sd_strs) if sd_strs else None)

        vr_sds: List[float] = []
        vr_ns: List[int] = []
        vr_labels: List[str] = []
        for g in groups:
            gname = str(g.get("name", "group"))
            target = f"{vname} / {gname}"
            n = _int(g.get("n"))
            mean = g.get("mean")
            sd = g.get("sd")

            if mean is not None and n is not None:
                findings.append(_safe(
                    "grim", grim, target,
                    {"mean": mean, "n": n, "scale": granularity,
                     "dp": dp_mean},
                    mean=_as_str(mean), n=n, scale=granularity, dp=dp_mean,
                ))
            if mean is not None and sd is not None and n is not None:
                findings.append(_safe(
                    "grimmer", grimmer, target,
                    {"mean": mean, "sd": sd, "n": n, "scale": granularity},
                    mean=_as_str(mean), sd=_as_str(sd), n=n,
                    scale=granularity, dp_mean=dp_mean, dp_sd=dp_sd,
                ))
            sd_f = _num(sd)
            # Require a known n: the correct sample-SD bound is
            # (range/2)*sqrt(floor(n/2)*ceil(n/2)/(n(n-1))), so without n
            # the check would fall back to the population bound and could
            # brand a valid small-sample SD "IMPOSSIBLE" — a false accusation.
            if sd_f is not None and have_bounds and n is not None:
                findings.append(_safe(
                    "quick_sd_check", quick_sd_check, target,
                    {"sd": sd_f, "n": n, "lo": lo, "hi": hi},
                    sd=sd_f, n=n, lo=lo, hi=hi, label=target,
                ))
            if sd_f is not None and n is not None:
                vr_sds.append(sd_f)
                vr_ns.append(n)
                vr_labels.append(gname)

        # variance_ratio_test wants >= 2 groups; skip cleanly otherwise
        if len(vr_sds) >= 2:
            findings.append(_safe(
                "variance_ratio_test", variance_ratio_test,
                f"{vname} / SDs across groups",
                {"sds": vr_sds, "ns": vr_ns},
                sds=vr_sds, ns=vr_ns, labels=vr_labels,
            ))

        bp = _num(var.get("baseline_p"))
        if bp is not None:
            baseline_ps.append(bp)

    # ── Carlisle across ALL collected baseline p-values (needs >= 3) ──
    if len(baseline_ps) >= 3:
        findings.append(_safe(
            "carlisle_stouffer_fisher", carlisle_stouffer_fisher,
            "Table 1 baseline p-values",
            {"p_values": baseline_ps},
            p_values=baseline_ps, label="Table 1 baseline p-values",
        ))

    # ── percentages -> GRIM for percentages ──
    for entry in _entries(table, "percentages"):
        name = str(entry.get("name", "percentage"))
        gname = entry.get("group")
        target = f"{name} / {gname}" if gname else name
        pct = entry.get("percentage")
        n = _int(entry.get("n"))
        dp = _int(entry.get("dp"))
        if dp is None:
            # a string percentage carries its own dp; otherwise match the
            # grim_percentage default of 1
            dp = _dp_from_str(pct) if isinstance(pct, str) else 1
        pct_f = _num(pct)
        inputs = {"percentage": pct, "n": entry.get("n"), "dp": dp}
        if pct_f is None or n is None:
            findings.append(finding_from_result(
                "grim_percentage",
                {'detail': (f"UNDETERMINED: percentage/n missing or "
                            f"non-numeric for {target} — cannot test")},
                target, inputs))
            continue
        findings.append(_safe(
            "grim_percentage", grim_percentage, target, inputs,
            percentage=pct_f, n=n, dp=dp,
        ))

    # ── tests -> the matching check_* recalculation ──
    for i, t in enumerate(_entries(table, "tests")):
        ttype = str(t.get("type", ""))
        target = str(t.get("target") or f"{ttype or 'test'} #{i + 1}")
        inputs = {k: v for k, v in t.items() if k not in ("type", "target")}
        if ttype == "ttest_independent":
            findings.append(_safe(
                "check_ttest_independent", check_ttest_independent,
                target, inputs,
                mean1=t.get("mean1"), sd1=t.get("sd1"), n1=t.get("n1"),
                mean2=t.get("mean2"), sd2=t.get("sd2"), n2=t.get("n2"),
                reported_p=t.get("reported_p"),
            ))
        elif ttype == "ttest_paired":
            findings.append(_safe(
                "check_ttest_paired", check_ttest_paired, target, inputs,
                mean_change=t.get("mean_change"),
                sd_change=t.get("sd_change"),
                n=t.get("n"), reported_p=t.get("reported_p"),
            ))
        elif ttype == "anova_oneway":
            findings.append(_safe(
                "check_anova_oneway", check_anova_oneway, target, inputs,
                means=t.get("means") or [], sds=t.get("sds") or [],
                ns=t.get("ns") or [],
                reported_f=t.get("reported_f"),
                reported_p=t.get("reported_p"),
            ))
        elif ttype == "chi_squared":
            findings.append(_safe(
                "check_chi_squared", check_chi_squared, target, inputs,
                observed=t.get("table"),
                reported_chi2=t.get("reported_chi2"),
                reported_p=t.get("reported_p"),
                label=target,
            ))
        else:
            # Unknown test type is an input problem — never a FAIL
            findings.append(finding_from_result(
                ttype or "unknown_test",
                {'detail': (f"UNDETERMINED: unknown test type "
                            f"'{ttype}' — cannot test")},
                target, inputs))

    # ── pre_post -> correlation bound from pre/post/change SDs ──
    for entry in _entries(table, "pre_post"):
        target = str(entry.get("name", "pre/post"))
        findings.append(_safe(
            "correlation_bound", correlation_bound, target,
            {"sd_pre": entry.get("sd_pre"), "sd_post": entry.get("sd_post"),
             "sd_change": entry.get("sd_change")},
            sd_pre=entry.get("sd_pre"), sd_post=entry.get("sd_post"),
            sd_change=entry.get("sd_change"),
        ))

    # ── changes -> End - Baseline = Change arithmetic ──
    for entry in _entries(table, "changes"):
        target = str(entry.get("name", "change"))
        findings.append(_safe(
            "check_change_arithmetic", check_change_arithmetic, target,
            {"baseline": entry.get("baseline"), "end": entry.get("end"),
             "reported_change": entry.get("reported_change")},
            baseline=entry.get("baseline"), end=entry.get("end"),
            reported_change=entry.get("reported_change"), label=target,
        ))

    return build_report(source, "table", findings)
