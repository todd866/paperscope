"""Static HTML review site — Covidence-ish UX, fully static.

What v0 emits:

  index.html              — funnel summary, exclusion-reason breakdown,
                            per-tier and per-theme counts (the PRISMA-ScR
                            picture in one page)
  screening/<pmid>.html   — one page per screened record showing title,
                            abstract, journal/year, the AI's decision +
                            reason, and the rubric themes hit. Linked from
                            the index by decision category.

The pages are plain HTML + a small embedded CSS, no JS dependency. Decisions
are read-only here; live override needs the (not-yet-built) `ui.serve`
companion that POSTs back into the JSONL.

No external templating dep — paperscope's requirements stay lean.
"""

from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

from paperscope.systematic_review.records import load_jsonl

_CSS = """
body { font-family: -apple-system, system-ui, sans-serif; max-width: 880px;
       margin: 2em auto; padding: 0 1em; color: #222; line-height: 1.45; }
h1, h2 { font-weight: 600; }
.tag { display: inline-block; padding: .1em .5em; border-radius: 3px;
       font-size: .85em; margin-right: .3em; }
.tag.include { background: #e0f2e9; color: #135e3a; }
.tag.exclude { background: #fae3e3; color: #8a1a1a; }
.tag.maybe   { background: #fdf2c4; color: #6b5400; }
.tag.theme   { background: #e8edf6; color: #1f3a5f; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { text-align: left; padding: .4em .6em; border-bottom: 1px solid #eee; }
.abstract { white-space: pre-wrap; background: #fafafa; padding: .8em 1em;
            border-left: 3px solid #ddd; font-size: .95em; }
.reason { font-style: italic; color: #555; }
nav.crumb { color: #888; font-size: .9em; margin-bottom: 1em; }
nav.crumb a { color: #555; }
"""


def _decision_class(d: str) -> str:
    return {"include": "include", "exclude": "exclude", "maybe": "maybe"}.get(d, "")


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head>"
        f"<body>{body}</body></html>"
    )


def _render_index(stats: dict) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in stats["funnel"].items()
    )
    excl_rows = "".join(
        f"<tr><td>{html.escape(reason)}</td><td>{count}</td></tr>"
        for reason, count in stats["top_exclusion_reasons"]
    )
    decisions = "".join(
        f"<a href='screening/{html.escape(d)}.html' class='tag {_decision_class(d)}'>"
        f"{html.escape(d)} ({n})</a> "
        for d, n in stats["by_decision"].items()
    )
    body = (
        f"<h1>{html.escape(stats['name'])} — review state</h1>"
        f"<p>Generated from JSONL on {html.escape(stats['generated_at'])}.</p>"
        f"<h2>Funnel</h2><table>{rows}</table>"
        f"<h2>Decisions</h2><p>{decisions}</p>"
        f"<h2>Top exclusion reasons</h2><table>"
        f"<tr><th>Reason</th><th>Count</th></tr>{excl_rows}</table>"
    )
    return _page(f"{stats['name']} — review state", body)


def _render_decision_list(decision: str, items: list[tuple[dict, dict]]) -> str:
    rows = "".join(
        f"<tr><td><a href='record/{html.escape(r['pmid'])}.html'>{html.escape(r['pmid'])}</a></td>"
        f"<td>{html.escape((r.get('title') or '')[:120])}</td>"
        f"<td>{', '.join(html.escape(t) for t in (d.get('themes') or []))}</td></tr>"
        for r, d in items
    )
    body = (
        f"<nav class='crumb'><a href='../index.html'>&larr; index</a></nav>"
        f"<h1><span class='tag {_decision_class(decision)}'>{html.escape(decision)}</span> "
        f"({len(items)})</h1>"
        f"<table><tr><th>PMID</th><th>Title</th><th>Themes</th></tr>{rows}</table>"
    )
    return _page(f"{decision} ({len(items)})", body)


def _render_record(record: dict, decision: dict) -> str:
    d = decision.get("decision", "?")
    themes = decision.get("themes") or []
    themes_html = "".join(f"<span class='tag theme'>{html.escape(t)}</span>" for t in themes)
    body = (
        f"<nav class='crumb'><a href='../index.html'>&larr; index</a></nav>"
        f"<h1>{html.escape(record.get('title') or 'Untitled')}</h1>"
        f"<p>PMID {html.escape(record.get('pmid',''))} — "
        f"{html.escape(record.get('journal',''))} "
        f"({html.escape(record.get('year',''))})</p>"
        f"<p><span class='tag {_decision_class(d)}'>{html.escape(d)}</span> {themes_html}</p>"
        f"<p class='reason'>{html.escape(decision.get('reason') or '')}</p>"
        f"<div class='abstract'>{html.escape(record.get('abstract') or '')}</div>"
    )
    return _page(record.get("title") or "record", body)


def build_review_site(
    corpus_dir: str | Path,
    out_dir: str | Path,
    *,
    name: str = "Review",
) -> dict:
    """Read corpus_dir/{records,screening}.jsonl, write a static review site
    to out_dir. Returns the stats dict used to render the index."""
    from datetime import datetime, timezone

    corpus_dir = Path(corpus_dir)
    out_dir = Path(out_dir)
    (out_dir / "screening").mkdir(parents=True, exist_ok=True)
    (out_dir / "record").mkdir(parents=True, exist_ok=True)

    records = {r["pmid"]: r for r in load_jsonl(corpus_dir / "records.jsonl")}
    screening = load_jsonl(corpus_dir / "screening.jsonl")

    by_decision: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    grouped: dict[str, list[tuple[dict, dict]]] = {
        "include": [],
        "exclude": [],
        "maybe": [],
    }
    for d in screening:
        decision = d.get("decision", "")
        by_decision[decision] += 1
        if decision == "exclude":
            reasons[(d.get("reason") or "").strip().lower()] += 1
        r = records.get(d.get("pmid", ""), {"pmid": d.get("pmid", ""), "title": "(no record)"})
        if decision in grouped:
            grouped[decision].append((r, d))
            (out_dir / "record" / f"{r.get('pmid','')}.html").write_text(
                _render_record(r, d), encoding="utf-8"
            )

    stats = {
        "name": name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "funnel": {
            "Records identified": len(records),
            "Screening decisions": len(screening),
            "Included": by_decision["include"],
            "Maybe (full-text needed)": by_decision["maybe"],
            "Excluded": by_decision["exclude"],
        },
        "by_decision": dict(by_decision),
        "top_exclusion_reasons": reasons.most_common(20),
    }
    (out_dir / "index.html").write_text(_render_index(stats), encoding="utf-8")
    for decision, items in grouped.items():
        (out_dir / "screening" / f"{decision}.html").write_text(
            _render_decision_list(decision, items), encoding="utf-8"
        )
    return stats
