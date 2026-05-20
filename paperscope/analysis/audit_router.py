"""Per-paper validity audit router: classify study type, run the matching battery.

paperscope already has the validity *components* (overclaiming, missing_methods,
forensic_stats). This module adds the two pieces they lacked: a study-type classifier
and a routing table, so any paper can be audited by the battery that fits it -- and the
ingest pipeline can run that automatically (see ingest.pipeline ``audit=True``).

Study types and their batteries (PROFILES):
  diagnostic_ml : overclaiming + missing_methods + ml_validity
  prognostic    : overclaiming + ml_validity
  rct           : overclaiming + forensic_stats (GRIM, when table data supplied)
  method        : overclaiming
  other         : overclaiming

``ml_validity`` is a set of ML-diagnostic red-flag heuristics (external test / CI /
class-imbalance / data-leakage / comparator realism) -- the checks that matter for
AUC-reporting ML papers, where GRIM does not apply. Heuristic (keyword presence in full
text = lower bound), pending an LLM refinement.

Prototyped in a downstream systematic-review project, generalised here.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# -- study-type classification ------------------------------------------------
# Exclusion-first ordering + dropped over-matching 'identif'/'recogni' stems. Validated on
# a 25-paper LLM-rater sample in a downstream project: the naive 'any DIAG keyword' rule
# scored ~40% precision for diagnostic_ml; this routing reaches ~89%.
_DIAG = re.compile(r"diagnos|detect|classif|screen for|screening|differentiat|distinguish|grading|tumou?r staging|disease staging", re.I)
_RCT = re.compile(r"randomi[sz]ed controlled trial|\bRCT\b|placebo[- ]controlled|double[- ]blind|intention[- ]to[- ]treat|randomly assigned", re.I)
_PROG = re.compile(r"prognos|survival analysis|recurrence prediction|predict[a-z ]{0,25}(recurrence|survival|progression|conversion|onset|mortality|impairment|decline|treatment response|outcome)|risk of (developing|progression|conversion)|prognostic (model|signature|score|index)|time[- ]to[- ]event|hazard ratio", re.I)
_REVIEW = re.compile(r"systematic review|narrative review|scoping review|literature review|a review of|application and prospect|prospect of|overview of|state[- ]of[- ]the[- ]art", re.I)
_DISCOVERY = re.compile(r"mendelian randomi|genome[- ]wide association|\bgwas\b|single[- ]cell|transcriptomic atlas|enhancer hijack|structural variation|immunometabolic|multi[- ]omics|atlas of|molecular characterization|drug mechanism|quantitative trait loci", re.I)
_SEGM = re.compile(r"segmentation|surface reconstruction|image reconstruction|\bregistration\b|super[- ]resolution|vessel reconstruction", re.I)
_METHOD = re.compile(r"we propose|novel framework|foundation model|benchmark|new architecture|we present a (method|model|framework)", re.I)


def classify_study_type(text: str) -> str:
    """Heuristic study-type label from full text. Exclusion-first: route reviews,
    discovery/biology, and segmentation/method out before the diagnostic test, so a mere
    background mention of 'diagnosis' does not mislabel a non-diagnostic paper."""
    t = text[:20000]  # title/abstract/intro dominate the signal
    if _RCT.search(t):
        return "rct"
    if _REVIEW.search(t):
        return "review"
    if _DISCOVERY.search(t):
        return "discovery"
    if _SEGM.search(t):
        return "method"
    if _PROG.search(t):
        return "prognostic"
    if _DIAG.search(t):
        return "diagnostic_ml"
    if _METHOD.search(t):
        return "method"
    return "other"


PROFILES: Dict[str, List[str]] = {
    "diagnostic_ml": ["overclaiming", "missing_methods", "ml_validity"],
    "prognostic":    ["overclaiming", "ml_validity"],
    "rct":           ["overclaiming", "forensic_stats"],
    "discovery":     ["overclaiming"],
    "review":        ["overclaiming"],
    "method":        ["overclaiming"],
    "other":         ["overclaiming"],
}

# -- ML-diagnostic validity flags (paperscope had no equivalent) ---------------
_EXTERNAL = re.compile(r"external (validation|test|cohort|dataset)|independent (cohort|test|validation|dataset)|held[- ]out|multi[- ]?cent(er|re)|multi[- ]?site|prospective validation|out[- ]of[- ]distribution", re.I)
_CI = re.compile(r"confidence interval|95%\s*ci|credible interval|bootstrap", re.I)
_IMBALANCE = re.compile(r"imbalanc|smote|class weight|weighted (loss|cross|sampl)|oversampl|undersampl|resampl|stratified", re.I)
_LEAKAGE = re.compile(r"patient[- ]level split|subject[- ]wise|group[- ]wise|grouped (split|k[- ]?fold|cross)|prevent[a-z ]{0,20}leakage|data leakage", re.I)
_VS_HEALTHY = re.compile(r"healthy control|healthy subject|healthy volunteer|normal control|typically[- ]developing", re.I)
_VS_MIMIC = re.compile(r"differential diagnos|mimic|disease control|distinguish[a-z ]+from|differentiat[a-z ]+from|other [a-z]+ (disease|disorder|condition)", re.I)


def ml_validity(text: str) -> Dict:
    return {
        "external_validation": bool(_EXTERNAL.search(text)),
        "reports_ci": bool(_CI.search(text)),
        "imbalance_addressed": bool(_IMBALANCE.search(text)),
        "leakage_addressed": bool(_LEAKAGE.search(text)),
        "comparator": ("mimic_differential" if _VS_MIMIC.search(text)
                       else "healthy_easy" if _VS_HEALTHY.search(text) else "unclear"),
    }


def audit_paper(text: str, *, study_type: Optional[str] = None, model=None,
                run_overclaiming: bool = True, table_data: Optional[list] = None) -> Dict:
    """Audit one paper with the battery for its study type.

    Args:
        text: full paper text.
        study_type: override the classifier if known.
        model: pre-loaded embedding model for overclaiming (load once for batches).
        run_overclaiming: set False to skip the embedding-backed step (fast/offline).
        table_data: list of (mean, n, dp) tuples for GRIM, if extracted upstream.
    """
    st = study_type or classify_study_type(text)
    battery = PROFILES.get(st, ["overclaiming"])
    rec: Dict = {"study_type": st, "battery": battery}

    if "overclaiming" in battery and run_overclaiming:
        try:
            from .overclaiming import split_sections, detect_overclaiming
            oc = detect_overclaiming(split_sections(text), model=model)
            rec["overclaiming_score"] = round(oc.get("overall_overclaiming_score", 0.0), 3)
            rec["overclaiming_flags"] = oc.get("flags", [])
        except Exception as e:  # pragma: no cover - embedding/runtime issues
            rec["overclaiming_error"] = repr(e)[:120]

    if "missing_methods" in battery:
        try:
            from .missing_methods import detect_methods, check_missing_methods
            mm = check_missing_methods(detect_methods(text))
            rec["methods_identified"] = mm.get("methods_identified", [])
            rec["n_missing_complementary"] = len(mm.get("missing_complementary", []))
        except Exception as e:  # pragma: no cover
            rec["missing_methods_error"] = repr(e)[:120]

    if "ml_validity" in battery:
        rec["ml_validity"] = ml_validity(text)

    if "forensic_stats" in battery:
        if table_data:
            try:
                from .forensic_stats import grim
                rec["grim"] = [grim(m, n, dp=dp) for (m, n, dp) in table_data]
            except Exception as e:  # pragma: no cover
                rec["forensic_stats_error"] = repr(e)[:120]
        else:
            rec["forensic_stats"] = "skipped: needs extracted summary-stat table data"

    return rec


def _cli():  # pragma: no cover - thin CLI wrapper
    import argparse, json
    from pathlib import Path
    ap = argparse.ArgumentParser(description="Type-routed per-paper validity audit.")
    ap.add_argument("path", type=Path, help="a .txt file or a directory of .txt files")
    ap.add_argument("--no-overclaiming", action="store_true", help="skip embedding step")
    ap.add_argument("--out", type=Path, default=None, help="write JSONL here")
    args = ap.parse_args()

    files = sorted(args.path.glob("*.txt")) if args.path.is_dir() else [args.path]
    model = None
    if not args.no_overclaiming:
        try:
            from ..embed import load_model
            model = load_model()
        except Exception:
            model = None
    out = []
    for f in files:
        rec = {"id": f.stem, **audit_paper(f.read_text(encoding="utf-8", errors="ignore"),
                                           model=model, run_overclaiming=not args.no_overclaiming)}
        out.append(rec)
        print(f"{f.stem}: {rec['study_type']} -> {rec['battery']}")
    if args.out:
        args.out.write_text("\n".join(json.dumps(r) for r in out))
        print(f"wrote {len(out)} -> {args.out}")


if __name__ == "__main__":
    _cli()
