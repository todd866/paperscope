#!/usr/bin/env python3
"""
statcheck-style reported-statistics parser.

Extracts APA-ish inferential statistics (t, F, chi-squared, r, z with
their reported p-values) from plain paper text, recomputes each p-value
from the printed test statistic, and reports consistency findings using
the shared Finding/Report contract in forensic_report.py.

The recomputation is *interval-safe*: a printed statistic (and any
decimal df) is treated as a rounding interval of ± half a unit of its
last printed digit, and the reported p is compared against the whole
recomputed-p range.  Because p is monotone in each argument, evaluating
the interval endpoints bounds the range exactly — a statistic can never
FAIL because of honest rounding (the cardinal rule of a forensic tool).

Verdict semantics:
    PASS  — reported p is consistent with the recomputed range
    FLAG  — inconsistent (reporting error), or consistent only under a
            one-tailed recomputation
    FAIL  — decision error (the recomputed range sits entirely on the
            other side of alpha = .05 from the reported p), or the
            printed numbers are impossible (|r| >= 1, df <= 0,
            negative F or chi-squared)
    UNDETERMINED — the p could not be recomputed; never bad news

Extraction is conservative: no match, no claim.  A parsing or input
problem never produces FAIL.

Usage:
    from paperscope.analysis.reported_stats import check_reported_tests
    report = check_reported_tests(open("paper.txt").read(), "paper.txt")

Ref: Nuijten, Hartgerink, van Assen, Epskamp & Wicherts (2016)
     "The prevalence of statistical reporting errors in psychology"
     doi:10.3758/s13428-015-0664-2 (statcheck)
"""

from __future__ import annotations

import math
import re
from typing import List, Optional, Tuple

from scipy import stats as sp

from paperscope.analysis.forensic_report import build_report, make_finding
from paperscope.analysis.forensic_stats import _dp_from_str

ALPHA = 0.05
_EPS = 1e-12
_REF = "Nuijten et al. 2016 (statcheck)"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

# A printed number: optional ASCII or unicode minus, "3.16", "38", ".42"
_NUM = r'[-−]?(?:\d+(?:\.\d+)?|\.\d+)'
_DF = r'\d+(?:\.\d+)?'          # df may be decimal (Welch correction)
_PNUM = r'(?:\d+(?:\.\d+)?|\.\d+)'

# "= 3.16" (also tolerates "≈")
_EQ = r'\s*[=≈]\s*'

# ", p = .003" / "; p<0.003" / ", p ≈ .05" / ", ns" / ", p = ns"
_P_TAIL = (
    r'\s*[,;]\s*'
    r'(?:[pP]\s*(?P<pop>[=<>≈])\s*(?P<pnum>' + _PNUM + r')'
    r'|(?:[pP]\s*=\s*)?(?P<ns>ns)(?![A-Za-z]))'
)

# Guard against near-misses like "page(3) = 4": the statistic letter
# must not be the tail of a word.
_HEAD = r'(?<![A-Za-z0-9_])'

_PATTERNS: List[Tuple[str, "re.Pattern"]] = [
    ('t', re.compile(
        _HEAD + r't\s*\(\s*(?P<df1>' + _DF + r')\s*\)' +
        _EQ + r'(?P<val>' + _NUM + r')' + _P_TAIL)),
    ('F', re.compile(
        _HEAD + r'F\s*\(\s*(?P<df1>' + _DF + r')\s*,\s*(?P<df2>' +
        _DF + r')\s*\)' + _EQ + r'(?P<val>' + _NUM + r')' + _P_TAIL)),
    # chi2 / χ² / Χ2 / x2, optionally with ", N = 320" inside the parens
    ('chi2', re.compile(
        _HEAD + r'(?:chi2|chi-squared?|[χΧ]\s?[2²]|[xX]2)\s*'
        r'\(\s*(?P<df1>' + _DF + r')\s*(?:,\s*N\s*=\s*\d+\s*)?\)' +
        _EQ + r'(?P<val>' + _NUM + r')' + _P_TAIL)),
    ('r', re.compile(
        _HEAD + r'r\s*\(\s*(?P<df1>' + _DF + r')\s*\)' +
        _EQ + r'(?P<val>' + _NUM + r')' + _P_TAIL)),
    ('z', re.compile(
        _HEAD + r'z' + _EQ + r'(?P<val>' + _NUM + r')' + _P_TAIL)),
]


def _to_float(s: str) -> float:
    """Parse a printed number, tolerating the unicode minus sign."""
    return float(s.replace('−', '-'))


