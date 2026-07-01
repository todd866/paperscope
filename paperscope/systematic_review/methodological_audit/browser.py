"""Static HTML browser for the audited corpus.

Renders a self-contained directory with:
  - index.html — searchable / filterable / sortable table of all papers
  - data/papers.json, clusters.json, summary.json — JSON data files
  - paper/<pmid>.html — per-paper detail page (server-side rendered)

The detail pages are SSR'd Python (all dynamic content escape()'d
server-side). The index page uses safe DOM APIs (textContent +
createElement) — no innerHTML on user-controlled content.

Open as file:// in any modern browser; if fetch() is blocked locally,
run `python3 -m http.server -d <out_parent>` and visit /browser/.

Usage:
    from paperscope.systematic_review.methodological_audit.browser import build_browser
    build_browser(
        db_path="audit.sqlite",
        metadata_dir="metadata/",
        out_dir="audit/browser/",
        diagnostic_clusters={0, 3, 4, 18, 19},  # subset for the headline % calc
    )
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path


def _compact_paper(meta: dict) -> dict:
    ratings = meta.get("ratings", {})
    g = lambda d: (ratings.get(d) or {}).get("rating")
    fv1 = meta.get("forensic_v1", {}) or {}
    fv2 = meta.get("forensic_v2", {}) or {}
    paper_types = sorted({r.get("paper_type") for r in ratings.values() if r.get("paper_type")})
    return {
        "pmid": meta["pmid"],
        "title": meta.get("title") or "",
        "year": meta.get("year"),
        "journal": meta.get("journal") or "",
        "authors": (meta.get("authors") or [])[:3],
        "cluster_id": meta.get("cluster_id"),
        "cluster_name": meta.get("cluster_name") or "",
        "is_thesis_voice": meta.get("is_thesis_voice", False),
        "is_centroid": meta.get("is_centroid", False),
        "excluded": bool(meta.get("exclusion_reason")),
        "exclusion_reason": meta.get("exclusion_reason"),
        "paper_type": paper_types[0] if paper_types else "",
        "construct_adequacy": g("construct_adequacy"),
        "construct_validity": g("construct_validity"),
        "statistical_hygiene": g("statistical_hygiene"),
        "transparency": g("transparency"),
        "novelty": g("novelty"),
        "reproducibility": g("reproducibility"),
        "n_pvalues": fv1.get("sc_n_pvalues", 0),
        "n_effects": fv1.get("ef_n_effects", 0),
        "n_wide_ci": fv1.get("ef_n_wide_ci", 0),
        "positivity": fv1.get("pos_positivity_ratio"),
        "funding": fv2.get("funding_classification", ""),
        "industry_linked": fv2.get("industry_linked", False),
        "source_db": meta.get("source_db", ""),
    }


def _build_data(metadata_dir: Path, out: Path, diagnostic_clusters: set[int]):
    pmids = [p.stem for p in sorted(metadata_dir.glob("*.json"))]
    papers = []
    for pmid in pmids:
        try:
            meta = json.loads((metadata_dir / f"{pmid}.json").read_text())
        except Exception:
            continue
        papers.append(_compact_paper(meta))

    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "data" / "papers.json").write_text(json.dumps(papers, separators=(",", ":")))

    by_cluster = defaultdict(list)
    for p in papers:
        by_cluster[p["cluster_id"]].append(p)
    cluster_rows = []
    for cid, ps in sorted(by_cluster.items(), key=lambda x: (x[0] is None, x[0])):
        cname = ps[0]["cluster_name"] if ps else ""
        ca_counts = defaultdict(int)
        for p in ps:
            if not p["excluded"] and p["construct_adequacy"]:
                ca_counts[p["construct_adequacy"]] += 1
        n_valid = sum(ca_counts.values())
        n_susp = ca_counts.get("suspect", 0)
        cluster_rows.append({
            "cluster_id": cid, "cluster_name": cname,
            "n_audited": len(ps), "n_valid": n_valid,
            "n_excluded": sum(1 for p in ps if p["excluded"]),
            "n_thesis_voices": sum(1 for p in ps if p["is_thesis_voice"] and not p["excluded"]),
            "construct_adequacy_breakdown": dict(ca_counts),
            "construct_adequacy_suspect_pct": (100 * n_susp / n_valid) if n_valid else None,
        })
    (out / "data" / "clusters.json").write_text(json.dumps(cluster_rows, separators=(",", ":")))

    diag_papers = [p for p in papers if p["cluster_id"] in diagnostic_clusters and not p["excluded"]]
    diag_susp = sum(1 for p in diag_papers if p["construct_adequacy"] == "suspect")
    diag_total = sum(1 for p in diag_papers if p["construct_adequacy"] and p["construct_adequacy"] != "n/a")
    summary = {
        "n_audited_total": len(papers),
        "n_valid": sum(1 for p in papers if not p["excluded"]),
        "n_excluded": sum(1 for p in papers if p["excluded"]),
        "n_thesis_voices_valid": sum(1 for p in papers if p["is_thesis_voice"] and not p["excluded"]),
        "n_industry_linked": sum(1 for p in papers if p["industry_linked"]),
        "diagnostic_cluster_n": diag_total,
        "diagnostic_cluster_suspect": diag_susp,
        "diagnostic_cluster_suspect_pct": (100 * diag_susp / diag_total) if diag_total else None,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    (out / "data" / "summary.json").write_text(json.dumps(summary, indent=2))
    return papers, cluster_rows, summary


# Index HTML (text-templated; JS uses textContent for all dynamic content)
_INDEX_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Audit corpus browser</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',sans-serif;margin:0;background:#fafafa;color:#222}
header{background:#1a1a2e;color:#fff;padding:1rem 2rem}h1{margin:0;font-size:1.2rem;font-weight:600}
header .stats{display:flex;gap:2rem;margin-top:.5rem;font-size:.85rem;opacity:.9}
.cluster-strip{padding:1rem 2rem;background:#f4f4f8;border-bottom:1px solid #ddd;display:flex;gap:.5rem;flex-wrap:wrap;font-size:.78rem}
.cluster-chip{background:#fff;border:1px solid #ccc;padding:.3rem .6rem;border-radius:12px;cursor:pointer}
.cluster-chip:hover{background:#1a1a2e;color:#fff}.cluster-chip.active{background:#1a1a2e;color:#fff}
.cluster-chip .susp{color:#c00;font-weight:600;margin-left:.3rem}.cluster-chip.active .susp{color:#ffc857}
.controls{padding:1rem 2rem;background:#fff;border-bottom:1px solid #ddd;display:flex;gap:1rem;flex-wrap:wrap;align-items:center}
.controls label{display:flex;align-items:center;gap:.3rem;font-size:.85rem}
.controls input,.controls select{padding:.3rem .5rem;font:inherit;border:1px solid #ccc;border-radius:3px}
.controls input[type=text]{width:300px}.result-count{margin-left:auto;font-size:.85rem;color:#666}
table{width:100%;border-collapse:collapse;background:#fff;font-size:.85rem}
th{background:#f4f4f8;padding:.5rem .7rem;text-align:left;border-bottom:2px solid #ddd;font-weight:600;cursor:pointer;position:sticky;top:0}
th.sorted-asc::after{content:" ▲"}th.sorted-desc::after{content:" ▼"}
td{padding:.5rem .7rem;border-bottom:1px solid #eee;vertical-align:top}tr:hover td{background:#f7f7fb}
.title{font-weight:500;max-width:400px}.meta{color:#777;font-size:.78rem}
a{color:#2a5d9f;text-decoration:none}a:hover{text-decoration:underline}
.rating{display:inline-block;padding:.1rem .4rem;border-radius:3px;font-size:.75rem;font-weight:500}
.rating.good{background:#d4edda;color:#155724}.rating.acceptable{background:#fff3cd;color:#856404}
.rating.suspect{background:#f8d7da;color:#721c24;font-weight:600}.rating.missing{background:#cce5ff;color:#004085}
.rating.na{background:#e9ecef;color:#6c757d}.rating.unclear{background:#e2e3e5}
.badge{font-size:.7rem;padding:.1rem .3rem;border-radius:3px;margin-right:.2rem;display:inline-block}
.badge.voice{background:#d4edda;color:#155724}.badge.centroid{background:#d1ecf1;color:#0c5460}
.badge.excluded{background:#f8d7da;color:#721c24}.badge.industry{background:#fce5cd;color:#7c4a03}
</style></head><body>
<header><h1>Audit corpus browser</h1><div class="stats" id="summary-stats"></div></header>
<div class="cluster-strip" id="cluster-strip"></div>
<div class="controls">
<label>Search: <input type="text" id="search" placeholder="title or PMID"></label>
<label>Construct adequacy: <select id="filter-ca"><option value="">all</option><option value="suspect">suspect</option><option value="acceptable">acceptable</option><option value="good">good</option><option value="n/a">n/a</option><option value="unclear">unclear</option></select></label>
<label>Paper type: <select id="filter-pt"><option value="">all</option></select></label>
<label>Funding: <select id="filter-fund"><option value="">all</option><option value="industry_linked">industry-linked</option><option value="public_disclosed">public, disclosed</option><option value="partial">partial</option><option value="none_stated">none stated</option></select></label>
<label><input type="checkbox" id="filter-voices"> Thesis voices only</label>
<label><input type="checkbox" id="filter-exclude"> Hide excluded</label>
<span class="result-count" id="count"></span>
</div>
<table id="papers"><thead><tr>
<th data-sort="pmid">PMID</th><th data-sort="title">Title</th><th data-sort="year">Year</th>
<th data-sort="cluster_id">Cluster</th><th data-sort="construct_adequacy">Construct adequacy</th>
<th data-sort="construct_validity">Construct validity</th><th data-sort="statistical_hygiene">Stat hygiene</th>
<th data-sort="novelty">Novelty</th><th data-sort="funding">Funding</th>
</tr></thead><tbody id="rows"></tbody></table>
<script>
let PAPERS=[],CLUSTERS=[],SUMMARY={};let sortKey='pmid',sortDir=1,activeCluster=null;
const el=(t,p={},c=[])=>{const n=document.createElement(t);for(const[k,v]of Object.entries(p)){if(k==='className')n.className=v;else if(k==='text')n.textContent=v==null?'':String(v);else if(k==='href')n.setAttribute('href',v);else if(k==='dataset')Object.assign(n.dataset,v);else if(k==='onclick')n.onclick=v;else n.setAttribute(k,v)}for(const x of c)if(x)n.appendChild(x);return n};
async function load(){PAPERS=await fetch('data/papers.json').then(r=>r.json());CLUSTERS=await fetch('data/clusters.json').then(r=>r.json());SUMMARY=await fetch('data/summary.json').then(r=>r.json());renderStats();renderClusters();populateFilters();render();attachEvents()}
function renderStats(){const s=document.getElementById('summary-stats');s.textContent='';const mk=(t)=>{const d=el('div');d.textContent=t;return d};s.appendChild(mk(SUMMARY.n_audited_total+' audited'));s.appendChild(mk(SUMMARY.n_valid+' valid (excl. '+SUMMARY.n_excluded+')'));if(SUMMARY.diagnostic_cluster_suspect_pct!=null)s.appendChild(mk('Diagnostic clusters: '+SUMMARY.diagnostic_cluster_suspect+'/'+SUMMARY.diagnostic_cluster_n+' suspect ('+SUMMARY.diagnostic_cluster_suspect_pct.toFixed(1)+'%)'));s.appendChild(mk(SUMMARY.n_thesis_voices_valid+' thesis voices'));s.appendChild(mk(SUMMARY.n_industry_linked+' industry-linked'))}
function renderClusters(){const strip=document.getElementById('cluster-strip');strip.textContent='';const all=el('div',{className:'cluster-chip'+(activeCluster==null?' active':''),dataset:{cid:''}});all.textContent='all clusters ('+PAPERS.length+')';all.onclick=()=>{activeCluster=null;rerenderClusters();render()};strip.appendChild(all);for(const c of CLUSTERS){if(c.cluster_id==null)continue;const chip=el('div',{className:'cluster-chip'+(activeCluster===c.cluster_id?' active':''),dataset:{cid:String(c.cluster_id)}});chip.textContent='c'+c.cluster_id+': '+c.cluster_name+' ('+c.n_valid+')';if(c.construct_adequacy_suspect_pct!=null){const sp=el('span',{className:'susp'});sp.textContent=c.construct_adequacy_suspect_pct.toFixed(0)+'%';chip.appendChild(sp)}chip.onclick=()=>{activeCluster=c.cluster_id;rerenderClusters();render()};strip.appendChild(chip)}}
function rerenderClusters(){document.querySelectorAll('.cluster-chip').forEach(el=>{const cid=el.dataset.cid===''?null:parseInt(el.dataset.cid);el.classList.toggle('active',cid===activeCluster)})}
function populateFilters(){const ptSel=document.getElementById('filter-pt');const types=[...new Set(PAPERS.map(p=>p.paper_type).filter(Boolean))].sort();for(const t of types){const o=el('option',{value:t});o.textContent=t;ptSel.appendChild(o)}}
function rNode(r){if(!r)return document.createTextNode('');const span=el('span',{className:'rating '+(r==='n/a'?'na':r)});span.textContent=r;return span}
function render(){const search=document.getElementById('search').value.toLowerCase();const caFilter=document.getElementById('filter-ca').value;const ptFilter=document.getElementById('filter-pt').value;const fundFilter=document.getElementById('filter-fund').value;const voicesOnly=document.getElementById('filter-voices').checked;const hideExcl=document.getElementById('filter-exclude').checked;let filtered=PAPERS.filter(p=>{if(activeCluster!==null&&p.cluster_id!==activeCluster)return false;if(search&&!(p.title.toLowerCase().includes(search)||p.pmid.includes(search)))return false;if(caFilter&&p.construct_adequacy!==caFilter)return false;if(ptFilter&&p.paper_type!==ptFilter)return false;if(fundFilter&&p.funding!==fundFilter)return false;if(voicesOnly&&!p.is_thesis_voice)return false;if(hideExcl&&p.excluded)return false;return true});filtered.sort((a,b)=>{let av=a[sortKey],bv=b[sortKey];if(av==null)av='';if(bv==null)bv='';if(av<bv)return -1*sortDir;if(av>bv)return 1*sortDir;return 0});document.getElementById('count').textContent=filtered.length+' of '+PAPERS.length+' papers';const tbody=document.getElementById('rows');tbody.textContent='';const limit=Math.min(filtered.length,500);for(let i=0;i<limit;i++){const p=filtered[i];const tr=el('tr');const link=el('a',{href:'paper/'+p.pmid+'.html'});link.textContent=p.pmid;tr.appendChild(el('td',{},[link]));const titleCell=el('td',{className:'title'});const tt=document.createElement('div');tt.textContent=p.title;titleCell.appendChild(tt);const m=document.createElement('div');m.className='meta';m.textContent=(p.authors||[]).join(', ')+(p.authors&&p.authors.length===3?', …':'')+(p.journal?' — '+p.journal:'');titleCell.appendChild(m);const badges=document.createElement('div');if(p.is_thesis_voice){const b=el('span',{className:'badge voice'});b.textContent='🗣 voice';badges.appendChild(b)}if(p.is_centroid){const b=el('span',{className:'badge centroid'});b.textContent='★ centroid';badges.appendChild(b)}if(p.excluded){const b=el('span',{className:'badge excluded'});b.textContent='⊘ '+(p.exclusion_reason||'excluded');badges.appendChild(b)}if(p.industry_linked){const b=el('span',{className:'badge industry'});b.textContent='$$ industry';badges.appendChild(b)}titleCell.appendChild(badges);tr.appendChild(titleCell);const yc=el('td');yc.textContent=p.year==null?'':String(p.year);tr.appendChild(yc);const cc=el('td');cc.textContent='c'+(p.cluster_id==null?'?':p.cluster_id);const cm=document.createElement('div');cm.className='meta';cm.textContent=p.cluster_name||'';cc.appendChild(cm);tr.appendChild(cc);for(const dim of['construct_adequacy','construct_validity','statistical_hygiene','novelty']){const td=el('td');td.appendChild(rNode(p[dim]));tr.appendChild(td)}const fc=el('td');const fm=document.createElement('span');fm.className='meta';fm.textContent=p.funding;fc.appendChild(fm);tr.appendChild(fc);tbody.appendChild(tr)}if(filtered.length>500){const tr=el('tr');const td=el('td');td.colSpan=9;td.style.textAlign='center';td.style.color='#888';td.style.padding='1rem';td.textContent='(showing first 500 of '+filtered.length+' — narrow with filters)';tr.appendChild(td);tbody.appendChild(tr)}document.querySelectorAll('th').forEach(th=>{th.classList.remove('sorted-asc','sorted-desc');if(th.dataset.sort===sortKey)th.classList.add(sortDir===1?'sorted-asc':'sorted-desc')})}
function attachEvents(){['search','filter-ca','filter-pt','filter-fund'].forEach(id=>{document.getElementById(id).oninput=render});['filter-voices','filter-exclude'].forEach(id=>{document.getElementById(id).onchange=render});document.querySelectorAll('th[data-sort]').forEach(th=>{th.onclick=()=>{const k=th.dataset.sort;if(sortKey===k)sortDir=-sortDir;else{sortKey=k;sortDir=1}render()}})}
load();
</script></body></html>"""


def _render_paper_html(meta: dict) -> str:
    pmid = meta["pmid"]
    title = meta.get("title") or "Untitled"
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             f'<title>{escape(title)}</title>',
             '<style>body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:0;background:#fafafa;color:#222;line-height:1.5}header{background:#1a1a2e;color:#fff;padding:1rem 2rem}header a{color:#ffc857}.container{max-width:900px;margin:0 auto;padding:2rem;background:#fff}h1{font-size:1.4rem;margin:0 0 .3rem}.meta{color:#666;font-size:.9rem;margin-bottom:1rem}.meta a{color:#2a5d9f}.badge{font-size:.78rem;padding:.15rem .4rem;border-radius:3px;margin-right:.3rem;display:inline-block}.voice{background:#d4edda;color:#155724}.centroid{background:#d1ecf1;color:#0c5460}.excluded{background:#f8d7da;color:#721c24}.industry{background:#fce5cd;color:#7c4a03}table{width:100%;border-collapse:collapse;margin:1rem 0}th,td{padding:.5rem;border-bottom:1px solid #eee;text-align:left;font-size:.9rem;vertical-align:top}th{background:#f4f4f8;font-weight:600}.rating{display:inline-block;padding:.15rem .5rem;border-radius:3px;font-weight:500;font-size:.85rem}.rating.good{background:#d4edda;color:#155724}.rating.acceptable{background:#fff3cd;color:#856404}.rating.suspect{background:#f8d7da;color:#721c24;font-weight:600}.rating.missing{background:#cce5ff;color:#004085}.rating.na{background:#e9ecef;color:#6c757d}.rating.unclear{background:#e2e3e5}.evidence{color:#444;font-size:.85rem;max-width:600px}.section{margin-top:2rem}.section h2{font-size:1.1rem;border-bottom:2px solid #1a1a2e;padding-bottom:.3rem}blockquote{border-left:3px solid #1a1a2e;margin-left:0;padding-left:1rem;color:#444;font-size:.9rem;font-style:italic}ul{font-size:.9rem}</style>',
             '</head><body><header><a href="../index.html">← all papers</a></header>',
             '<div class="container">',
             f'<h1>{escape(title)}</h1>']
    meta_bits = [f"PMID {escape(pmid)}"]
    if meta.get("year"): meta_bits.append(escape(str(meta["year"])))
    if meta.get("journal"): meta_bits.append(escape(meta["journal"]))
    if meta.get("doi"):
        meta_bits.append(f'<a href="https://doi.org/{escape(meta["doi"])}">{escape(meta["doi"])}</a>')
    if pmid.isdigit():
        meta_bits.append(f'<a href="https://pubmed.ncbi.nlm.nih.gov/{escape(pmid)}/">PubMed</a>')
    parts.append(f'<div class="meta">{" · ".join(meta_bits)}</div>')
    badges = []
    if meta.get("is_thesis_voice"): badges.append('<span class="badge voice">🗣 in-corpus thesis voice</span>')
    if meta.get("is_centroid"): badges.append('<span class="badge centroid">★ cluster centroid</span>')
    if meta.get("exclusion_reason"): badges.append(f'<span class="badge excluded">⊘ {escape(meta["exclusion_reason"])}</span>')
    if (meta.get("forensic_v2") or {}).get("industry_linked"): badges.append('<span class="badge industry">$$ industry-linked</span>')
    if badges: parts.append(f'<div style="margin-bottom:1rem">{"".join(badges)}</div>')
    authors = meta.get("authors") or []
    if authors:
        au = ", ".join(escape(a) for a in authors[:8]) + (f", … (+{len(authors)-8})" if len(authors)>8 else "")
        parts.append(f'<div class="meta"><b>Authors:</b> {au}</div>')
    cid = meta.get("cluster_id")
    if cid is not None:
        parts.append(f'<div class="meta"><b>Cluster:</b> c{cid} — {escape(meta.get("cluster_name") or "")}')
        if meta.get("cluster_description"): parts.append(f'<br>{escape(meta["cluster_description"])}')
        parts.append('</div>')
    if meta.get("abstract"):
        ab = escape(meta["abstract"].strip().replace("\n"," ")[:1200])
        parts.append(f'<div class="section"><h2>Abstract</h2><blockquote>{ab}</blockquote></div>')
    ratings = meta.get("ratings", {})
    if ratings:
        parts.append('<div class="section"><h2>Methodological audit</h2><table><tr><th>Dimension</th><th>Rating</th><th>Evidence</th></tr>')
        DIM = ["statistical_hygiene","transparency","construct_validity","reproducibility","novelty","construct_adequacy","screening_fit","transparency_basic_disclosure","transparency_review_process"]
        for dim in DIM:
            r = ratings.get(dim)
            if not r: continue
            cls = "na" if r["rating"]=="n/a" else r["rating"]
            ev = escape((r.get("evidence_quote") or "").strip()[:500])
            parts.append(f'<tr><td>{escape(dim)}</td><td><span class="rating {escape(cls)}">{escape(r["rating"])}</span></td><td class="evidence">{ev}</td></tr>')
        parts.append('</table>')
        fns = [r.get("free_notes") or "" for r in ratings.values()]
        fns = list(dict.fromkeys([n for n in fns if n and n.strip()]))
        if fns:
            parts.append('<p><b>Auditor notes:</b></p><ul>')
            for n in fns: parts.append(f'<li>{escape(n[:400])}</li>')
            parts.append('</ul>')
        parts.append('</div>')
    fv1 = meta.get("forensic_v1") or {}
    fv2 = meta.get("forensic_v2") or {}
    if fv1 or fv2:
        parts.append('<div class="section"><h2>Forensic profile</h2><ul>')
        if fv1.get("sc_n_pvalues"):
            n_dm = fv1.get("sc_n_decisive_mismatch", 0)
            caveat = ' <span class="meta">(≥95% false-positive rate on medical papers)</span>' if n_dm else ""
            parts.append(f'<li><b>p-values:</b> {fv1["sc_n_pvalues"]} ({fv1.get("sc_n_decided",0)} with adjacent test stat; {n_dm} flag{caveat})</li>')
        if fv1.get("ef_n_effects"):
            x = []
            if fv1.get("ef_n_wide_ci"): x.append(f'{fv1["ef_n_wide_ci"]} implausibly wide')
            if fv1.get("ef_n_ci_inconsistent"): x.append(f'{fv1["ef_n_ci_inconsistent"]} CI inconsistent')
            xs = f' — {", ".join(x)}' if x else ""
            parts.append(f'<li><b>Effect-size + CI rows:</b> {fv1["ef_n_effects"]}{xs}</li>')
        if fv2.get("grim_n_triples"):
            bad = fv2.get("grim_n_grim_bad", 0)
            cv = " — continuous-data extraction, GRIM-not-applicable" if bad else ""
            parts.append(f'<li><b>Mean+SD+n triples:</b> {fv2["grim_n_triples"]}{f", {bad} flagged" if bad else ""}{cv}</li>')
        pos = fv1.get("pos_positivity_ratio")
        if pos is not None:
            ns, nn = fv1.get("pos_n_significant_mentions",0), fv1.get("pos_n_not_significant_mentions",0)
            parts.append(f'<li><b>Result positivity:</b> {pos:.2f} ({ns}/{ns+nn} mentions)</li>')
        if fv2.get("funding_classification"):
            ind = " (industry-linked)" if fv2.get("industry_linked") else ""
            parts.append(f'<li><b>Funding/COI:</b> {escape(fv2["funding_classification"])}{ind}</li>')
        parts.append('</ul></div>')
    parts.append('<div class="section"><h2>Provenance</h2><ul>')
    if ratings:
        sas = sorted({(r.get("scored_at") or "")[:10] for r in ratings.values() if r.get("scored_at")})
        if sas: parts.append(f'<li><b>Audited:</b> {escape(sas[0])} → {escape(sas[-1])}</li>')
        rvs = sorted({r.get("rubric_version") or "" for r in ratings.values() if r.get("rubric_version")})
        if rvs: parts.append(f'<li><b>Rubric versions:</b> {", ".join(escape(v) for v in rvs)}</li>')
    if meta.get("cluster_run_id"): parts.append(f'<li><b>Cluster run:</b> {escape(meta["cluster_run_id"])}</li>')
    parts.append('</ul></div></div></body></html>')
    return "\n".join(parts)


def build_browser(
    *,
    metadata_dir: str | Path,
    out_dir: str | Path,
    diagnostic_clusters: set[int] | None = None,
    progress: callable = None,
) -> dict:
    """Build the static HTML browser. Returns the summary dict."""
    metadata_dir, out_dir = Path(metadata_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    diag = diagnostic_clusters or set()
    papers, _, summary = _build_data(metadata_dir, out_dir, diag)
    (out_dir / "index.html").write_text(_INDEX_HTML)
    paper_dir = out_dir / "paper"
    paper_dir.mkdir(parents=True, exist_ok=True)
    pmids = [p["pmid"] for p in papers]
    for i, pmid in enumerate(pmids):
        if progress and i % 500 == 0:
            progress(i, len(pmids))
        try:
            meta = json.loads((metadata_dir / f"{pmid}.json").read_text())
        except Exception:
            continue
        (paper_dir / f"{pmid}.html").write_text(_render_paper_html(meta))
    return summary
