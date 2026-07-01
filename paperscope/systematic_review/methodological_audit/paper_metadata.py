"""Per-paper metadata document generator.

For each audited paper, consolidates all known data sources into a single
readable markdown document + a JSON sidecar with the same data structured.

Pulls from:
  - audit.sqlite (papers, ratings, cluster_assignments, audit_exclusions,
    rubric_versions)
  - corpus records JSONL (titles, authors, DOIs, MeSH)
  - forensic-per-paper.jsonl + forensic-v2-per-paper.jsonl (p-value counts,
    effect+CI flags, GRIM triples, positivity, funding/COI)
  - forensic-v2-salami.jsonl (cross-paper author × cohort flags)

Each output:
  metadata/<pmid>.md   — human-readable, ~10-30 lines
  metadata/<pmid>.json — machine-readable sidecar

Plus a top-level metadata/README.md index browseable by cluster, with
flags for in-corpus thesis voices (🗣) and post-hoc exclusions (⊘).

Usage:
    from paperscope.systematic_review.methodological_audit.paper_metadata import (
        generate_metadata_corpus,
    )
    generate_metadata_corpus(
        db_path="audit/audit.sqlite",
        out_dir="metadata/",
        forensic_dir="audit/",            # where forensic-*.jsonl live
        records_jsonl="corpus/records.jsonl",
        extra_records_jsonl="corpus/cinahl-records.jsonl",  # optional
        cluster_run_id="kmeans-20-2026-05-16",
    )
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path


DIM_ORDER = [
    "statistical_hygiene", "transparency", "construct_validity",
    "reproducibility", "novelty", "construct_adequacy",
    "screening_fit", "transparency_basic_disclosure",
    "transparency_review_process",
]


def _load_records_jsonl(path: Path) -> dict[str, dict]:
    out = {}
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            try:
                r = json.loads(line)
                pmid = str(r.get("pmid") or (f"cinahl-{r['ebsco_an']}" if r.get("ebsco_an") else ""))
                if pmid:
                    out[pmid] = r
            except Exception:
                pass
    return out


def _load_per_paper(path: Path) -> dict[str, dict]:
    out = {}
    if path.exists():
        for line in path.open():
            try:
                r = json.loads(line)
                out[r["pmid"]] = r
            except Exception:
                pass
    return out


def _md_rating_row(dim: str, rating: str, evidence: str) -> str:
    disp = (f"**{rating}**" if rating in {"suspect", "missing"}
            else f"_{rating}_" if rating == "good" else rating)
    ev = (evidence or "").replace("\n", " ").strip()
    if len(ev) > 320:
        ev = ev[:317] + "…"
    return f"| {dim} | {disp} | {ev} |"


def render_paper_markdown(pmid: str, ctx: dict) -> str:
    """Render one paper's metadata as a markdown document."""
    L: list[str] = []
    L.append(f"# {pmid} — {ctx.get('title') or 'Untitled'}")
    L.append("")
    if ctx.get("authors"):
        au = ctx["authors"]
        au_disp = ", ".join(au[:5]) + (f", … (+{len(au) - 5})" if len(au) > 5 else "")
        L.append(f"**Authors:** {au_disp}")
    j, y = ctx.get("journal") or "", ctx.get("year")
    if j or y:
        L.append(f"**Journal:** {j}{', ' if j and y else ''}{y or ''}")
    if ctx.get("doi"):
        L.append(f"**DOI:** [{ctx['doi']}](https://doi.org/{ctx['doi']})")
    L.append(f"**PubMed:** https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
    L.append("")

    if ctx.get("cluster_id") is not None:
        cdesc = ctx.get("cluster_description") or ""
        d = ctx.get("distance_to_centroid")
        dd = f", distance-to-centroid {d:.4f}" if d is not None else ""
        L.append(f"**Cluster:** c{ctx['cluster_id']} — {ctx.get('cluster_name') or '?'}{dd}")
        if cdesc:
            L.append(f"> {cdesc}")
        L.append("")

    src = []
    if ctx.get("source_db"): src.append(ctx["source_db"])
    if ctx.get("in_included"): src.append("included set")
    if ctx.get("n_text_chars"): src.append(f"{ctx['n_text_chars']:,} chars text extracted")
    if src:
        L.append(f"**Source:** " + " · ".join(src))
        L.append("")

    if ctx.get("exclusion_reason"):
        L.append(f"**⚠ Audit exclusion:** `{ctx['exclusion_reason']}`")
        if ctx.get("exclusion_details"):
            L.append(f"> {ctx['exclusion_details']}")
        L.append("")

    ratings = ctx.get("ratings", {})
    if ratings:
        pts = sorted({r["paper_type"] for r in ratings.values() if r.get("paper_type")})
        if pts:
            L.append(f"**Paper type:** `{', '.join(pts)}`")
            L.append("")
        L.append("## Methodological audit")
        L.append("")
        L.append("| Dimension | Rating | Evidence |")
        L.append("|---|---|---|")
        for dim in DIM_ORDER:
            if dim in ratings:
                r = ratings[dim]
                L.append(_md_rating_row(dim, r["rating"], r.get("evidence_quote", "")))
        L.append("")
        fns = [r.get("free_notes") or "" for r in ratings.values()]
        fns = [n for n in fns if n and n.strip()]
        fns = list(dict.fromkeys(fns))
        if fns:
            L.append("**Auditor notes:**")
            for n in fns:
                if len(n) > 400:
                    n = n[:397] + "…"
                L.append(f"- {n}")
            L.append("")

    fv1 = ctx.get("forensic_v1") or {}
    fv2 = ctx.get("forensic_v2") or {}
    if fv1 or fv2:
        L.append("## Forensic profile")
        L.append("")
        bullets = []
        if fv1.get("sc_n_pvalues"):
            n_dec = fv1.get("sc_n_decided", 0)
            n_dm = fv1.get("sc_n_decisive_mismatch", 0)
            caveat = " — note: ≥95% false-positive rate on medical papers" if n_dm else ""
            bullets.append(f"**p-values extracted:** {fv1['sc_n_pvalues']} ({n_dec} with adjacent test stat, {n_dm} decisive-mismatch flag{caveat})")
        if fv1.get("ef_n_effects"):
            wide = fv1.get("ef_n_wide_ci", 0)
            inc = fv1.get("ef_n_ci_inconsistent", 0)
            bullets.append(
                f"**Effect-size + CI rows:** {fv1['ef_n_effects']}"
                + (f", {wide} implausibly wide" if wide else "")
                + (f", {inc} CI inconsistent with point estimate" if inc else "")
            )
        if fv2.get("grim_n_triples"):
            bad = fv2.get("grim_n_grim_bad", 0)
            caveat = " — likely continuous-data extraction (GRIM-not-applicable, not fabrication)" if bad else ""
            bullets.append(f"**Mean+SD+n triples:** {fv2['grim_n_triples']} extracted{f', {bad} GRIM-flagged' if bad else ''}{caveat}")
        pos = fv1.get("pos_positivity_ratio")
        if pos is not None:
            ns = fv1.get("pos_n_significant_mentions", 0)
            nn = fv1.get("pos_n_not_significant_mentions", 0)
            bullets.append(f"**Result positivity:** {pos:.2f} ({ns} sig / {ns + nn} mentions)")
        if fv2.get("funding_classification"):
            ind = " (industry-linked)" if fv2.get("industry_linked") else ""
            bullets.append(f"**Funding/COI:** `{fv2['funding_classification']}`{ind}")
        for b in bullets:
            L.append(f"- {b}")
        L.append("")

    cs = ctx.get("cluster_stats")
    if cs:
        L.append("## Cluster context")
        L.append("")
        if cs.get("ca_n_total"):
            L.append(
                f"In `c{ctx['cluster_id']} {ctx.get('cluster_name', '')}` "
                f"({cs.get('n_papers', '?')} papers in corpus, {cs['ca_n_total']} audited valid): "
                f"{cs.get('ca_suspect_pct', 0):.0f}% rate `suspect` on construct_adequacy, "
                f"{cs.get('ca_n_good', 0)} in-corpus thesis voices."
            )
            L.append("")
        if ctx.get("is_thesis_voice"):
            L.append("**This paper is one of those in-corpus thesis voices** (rated `good` on construct_adequacy).")
            L.append("")
        if ctx.get("is_centroid"):
            L.append("**This paper is the cluster centroid** (closest to centroid in embedding space).")
            L.append("")

    sib = ctx.get("salami_siblings") or []
    if sib:
        L.append("## Cross-paper flags")
        L.append("")
        L.append("**Same-cohort author-overlap salami flag** with:")
        for s in sib:
            L.append(f"- {s['pmid']} (shared cohort_n={s['shared_cohort_n']}, {s['n_shared']} shared author surnames)")
        L.append("")

    L.append("## Provenance")
    L.append("")
    if ratings:
        sas = sorted({r["scored_at"] for r in ratings.values() if r.get("scored_at")})
        if sas:
            L.append(f"- **Audited:** {sas[0][:10]} (first rated) → {sas[-1][:10]} (last rated)")
        rvs = sorted({r["rubric_version"] for r in ratings.values() if r.get("rubric_version")})
        if rvs:
            L.append(f"- **Rubric versions:** {', '.join(rvs)}")
    if ctx.get("cluster_run_id"):
        L.append(f"- **Cluster run:** {ctx['cluster_run_id']}")
    L.append(f"- **Generated by:** `paperscope.systematic_review.methodological_audit.paper_metadata`")
    L.append("")
    return "\n".join(L)


def generate_metadata_corpus(
    *,
    db_path: str | Path,
    out_dir: str | Path,
    forensic_dir: str | Path | None = None,
    records_jsonl: str | Path | None = None,
    extra_records_jsonl: str | Path | None = None,
    cluster_run_id: str | None = None,
    progress: callable = None,
) -> int:
    """Generate metadata/<pmid>.md + .json for every audited paper in
    `db_path`. Returns count of papers processed."""
    db_path, out_dir = Path(db_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    forensic_dir = Path(forensic_dir) if forensic_dir else db_path.parent

    records: dict[str, dict] = {}
    if records_jsonl:
        records.update(_load_records_jsonl(Path(records_jsonl)))
    if extra_records_jsonl:
        records.update(_load_records_jsonl(Path(extra_records_jsonl)))

    fv1 = _load_per_paper(forensic_dir / "forensic-per-paper.jsonl")
    fv2 = _load_per_paper(forensic_dir / "forensic-v2-per-paper.jsonl")

    salami: dict[str, list] = defaultdict(list)
    s_path = forensic_dir / "forensic-v2-salami.jsonl"
    if s_path.exists():
        for line in s_path.open():
            try:
                r = json.loads(line)
                salami[r["pmid_a"]].append({"pmid": r["pmid_b"], "shared_cohort_n": r["shared_cohort_n"], "n_shared": r["n_shared"]})
                salami[r["pmid_b"]].append({"pmid": r["pmid_a"], "shared_cohort_n": r["shared_cohort_n"], "n_shared": r["n_shared"]})
            except Exception:
                pass

    con = sqlite3.connect(db_path)
    # Resolve cluster_run_id
    if cluster_run_id is None:
        row = con.execute("SELECT cluster_run_id FROM clusters GROUP BY cluster_run_id ORDER BY MAX(rowid) DESC LIMIT 1").fetchone()
        cluster_run_id = row[0] if row else None

    # Per-cluster stats once
    cluster_stats: dict[int, dict] = {}
    if cluster_run_id:
        for cid, name, desc, n_papers in con.execute(
            "SELECT cluster_id, cluster_name, cluster_description, n_papers FROM clusters WHERE cluster_run_id = ?",
            (cluster_run_id,),
        ):
            cas = {r[0]: r[1] for r in con.execute("""
                SELECT ar.rating, COUNT(DISTINCT ar.pmid) FROM audit_ratings ar
                JOIN cluster_assignments ca ON ca.pmid = ar.pmid AND ca.cluster_run_id = ?
                WHERE ca.cluster_id = ? AND ar.dimension = 'construct_adequacy'
                      AND ar.pmid NOT IN (SELECT pmid FROM audit_exclusions)
                GROUP BY ar.rating
            """, (cluster_run_id, cid))}
            n_valid = sum(cas.values())
            cluster_stats[cid] = {
                "cluster_id": cid, "cluster_name": name, "cluster_description": desc,
                "n_papers": n_papers, "ca_n_total": n_valid,
                "ca_n_good": cas.get("good", 0),
                "ca_suspect_pct": (100 * cas.get("suspect", 0) / n_valid) if n_valid else None,
            }

    audited = [r[0] for r in con.execute("SELECT DISTINCT pmid FROM audit_ratings ORDER BY pmid")]
    for i, pmid in enumerate(audited):
        if progress and i % 200 == 0:
            progress(i, len(audited))

        paper = con.execute(
            "SELECT title, year, journal, n_text_chars, in_included, source_db FROM papers WHERE pmid = ?",
            (pmid,),
        ).fetchone()
        title, year, journal, n_text_chars, in_included, source_db = paper or (None,) * 6
        ca = con.execute(
            "SELECT cluster_id, distance_to_centroid FROM cluster_assignments WHERE pmid = ? AND cluster_run_id = ?",
            (pmid, cluster_run_id),
        ).fetchone() if cluster_run_id else None
        cid, dist = (ca or (None, None))
        cs = cluster_stats.get(cid) if cid is not None else None
        is_centroid = False
        if cid is not None and cluster_run_id:
            cp = con.execute(
                "SELECT centroid_pmid FROM clusters WHERE cluster_run_id = ? AND cluster_id = ?",
                (cluster_run_id, cid),
            ).fetchone()
            is_centroid = bool(cp and cp[0] == pmid)

        rating_rows = con.execute(
            "SELECT dimension, rating, paper_type, evidence_quote, free_notes, scored_at, rubric_version, confidence "
            "FROM audit_ratings WHERE pmid = ?",
            (pmid,),
        ).fetchall()
        ratings = {}
        is_voice = False
        for dim, rating, ptype, ev, fn, sa, rv, conf in rating_rows:
            ratings[dim] = {"dimension": dim, "rating": rating, "paper_type": ptype,
                            "evidence_quote": ev, "free_notes": fn, "scored_at": sa,
                            "rubric_version": rv, "confidence": conf}
            if dim == "construct_adequacy" and rating == "good":
                is_voice = True

        ex = con.execute("SELECT reason, details FROM audit_exclusions WHERE pmid = ?", (pmid,)).fetchone()

        rec = records.get(pmid, {})
        authors = rec.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]

        ctx = {
            "pmid": pmid,
            "title": title or rec.get("title"),
            "year": year or rec.get("year"),
            "journal": journal or rec.get("journal"),
            "authors": authors,
            "doi": rec.get("doi", ""),
            "source_db": source_db,
            "n_text_chars": n_text_chars,
            "in_included": in_included,
            "cluster_id": cid, "cluster_name": cs["cluster_name"] if cs else None,
            "cluster_description": cs["cluster_description"] if cs else None,
            "distance_to_centroid": dist, "is_centroid": is_centroid,
            "is_thesis_voice": is_voice,
            "exclusion_reason": ex[0] if ex else None,
            "exclusion_details": ex[1] if ex else None,
            "ratings": ratings,
            "forensic_v1": fv1.get(pmid, {}),
            "forensic_v2": fv2.get(pmid, {}),
            "cluster_stats": cs,
            "salami_siblings": salami.get(pmid, []),
            "cluster_run_id": cluster_run_id,
        }
        (out_dir / f"{pmid}.md").write_text(render_paper_markdown(pmid, ctx))
        # Strip cluster_stats from JSON (it's redundant with cluster_id + own queries)
        ctx_json = {k: v for k, v in ctx.items() if k != "cluster_stats"}
        (out_dir / f"{pmid}.json").write_text(
            json.dumps(ctx_json, ensure_ascii=False, indent=2, default=str)
        )

    con.close()
    return len(audited)


def write_index(
    *,
    db_path: str | Path,
    metadata_dir: str | Path,
    cluster_run_id: str | None = None,
) -> Path:
    """Write metadata/README.md — a per-cluster browseable index of all
    audited papers with thesis-voice + exclusion flags."""
    db_path, metadata_dir = Path(db_path), Path(metadata_dir)
    con = sqlite3.connect(db_path)
    if cluster_run_id is None:
        row = con.execute("SELECT cluster_run_id FROM clusters GROUP BY cluster_run_id ORDER BY MAX(rowid) DESC LIMIT 1").fetchone()
        cluster_run_id = row[0] if row else None
    cluster_names = {r[0]: r[1] for r in con.execute(
        "SELECT cluster_id, cluster_name FROM clusters WHERE cluster_run_id = ?",
        (cluster_run_id,) if cluster_run_id else ("",),
    )} if cluster_run_id else {}
    by_cluster: dict = defaultdict(list)
    for pmid, in con.execute("SELECT DISTINCT pmid FROM audit_ratings ORDER BY pmid").fetchall():
        paper = con.execute("SELECT title, year FROM papers WHERE pmid = ?", (pmid,)).fetchone()
        title, year = paper or (None, None)
        ca = con.execute(
            "SELECT cluster_id FROM cluster_assignments WHERE pmid = ? AND cluster_run_id = ?",
            (pmid, cluster_run_id) if cluster_run_id else (pmid, ""),
        ).fetchone() if cluster_run_id else None
        cid = ca[0] if ca else None
        is_voice = bool(con.execute(
            "SELECT 1 FROM audit_ratings WHERE pmid = ? AND dimension = 'construct_adequacy' AND rating = 'good'",
            (pmid,),
        ).fetchone())
        excluded = bool(con.execute("SELECT 1 FROM audit_exclusions WHERE pmid = ?", (pmid,)).fetchone())
        by_cluster[cid].append({"pmid": pmid, "title": title or "???", "year": year,
                                 "is_voice": is_voice, "excluded": excluded})

    total = sum(len(v) for v in by_cluster.values())
    n_voices = sum(1 for ps in by_cluster.values() for p in ps if p["is_voice"])
    n_excluded = sum(1 for ps in by_cluster.values() for p in ps if p["excluded"])

    out = []
    out.append("# Per-paper metadata index")
    out.append("")
    out.append(f"**Total audited papers:** {total}")
    out.append(f"**Clusters:** {len(by_cluster)}")
    out.append(f"**In-corpus thesis voices** (rated `good` on construct_adequacy): {n_voices}")
    out.append(f"**Post-hoc excluded:** {n_excluded}")
    out.append("")
    out.append("Each paper has a markdown document and a JSON sidecar at `metadata/<pmid>.md` and `metadata/<pmid>.json`.")
    out.append("")
    out.append("## Browse by cluster")
    out.append("")
    for cid in sorted(by_cluster.keys(), key=lambda x: (x is None, x)):
        ps = sorted(by_cluster[cid], key=lambda p: -(p["year"] or 0))
        name = cluster_names.get(cid, f"(cluster {cid})") if cid is not None else "(unclustered)"
        n_v = sum(1 for p in ps if p["is_voice"])
        out.append(f"### c{cid} — {name}  ({len(ps)} audited, {n_v} in-corpus thesis voices)")
        out.append("")
        for p in ps[:50]:
            title = (p["title"][:90] + "…") if p["title"] and len(p["title"]) > 90 else p["title"]
            flags = "".join([" 🗣" if p["is_voice"] else "", " ⊘" if p["excluded"] else ""])
            out.append(f"- [{p['pmid']}](./{p['pmid']}.md) ({p['year'] or '?'}){flags}  {title}")
        if len(ps) > 50:
            out.append(f"- … (+{len(ps) - 50} more in this cluster)")
        out.append("")
    out.append("## Legend")
    out.append("")
    out.append("- 🗣 = in-corpus thesis voice (rated `good` on construct_adequacy — explicitly argues for high-dimensional / longitudinal / multi-modal measurement)")
    out.append("- ⊘ = post-hoc excluded (acquisition error / content-mismatch / boilerplate / non-English / duplicate)")
    out.append("")

    path = metadata_dir / "README.md"
    path.write_text("\n".join(out))
    con.close()
    return path