def extract_reported_tests(text: str) -> List[dict]:
    """
    Regex-extract APA-ish reported inferential statistics from text.

    Recognised forms (variable spacing, unicode minus, "≈", decimal
    Welch df, "p = .003" / "p=0.003" / "p < .001" / "p > .05" / "ns"):

        t(df) = v, p <op> q
        F(df1, df2) = v, p <op> q
        chi2/χ²/Χ2/x2(df[, N = n]) = v, p <op> q
        r(df) = v, p <op> q
        z = v, p <op> q

    Returns a list of extraction dicts, sorted by position:
        {"stat": "t"|"F"|"chi2"|"r"|"z", "df1": float|None,
         "df2": float|None, "value": float, "value_str": "<as printed>",
         "p_op": "="|"<"|">"|"ns", "p": float|None, "p_str": "...",
         "anchor": "<exact matched text>", "start": int, "end": int}
    (plus "df1_str"/"df2_str", kept so the checker can honour the
    printed precision of decimal dfs).
    """
    extractions = []
    for stat, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            groups = m.groupdict()
            value_str = groups['val']
            df1_str = groups.get('df1')
            df2_str = groups.get('df2')
            if groups.get('ns') is not None:
                p_op, p, p_str = 'ns', None, groups['ns']
            else:
                # "≈" is a claim of equality at the printed precision
                p_op = '=' if groups['pop'] == '≈' else groups['pop']
                p_str = groups['pnum']
                p = float(p_str)
            extractions.append({
                'stat': stat,
                'df1': float(df1_str) if df1_str is not None else None,
                'df2': float(df2_str) if df2_str is not None else None,
                'df1_str': df1_str,
                'df2_str': df2_str,
                'value': _to_float(value_str),
                'value_str': value_str,
                'p_op': p_op,
                'p': p,
                'p_str': p_str,
                'anchor': m.group(0),
                'start': m.start(),
                'end': m.end(),
            })
    # Sort by position; drop any overlapping matches (keep the earliest)
    extractions.sort(key=lambda e: (e['start'], -e['end']))
    result = []
    last_end = -1
    for e in extractions:
        if e['start'] >= last_end:
            result.append(e)
            last_end = e['end']
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 2. P-VALUE RECOMPUTATION
# ═══════════════════════════════════════════════════════════════════════════════

def recompute_p(stat: str, value: float, df1: Optional[float] = None,
                df2: Optional[float] = None) -> float:
    """
    Recompute the (two-tailed) p-value for a reported test statistic.

        t:    2 * sf(|t|, df1)
        F:    sf(F, df1, df2)
        chi2: sf(x, df1)
        r:    converted to t = r * sqrt(df1 / (1 - r^2)), then as t
        z:    2 * sf(|z|)

    Raises ValueError on impossible inputs (df <= 0, |r| >= 1,
    negative F/chi2, unknown statistic) — a clean error, never a verdict.
    """
    if stat == 't':
        if df1 is None or df1 <= 0:
            raise ValueError(f"t-test requires df > 0 (got {df1})")
        return float(sp.t.sf(abs(value), df1) * 2)
    if stat == 'F':
        if df1 is None or df2 is None or df1 <= 0 or df2 <= 0:
            raise ValueError(f"F-test requires two dfs > 0 (got {df1}, {df2})")
        if value < 0:
            raise ValueError(f"F cannot be negative (got {value})")
        return float(sp.f.sf(value, df1, df2))
    if stat == 'chi2':
        if df1 is None or df1 <= 0:
            raise ValueError(f"chi2 requires df > 0 (got {df1})")
        if value < 0:
            raise ValueError(f"chi2 cannot be negative (got {value})")
        return float(sp.chi2.sf(value, df1))
    if stat == 'r':
        if df1 is None or df1 <= 0:
            raise ValueError(f"r-test requires df > 0 (got {df1})")
        if abs(value) >= 1:
            raise ValueError(f"|r| must be < 1 (got {value})")
        t_val = value * math.sqrt(df1 / (1 - value ** 2))
        return float(sp.t.sf(abs(t_val), df1) * 2)
    if stat == 'z':
        return float(sp.norm.sf(abs(value)) * 2)
    raise ValueError(f"unknown statistic {stat!r}")


def _value_corners(stat: str, value: float, value_str: str) -> List[float]:
    """
    Endpoints of the rounding interval of the printed statistic
    (± half a unit of its last printed digit).  For sign-symmetric
    statistics (t, r, z) the corners are magnitudes; for F/chi2 the
    lower corner is clamped at 0.
    """
    half_ulp = 0.5 * 10 ** -_dp_from_str(value_str)
    lo, hi = value - half_ulp, value + half_ulp
    if stat in ('F', 'chi2'):
        return [max(0.0, lo), hi]
    # t / r / z: p depends on |stat|
    if lo <= 0.0 <= hi:
        corners = [0.0, max(abs(lo), abs(hi))]
    else:
        corners = sorted([abs(lo), abs(hi)])
    if stat == 'r':
        # keep magnitudes strictly below 1 (p -> ~0 at the boundary)
        corners = [min(c, 1 - 1e-9) for c in corners]
    return corners


