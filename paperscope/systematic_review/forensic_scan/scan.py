"""Top-level orchestrator: run the full forensic scan over a corpus directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from paperscope.systematic_review.forensic_scan.extract import (
    extract_pvalues,
    extract_effects,
    extract_mean_sd_n_triples,
    extract_funding_coi,
    extract_authors,
    extract_cohort_size,
    extract_positivity_mentions,
)
from paperscope.systematic_review.forensic_scan.aggregate import (
    p_curve_summary,
    last_digit_distribution,
    positivity_rate,
    industry_vs_positivity,
    salami_screen,
)


def scan_corpus(
    *,
    text_dir: str | Path,
    out_dir: str | Path,
    progress: Callable[[int, int], None] | None = None,
    limit: int = 0,
) -> dict:
    """Run the full forensic scan; write per-paper + aggregated JSONLs;
    return the corpus-level summary dict.

    Output files:
      - forensic-per-paper.jsonl   — per-paper summary fields
      - forensic-pvalues.jsonl     — every extracted p-value row
      - forensic-effects.jsonl     — every effect+CI row
      - forensic-mean-sd-n.jsonl   — every mean+SD+n triple
      - forensic-funding.jsonl     — funding/COI classification per paper
      - forensic-salami.jsonl      — author/cohort-size overlap flags
      - forensic-summary.json      — corpus-level aggregates (p-curve etc.)
    """
    text_dir = Path(text_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    txt_files = sorted(text_dir.glob("*.txt"))
    if limit:
        txt_files = txt_files[:limit]

    per_paper = []
    all_pvalues = []
    all_effects = []
    all_triples = []
    all_funding = []

    for i, p in enumerate(txt_files):
        if progress and i % 200 == 0:
            progress(i, len(txt_files))
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        pmid = p.stem
        pvals = extract_pvalues(text, pmid)
        effs = extract_effects(text, pmid)
        triples = extract_mean_sd_n_triples(text, pmid)
        funding = extract_funding_coi(text, pmid)
        positivity = extract_positivity_mentions(text)
        authors = extract_authors(text)
        cohort_n = extract_cohort_size(text)

        all_pvalues.extend(pvals)
        all_effects.extend(effs)
        all_triples.extend(triples)
        all_funding.append(funding)

        per_paper.append({
            "pmid": pmid,
            "n_pvalues": len(pvals),
            "n_effects": len(effs),
            "n_triples": len(triples),
            "n_wide_ci": sum(1 for e in effs if e["implausibly_wide"]),
            "n_ci_inconsistent": sum(1 for e in effs if not e["ci_consistent"]),
            **positivity,
            "funding_classification": funding["classification"],
            "industry_linked": funding["industry_linked"],
            "authors_set": sorted(authors),
            "cohort_size": cohort_n,
        })

    # Write JSONL outputs
    def _write_jsonl(path: Path, rows: list):
        with path.open("w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    _write_jsonl(out_dir / "forensic-per-paper.jsonl", per_paper)
    _write_jsonl(out_dir / "forensic-pvalues.jsonl", all_pvalues)
    _write_jsonl(out_dir / "forensic-effects.jsonl", all_effects)
    _write_jsonl(out_dir / "forensic-mean-sd-n.jsonl", all_triples)
    _write_jsonl(out_dir / "forensic-funding.jsonl", all_funding)

    # Aggregations
    pos_rows = [{"pmid": r["pmid"], "positivity_ratio": r["positivity_ratio"]} for r in per_paper]
    salami_flags = salami_screen([{"pmid": r["pmid"], "authors_set": set(r["authors_set"]),
                                    "cohort_size": r["cohort_size"]} for r in per_paper])
    _write_jsonl(out_dir / "forensic-salami.jsonl", salami_flags)

    summary = {
        "n_papers_scanned": len(per_paper),
        "n_pvalues_extracted": len(all_pvalues),
        "n_effects_extracted": len(all_effects),
        "n_triples_extracted": len(all_triples),
        "p_curve": p_curve_summary(all_pvalues),
        "last_digit": last_digit_distribution(all_pvalues),
        "positivity": positivity_rate(pos_rows),
        "industry_vs_positivity": industry_vs_positivity(all_funding, pos_rows),
        "n_salami_flags": len(salami_flags),
    }
    (out_dir / "forensic-summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary
