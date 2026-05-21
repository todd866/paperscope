"""Render a self-contained, scroll-through validation workbook (one HTML file).

Flattens, per decision: the AI decision, the model's self-audit (confidence +
reasoning), the local source context (title + abstract), and a rater for each
friction dimension, so a human can adjudicate by scrolling. Self-flagged
low-confidence decisions sort to the top. Checkboxes/ratings/notes persist in
the browser; a button exports JSON that `reconcile` consumes.

Deterministic and offline: the builder only uses records you pass in (local
corpus first). It never fetches or embeds paywalled full text. An optional
`fetch_oa_abstracts` helper can backfill *open-access* abstracts from Europe PMC
when a corpus lacks them, and is only called by the CLI when asked.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from paperscope.systematic_review.records import record_id
from paperscope.systematic_review.validate.rubric import FrictionRubric

esc = html.escape


def _decision_html(decision: dict) -> str:
    """Render a decision dict generically, skipping identity/source fields."""
    skip = {"record_id", "pmid", "id", "title", "abstract"}
    rows = [f"<b>{esc(k)}</b>: {esc(str(v))}" for k, v in decision.items() if k not in skip]
    return "<br>".join(rows) or "<i>(no decision fields)</i>"


def _audit_html(a: dict | None) -> str:
    if not a:
        return ""
    conf = a.get("confidence")
    conf_s = f"{conf:.0%}" if isinstance(conf, (int, float)) else esc(str(conf))
    flag = " <b>[FLAGGED]</b>" if a.get("flag") else ""
    dim = f" · dimension: {esc(str(a['dimension']))}" if a.get("dimension") else ""
    return (f'<div class="audit">AI self-audit: confidence {conf_s}{flag}{dim}'
            f'<br>{esc(a.get("reasoning",""))}</div>')


def _raters_html(rid: str, rubric: FrictionRubric) -> str:
    parts = []
    for dim in rubric.dimensions:
        opts = "".join(
            f'<label><input type="radio" name="r-{esc(rid)}-{esc(dim.id)}" value="{esc(v)}"> {esc(v)}</label>'
            for v in dim.scale
        )
        q = f' <span class="q">{esc(dim.question)}</span>' if dim.question else ""
        parts.append(f'<div class="dim" data-dim="{esc(dim.id)}"><span class="dlab">{esc(dim.label)}</span>{q} {opts}</div>')
    return "".join(parts)


_CSS = """
:root{--g:#2a7f4f;--r:#b3322c;--a:#b07d00;}
*{box-sizing:border-box}
body{font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#1a1a1a;margin:0;background:#fafafa}
.wrap{max-width:880px;margin:0 auto;padding:0 18px 120px}
header{position:sticky;top:0;z-index:10;background:#fff;border-bottom:1px solid #ddd;padding:12px 18px;box-shadow:0 1px 4px rgba(0,0,0,.06)}
header .bar{max-width:880px;margin:0 auto;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
header h1{font-size:15px;margin:0;flex:1 1 auto}
.prog{font-size:13px;color:#555} .prog b{color:#111}
button{font:13px inherit;padding:6px 12px;border:1px solid #888;border-radius:6px;background:#fff;cursor:pointer}
button:hover{background:#f0f0f0}
.card{background:#fff;border:1px solid #e2e2e2;border-left:4px solid #e2e2e2;border-radius:8px;padding:14px 16px;margin:14px 0}
.card.flaggedAI{border-left-color:var(--a)}
.card.done{border-left-color:var(--g);background:#f6fbf8}
.card.flipped{border-left-color:var(--r);background:#fdf6f5}
.hd{display:flex;gap:16px;align-items:center;font-size:13px;color:#444;margin-bottom:6px}
.hd label{cursor:pointer;user-select:none} .hd .rid{margin-left:auto;color:#aaa;font-size:11px}
.ti{font-weight:600;font-size:15px} .mt{font-size:12.5px;color:#777;margin:2px 0 8px}
.decision{background:#f3f5f8;border:1px solid #dde3ea;border-radius:6px;padding:8px 10px;font-size:13.5px;margin-bottom:8px}
.audit{background:#fff7e0;border:1px solid #f0e0a8;border-radius:6px;padding:8px 10px;font-size:13px;margin-bottom:8px}
.dim{font-size:13px;margin:4px 0} .dim .dlab{font-weight:600} .dim .q{color:#777;font-size:12px} .dim label{margin:0 8px;cursor:pointer}
details{font-size:14px} summary{cursor:pointer;color:#666;font-size:12.5px}
.abs{margin-top:6px;color:#222}
.note{width:100%;margin-top:10px;padding:6px 8px;border:1px solid #ccc;border-radius:6px;font:13px inherit}
#out{width:100%;height:180px;margin-top:10px;font:12px ui-monospace,Menlo,monospace;display:none}
"""

_JS = """
const cards=[...document.querySelectorAll('.card')];
const KEY='psvalidate:'+document.body.dataset.wbid+':';
function refresh(){
  let rev=0,flip=0;
  cards.forEach(c=>{
    const r=c.querySelector('.cb-rev').checked, f=c.querySelector('.cb-flip').checked;
    c.classList.toggle('done',r&&!f); c.classList.toggle('flipped',f);
    if(r)rev++; if(f)flip++;
  });
  document.getElementById('nrev').textContent=rev;
  document.getElementById('nflip').textContent=flip;
}
function state(c){
  const ratings={};
  c.querySelectorAll('.dim').forEach(d=>{
    const sel=d.querySelector('input:checked'); if(sel) ratings[d.dataset.dim]=sel.value;
  });
  return {reviewed:c.querySelector('.cb-rev').checked, flip:c.querySelector('.cb-flip').checked,
          ratings, note:c.querySelector('.note').value.trim()};
}
function save(c){ localStorage.setItem(KEY+c.dataset.rid, JSON.stringify(state(c))); refresh(); }
cards.forEach(c=>{
  const raw=localStorage.getItem(KEY+c.dataset.rid);
  if(raw){ try{ const s=JSON.parse(raw);
    c.querySelector('.cb-rev').checked=!!s.reviewed; c.querySelector('.cb-flip').checked=!!s.flip;
    c.querySelector('.note').value=s.note||'';
    Object.entries(s.ratings||{}).forEach(([dim,val])=>{
      const el=c.querySelector('.dim[data-dim="'+dim+'"] input[value="'+val+'"]'); if(el) el.checked=true; });
  }catch(e){} }
  c.addEventListener('change',()=>save(c));
  c.querySelector('.note').addEventListener('input',()=>save(c));
});
function exportState(){
  const out={};
  cards.forEach(c=>{ const s=state(c); if(s.reviewed||s.flip||s.note||Object.keys(s.ratings).length) out[c.dataset.rid]=s; });
  const txt=JSON.stringify(out,null,1);
  const ta=document.getElementById('out'); ta.style.display='block'; ta.value=txt;
  navigator.clipboard&&navigator.clipboard.writeText(txt); ta.select();
}
refresh();
"""


def build_workbook(decisions: list[dict], records_by_id: dict[str, dict], rubric: FrictionRubric,
                   self_audit: dict[str, dict] | None = None, *, title: str = "Validation workbook",
                   wb_id: str = "wb") -> str:
    """Return the workbook HTML. `self_audit` maps record_id -> audit dict."""
    self_audit = self_audit or {}

    def sort_key(d):
        a = self_audit.get(record_id(d), {})
        # flagged first, then by ascending confidence (least sure first)
        conf = a.get("confidence", 1.0)
        conf = conf if isinstance(conf, (int, float)) else 1.0
        return (0 if a.get("flag") else 1, conf)

    cards = []
    for d in sorted(decisions, key=sort_key):
        rid = record_id(d)
        rec = records_by_id.get(rid, {})
        a = self_audit.get(rid)
        title_txt = esc(rec.get("title") or d.get("title") or rid)
        abstract = esc(rec.get("abstract") or "(no local abstract; pass --include-fulltext to backfill open-access abstracts)")
        flagged_cls = " flaggedAI" if (a and a.get("flag")) else ""
        cards.append(
            f'<div class="card{flagged_cls}" data-rid="{esc(rid)}">'
            f'<div class="hd"><label><input type="checkbox" class="cb-rev"> reviewed</label>'
            f'<label><input type="checkbox" class="cb-flip"> flip / disagree</label>'
            f'<span class="rid">{esc(rid)}</span></div>'
            f'<div class="ti">{title_txt}</div>'
            f'<div class="decision">{_decision_html(d)}</div>'
            f'{_audit_html(a)}'
            f'{_raters_html(rid, rubric)}'
            f'<details><summary>source abstract</summary><div class="abs">{abstract}</div></details>'
            f'<input class="note" placeholder="note (only if flipping / correcting)">'
            f'</div>'
        )

    n = len(cards)
    nflag = sum(1 for d in decisions if self_audit.get(record_id(d), {}).get("flag"))
    doc = _TEMPLATE
    doc = doc.replace("%%TITLE%%", esc(title))
    doc = doc.replace("%%WBID%%", esc(wb_id))
    doc = doc.replace("%%N%%", str(n))
    doc = doc.replace("%%NFLAG%%", str(nflag))
    doc = doc.replace("%%CSS%%", _CSS)
    doc = doc.replace("%%JS%%", _JS)
    doc = doc.replace("%%CARDS%%", "".join(cards))
    return doc


_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%%TITLE%%</title>
<style>%%CSS%%</style></head><body data-wbid="%%WBID%%">
<header><div class="bar">
  <h1>%%TITLE%%</h1>
  <span class="prog">reviewed <b id="nrev">0</b>/%%N%% &middot; flipped <b id="nflip">0</b> &middot; AI-flagged %%NFLAG%%</span>
  <button onclick="exportState()">Copy review (JSON)</button>
</div></header>
<div class="wrap">
<p style="color:#555;font-size:14px;margin:18px 0">AI-flagged low-confidence decisions are at the top. Rate the friction dimensions, tick <b>reviewed</b> when you agree, <b>flip / disagree</b> + a note when you would change the decision. State saves in your browser. When done, hit <b>Copy review (JSON)</b> and paste it back for <code>validate reconcile</code>.</p>
<textarea id="out" readonly></textarea>
%%CARDS%%
</div>
<script>%%JS%%</script></body></html>"""


def fetch_oa_abstracts(record_ids: list[str], *, timeout: int = 30) -> dict[str, str]:
    """Optional, OA-only backfill: fetch abstracts from Europe PMC for records
    that look like PMIDs. Used by the CLI only when --include-fulltext is set.
    Never fetches paywalled full text. Returns {record_id: abstract}."""
    import urllib.request
    import xml.etree.ElementTree as ET

    out: dict[str, str] = {}
    pmids = [r for r in record_ids if str(r).isdigit()]
    if not pmids:
        return out
    url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
           f"?db=pubmed&retmode=xml&id={','.join(pmids)}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "paperscope-validate/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            root = ET.fromstring(r.read().decode())
    except Exception:
        return out
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//PMID")
        parts = [" ".join(at.itertext()).strip() for at in art.findall(".//Abstract/AbstractText")]
        if pmid and parts:
            out[pmid] = " ".join(parts)
    return out