def _df_corners(df: Optional[float], df_str: Optional[str]) -> List:
    """df ± half-ulp when the df was printed with decimals (Welch)."""
    if df is None:
        return [None]
    if df_str and '.' in df_str:
        half_ulp = 0.5 * 10 ** -_dp_from_str(df_str)
        return [max(df - half_ulp, 1e-9), df + half_ulp]
    return [df]


def _recomputed_p_range(ext: dict, one_tailed: bool = False
                        ) -> Tuple[float, float]:
    """
    Recompute p over the rounding intervals of the printed statistic
    and dfs.  p is monotone in each argument, so evaluating every
    corner combination bounds the range exactly.
    """
    p_values = []
    for v in _value_corners(ext['stat'], ext['value'], ext['value_str']):
        for d1 in _df_corners(ext['df1'], ext['df1_str']):
            for d2 in _df_corners(ext['df2'], ext['df2_str']):
                p = recompute_p(ext['stat'], v, d1, d2)
                p_values.append(p / 2 if one_tailed else p)
    return min(p_values), max(p_values)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CONSISTENCY RULES (statcheck semantics, interval-safe)
# ═══════════════════════════════════════════════════════════════════════════════

def _consistent(p_lo: float, p_hi: float, p_op: str,
                p: Optional[float], p_str: str) -> bool:
    """Is the recomputed-p interval consistent with the reported p?"""
    if p_op == 'ns':
        # "ns" is treated as a claim that p > .05
        return p_hi > ALPHA - _EPS
    if p_op == '=':
        # "p = q" printed to d decimals: consistent if the recomputed
        # interval overlaps q's own rounding interval
        half_ulp = 0.5 * 10 ** -_dp_from_str(p_str)
        return (p_lo <= p + half_ulp + _EPS and
                p_hi >= max(0.0, p - half_ulp) - _EPS)
    if p_op == '<':
        return p_lo < p + _EPS       # interval reaches below q
    if p_op == '>':
        return p_hi > p - _EPS       # interval reaches above q
    return True  # unknown operator: extraction was conservative, no claim


def _reported_claims_significance(p_op: str, p: Optional[float]
                                  ) -> Optional[bool]:
    """
    Does the reported p claim significance at alpha = .05?  Returns
    None when the claim is ambiguous (e.g. "p = .05", "p < .10") —
    ambiguity always softens the verdict.
    """
    if p_op == 'ns':
        return False
    if p is None:
        return None
    if p_op == '<':
        return True if p <= ALPHA + _EPS else None
    if p_op == '>':
        return False if p >= ALPHA - _EPS else None
    # "p = q"
    if p < ALPHA - _EPS:
        return True
    if p > ALPHA + _EPS:
        return False
    return None  # exactly at alpha — ambiguous


def _reported_p_repr(ext: dict) -> str:
    """Human rendering of the reported p claim."""
    if ext['p_op'] == 'ns':
        return "ns (p > .05)"
    return f"p {ext['p_op']} {ext['p_str']}"


def _target(ext: dict) -> str:
    """Human label for the statistic, e.g. 't(37.4) = 2.10'."""
    if ext['stat'] == 'z':
        return f"z = {ext['value_str']}"
    dfs = ext['df1_str']
    if ext['df2_str'] is not None:
        dfs += f", {ext['df2_str']}"
    return f"{ext['stat']}({dfs}) = {ext['value_str']}"


def _round6(x: float) -> float:
    """Trim floats for readable JSON output (6 significant digits)."""
    return float(f"{x:.6g}")


def _finding_for(ext: dict) -> dict:
    """Apply the verdict rules to one extraction, returning a Finding."""
    target = _target(ext)
    reported = _reported_p_repr(ext)
    inputs = {
        'stat': ext['stat'],
        'value': ext['value'],
        'dfs': [ext['df1'], ext['df2']],
        'p_op': ext['p_op'],
        'reported_p': ext['p'],
        'recomputed_p_range': None,
    }

    def finding(verdict, detail):
        return make_finding('p_recalculation', verdict, target, inputs,
                            detail, _REF, anchor=ext['anchor'])

    # ── A reported p outside [0, 1] is garbled, not a decision error:
    #    we cannot judge consistency against a non-probability, and it is
    #    never evidence the analysis was wrong (usually a typo) ──
    if ext['p'] is not None and not (0.0 <= ext['p'] <= 1.0):
        return finding('UNDETERMINED', (
            f"UNDETERMINED: {target}: reported p = {ext['p_str']} is not a "
            f"valid probability (outside [0, 1]) — cannot check, not "
            f"evidence of error"))

    # ── Impossible as printed (the only FAILs not needing recomputation) ──
    if ext['stat'] == 'r':
        # Only impossible if EVERY value rounding to the printed r has
        # |r| >= 1.  "1.00" (interval [0.995, 1.005]) is a perfect or
        # near-perfect correlation, not an error; "1.07" is impossible.
        r_half_ulp = 0.5 * 10 ** -_dp_from_str(ext['value_str'])
        if abs(ext['value']) - r_half_ulp >= 1.0 - _EPS:
            return finding('FAIL', (
                f"FAIL: {target}: impossible as printed — even allowing for "
                f"rounding, |r| >= 1 (a correlation cannot reach 1 in a test "
                f"statistic)"))
        # otherwise fall through: _value_corners clamps |r| below 1 so the
        # normal p-consistency check runs (p -> ~0 at the boundary)
    for df, name in ((ext['df1'], 'df'), (ext['df2'], 'second df')):
        if df is not None and df <= 0:
            return finding('FAIL', (
                f"FAIL: {target}: impossible as printed — {name} must "
                f"be positive"))
    if ext['stat'] in ('F', 'chi2') and ext['value'] < 0:
        return finding('FAIL', (
            f"FAIL: {target}: impossible as printed — "
            f"{ext['stat']} cannot be negative"))

    # ── Recompute over the rounding interval of the printed numbers ──
    try:
        p_lo, p_hi = _recomputed_p_range(ext)
    except (ValueError, OverflowError) as exc:
        # A computation problem is never evidence against the paper
        return finding('UNDETERMINED', (
            f"UNDETERMINED: {target}: could not recompute p ({exc}) — "
            f"not evidence of error"))
    inputs['recomputed_p_range'] = [_round6(p_lo), _round6(p_hi)]
    p_range = f"[{p_lo:.4g}, {p_hi:.4g}]"

    if _consistent(p_lo, p_hi, ext['p_op'], ext['p'], ext['p_str']):
        return finding('PASS', (
            f"PASS: {target}: recomputed two-tailed p range {p_range} "
            f"is consistent with reported {reported} (within rounding)"))

    # ── Inconsistent: try a one-tailed rescue first (t, r, z only) ──
    if ext['stat'] in ('t', 'r', 'z'):
        ot_lo, ot_hi = _recomputed_p_range(ext, one_tailed=True)
        if _consistent(ot_lo, ot_hi, ext['p_op'], ext['p'], ext['p_str']):
            return finding('FLAG', (
                f"FLAG: {target}: two-tailed p range {p_range} is "
                f"inconsistent with reported {reported}, but a one-tailed "
                f"recomputation ([{ot_lo:.4g}, {ot_hi:.4g}]) matches — "
                f"possibly an unstated one-tailed test, not proven "
                f"impossible"))

    # ── Decision error only when the recomputed range sits entirely on
    #    the other side of alpha = .05 from an unambiguous claim ──
    claims_sig = _reported_claims_significance(ext['p_op'], ext['p'])
    if p_lo > ALPHA + _EPS:
        recomputed_side = False       # entirely non-significant
    elif p_hi < ALPHA - _EPS:
        recomputed_side = True        # entirely significant
    else:
        recomputed_side = None        # straddles alpha — soften
    if claims_sig is not None and recomputed_side is not None \
            and claims_sig != recomputed_side:
        return finding('FAIL', (
            f"FAIL: {target}: recomputed two-tailed p range {p_range} "
            f"sits entirely on the other side of alpha = .05 from "
            f"reported {reported} — decision error"))

    return finding('FLAG', (
        f"FLAG: {target}: recomputed two-tailed p range {p_range} is "
        f"inconsistent with reported {reported}, but the significance "
        f"decision at alpha = .05 does not flip — reporting error, "
        f"not proven impossible"))


# ═══════════════════════════════════════════════════════════════════════════════
# 4. TEXT -> REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def check_reported_tests(text: str, source: str = '') -> dict:
    """
    Extract every reported inferential statistic from `text`, recompute
    its p-value over the rounding interval of the printed numbers, and
    return a Report dict (mode "text", check name "p_recalculation").

    Extraction is conservative — unparseable statistics are skipped
    silently (no match, no claim) — and a computation problem yields
    UNDETERMINED, never FAIL.
    """
    findings = [_finding_for(ext) for ext in extract_reported_tests(text)]
    return build_report(source, 'text', findings)
