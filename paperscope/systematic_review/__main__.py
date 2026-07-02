"""CLI entry: `python -m paperscope.systematic_review <subcommand> [args]`.

Lightweight dispatcher — each subcommand is one well-scoped operation against
a ReviewConfig + a corpus directory. Heavy LLM-orchestrated steps (screen,
extract) live outside this CLI since their implementation depends on which
agent SDK the caller wires in.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from paperscope.systematic_review import ReviewConfig, load_jsonl
from paperscope.systematic_review.synthesise import aggregate, prisma_flow
from paperscope.systematic_review.ui import build_review_site


def _cmd_aggregate(args: argparse.Namespace) -> int:
    cfg = ReviewConfig.from_yaml(args.config)
    corpus = Path(args.corpus or cfg.corpus_dir)
    rows = load_jsonl(corpus / "extraction.jsonl")
    out = aggregate(rows, cfg.aggregation)
    out_path = Path(args.out) if args.out else corpus / "synthesis-tables.json"
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {out_path} ({out['corpus_n']} rows aggregated)")
    return 0


def _cmd_prisma(args: argparse.Namespace) -> int:
    cfg = ReviewConfig.from_yaml(args.config) if args.config else None
    corpus = Path(args.corpus or (cfg.corpus_dir if cfg else "."))
    records = load_jsonl(corpus / "records.jsonl")
    screening = load_jsonl(corpus / "screening.jsonl") if (corpus / "screening.jsonl").exists() else None
    full_text = (
        load_jsonl(corpus / "full-text-screening.jsonl")
        if (corpus / "full-text-screening.jsonl").exists()
        else None
    )
    flow = prisma_flow(records=records, screening=screening, full_text_screening=full_text)
    out_path = Path(args.out) if args.out else corpus / "prisma-flow.json"
    out_path.write_text(json.dumps(flow, indent=1, ensure_ascii=False))
    print(json.dumps(flow, indent=2))
    print(f"wrote {out_path}")
    return 0


def _cmd_build_site(args: argparse.Namespace) -> int:
    cfg = ReviewConfig.from_yaml(args.config) if args.config else None
    corpus = Path(args.corpus or (cfg.corpus_dir if cfg else "."))
    out = Path(args.out)
    name = args.name or (cfg.name if cfg else "Review")
    stats = build_review_site(corpus, out, name=name)
    print(f"wrote {out} — funnel: {stats['funnel']}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    from paperscope.systematic_review.search.medline import block_counts, harvest, compose_query

    cfg = ReviewConfig.from_yaml(args.config)
    if args.show_query:
        print(compose_query(cfg.search))
        return 0
    if args.block_counts:
        for name, n in block_counts(cfg.search).items():
            print(f"  {name:18s}: {n:>7,}")
        return 0
    corpus = Path(args.corpus or cfg.corpus_dir)
    n = harvest(cfg.search, corpus / "records.jsonl")
    print(f"harvested {n:,} records into {corpus / 'records.jsonl'}")
    return 0


def _cmd_acquire(args: argparse.Namespace) -> int:
    """Pull PDFs for the review's included set: OA via Unpaywall, plus an
    EZProxy queue for the paywalled tail. The paywalled queue is JSON for any
    browser-automation tool (or human hand) to walk — paperscope deliberately
    stops at queue generation rather than embedding its own browser driver."""
    from paperscope.systematic_review.acquire import acquire

    cfg = ReviewConfig.from_yaml(args.config)
    corpus = Path(args.corpus or cfg.corpus_dir)
    records_path = Path(args.records) if args.records else None

    report = acquire(
        review_name=cfg.name,
        corpus_dir=corpus,
        records_path=records_path,
        ezproxy_host=args.ezproxy_host,
        fetch_oa=not args.no_oa,
        extract_text_pdfs=not args.no_extract,
        upload_b2=args.upload_b2,
        oa_limit=args.limit,
        verbose=True,
    )
    # `acquire` prints its own pretty report.
    return 0


def _cmd_browser_harvest(args: argparse.Namespace) -> int:
    """Playwright-driven harvest of the paywalled tail.

    Walks the included.jsonl (or a custom queue), navigates each paper's
    EZProxy URL, dispatches to the matching publisher adapter, and saves
    PDFs to `<corpus>/papers/<pmid>.pdf`. Outcomes append to
    harvest-log.jsonl; a strategy cache learns from each run.
    """
    import asyncio
    import json as _json
    from paperscope.systematic_review.acquire.browser_driver import harvest_records

    corpus = Path(args.corpus) if args.corpus else None
    if args.config and not corpus:
        cfg = ReviewConfig.from_yaml(args.config)
        corpus = Path(cfg.corpus_dir)
    if corpus is None:
        print("error: --corpus or --config must be provided")
        return 2

    # Records source: explicit path, sample-100.json, or included.jsonl.
    if args.records:
        path = Path(args.records)
        if path.suffix == ".json":
            records = _json.loads(path.read_text())
        else:
            records = [_json.loads(l) for l in path.open()]
    else:
        for cand in (corpus / "included.jsonl", corpus / "records.jsonl"):
            if cand.exists():
                records = [_json.loads(l) for l in cand.open()]
                break
        else:
            print(f"error: no records source found under {corpus}; pass --records")
            return 2

    if args.limit:
        records = records[: args.limit]

    asyncio.run(
        harvest_records(
            records,
            corpus_dir=corpus,
            ezproxy_host=args.ezproxy_host,
            concurrency=args.concurrency,
            headless=args.headless,
            skip_already_have=not args.no_skip_existing,
            warmup_doi=args.warmup_doi,
            user_data_dir=args.user_data_dir,
            profile_directory=args.profile_directory,
            inter_paper_delay_s=args.inter_paper_delay,
            group_by_publisher=args.group_by_publisher,
            verbose=True,
        )
    )
    return 0


def _cmd_validate_workbook(args: argparse.Namespace) -> int:
    """Decisions + (optional) self-audit + rubric + local records -> one HTML
    workbook. Source context comes from the local corpus first; --include-fulltext
    backfills *open-access* abstracts only (never paywalled full text)."""
    from paperscope.systematic_review.records import record_id
    from paperscope.systematic_review.validate.workbook import build_workbook, fetch_oa_abstracts
    from paperscope.systematic_review.validate.rubric import load_friction_rubric

    decisions = load_jsonl(args.decisions)
    self_audit: dict[str, dict] = {}
    if args.self_audit:
        for a in load_jsonl(args.self_audit):
            self_audit[str(a.get("record_id") or a.get("pmid") or a.get("id", ""))] = a
    rubric = load_friction_rubric(args.rubric)
    corpus = Path(args.corpus) if args.corpus else Path(".")
    records_path = Path(args.records) if args.records else (corpus / "records.jsonl")
    recs = load_jsonl(records_path) if records_path.exists() else []
    rbi = {record_id(r): r for r in recs}
    if args.include_fulltext:
        need = [rid for rid in {record_id(d) for d in decisions} if not (rbi.get(rid) or {}).get("abstract")]
        for rid, ab in fetch_oa_abstracts(need).items():
            rbi.setdefault(rid, {})["abstract"] = ab
    html = build_workbook(decisions, rbi, rubric, self_audit,
                          title=args.title or "Validation workbook", wb_id=args.wb_id or "wb")
    Path(args.out).write_text(html)
    nflag = sum(1 for d in decisions if self_audit.get(record_id(d), {}).get("flag"))
    print(f"wrote {args.out} ({len(decisions)} decisions, {nflag} AI-flagged)")
    return 0


def _cmd_validate_reconcile(args: argparse.Namespace) -> int:
    """Human export -> append-only validation-overrides + requeue. Never
    mutates the source decisions."""
    from paperscope.systematic_review.records import dump_jsonl
    from paperscope.systematic_review.validate.reconcile import reconcile

    decisions = load_jsonl(args.decisions)
    human = json.loads(Path(args.human_export).read_text())
    overrides, requeue = reconcile(decisions, human)
    dump_jsonl(overrides, args.out)
    dump_jsonl(requeue, args.requeue)
    print(f"wrote {args.out} ({len(overrides)} overrides) and {args.requeue} ({len(requeue)} re-queued)")
    return 0


def _cmd_validate_summary(args: argparse.Namespace) -> int:
    """validation-overrides -> calibration summary (agreement rate, per-dimension)."""
    from paperscope.systematic_review.validate.reconcile import summarize

    summary = summarize(load_jsonl(args.validation))
    Path(args.out).write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=2))
    print(f"wrote {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="paperscope.systematic_review")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("aggregate", help="charted JSONL → synthesis tables")
    s.add_argument("config", help="path to review config YAML")
    s.add_argument("--corpus", help="corpus dir (default: config.corpus_dir)")
    s.add_argument("--out", help="output JSON path (default: <corpus>/synthesis-tables.json)")
    s.set_defaults(fn=_cmd_aggregate)

    s = sub.add_parser("prisma", help="records + screening → PRISMA-ScR flow")
    s.add_argument("--config", help="path to review config YAML (optional)")
    s.add_argument("--corpus", help="corpus dir")
    s.add_argument("--out", help="output JSON path")
    s.set_defaults(fn=_cmd_prisma)

    s = sub.add_parser("build-site", help="static HTML review site from JSONL")
    s.add_argument("--config", help="path to review config YAML (optional)")
    s.add_argument("--corpus", help="corpus dir")
    s.add_argument("--out", required=True, help="output directory")
    s.add_argument("--name", help="review name (for the page title)")
    s.set_defaults(fn=_cmd_build_site)

    s = sub.add_parser("search", help="MEDLINE harvest / query helpers")
    s.add_argument("config", help="path to review config YAML")
    s.add_argument("--corpus", help="corpus dir (default: config.corpus_dir)")
    s.add_argument("--show-query", action="store_true", help="print composed full Boolean and exit")
    s.add_argument("--block-counts", action="store_true", help="print per-block counts and exit")
    s.set_defaults(fn=_cmd_search)

    s = sub.add_parser(
        "acquire",
        help="pull PDFs for the included set (OA via Unpaywall + EZProxy queue for the paywalled tail)",
    )
    s.add_argument("config", help="path to review config YAML")
    s.add_argument("--corpus", help="corpus dir (default: config.corpus_dir)")
    s.add_argument("--records", help="path to records JSONL (default: <corpus>/included.jsonl, fallback records.jsonl)")
    s.add_argument("--ezproxy-host", default=os.environ.get("PAPERSCOPE_EZPROXY_HOST"), help="institutional EZProxy hostname (default: $PAPERSCOPE_EZPROXY_HOST)")
    s.add_argument("--no-oa", action="store_true", help="skip Unpaywall, just generate the EZProxy queue")
    s.add_argument("--no-extract", action="store_true", help="skip PyMuPDF text extraction")
    s.add_argument("--upload-b2", action="store_true", help="upload acquired PDFs to Backblaze B2")
    s.add_argument("--limit", type=int, default=0, help="cap OA fetches (0 = all)")
    s.set_defaults(fn=_cmd_acquire)

    s = sub.add_parser(
        "browser-harvest",
        help="Playwright-driven institutional-access PDF harvest of the paywalled tail",
    )
    s.add_argument("--config", help="path to review config YAML (optional if --corpus given)")
    s.add_argument("--corpus", help="corpus dir")
    s.add_argument("--records", help="JSON/JSONL records source (default: <corpus>/included.jsonl)")
    s.add_argument("--ezproxy-host", default=os.environ.get("PAPERSCOPE_EZPROXY_HOST"), help="institutional EZProxy host (default: $PAPERSCOPE_EZPROXY_HOST)")
    s.add_argument("--concurrency", type=int, default=4, help="parallel pages (default: 4)")
    s.add_argument("--headless", action="store_true", help="run headless (after initial warmup)")
    s.add_argument("--limit", type=int, default=0, help="cap records (0 = all)")
    s.add_argument("--no-skip-existing", action="store_true", help="re-attempt papers already in papers/")
    s.add_argument("--warmup-doi", help="warmup DOI for the first headed-mode auth flow")
    s.add_argument(
        "--user-data-dir",
        help="path to a real Chrome profile (e.g. ~/Library/Application Support/Google/Chrome). "
        "Inherits cookies + saved passwords + live SSO. Chrome must not be running with that profile.",
    )
    s.add_argument(
        "--profile-directory",
        help="profile subdir under user-data-dir (e.g. 'Default', 'Profile 1'). Optional.",
    )
    s.add_argument(
        "--inter-paper-delay",
        type=float,
        default=0.0,
        help="seconds to sleep between papers (after acquiring concurrency slot). "
        "Use 5-10 for IDPs that rate-limit (e.g. Sydney via Google).",
    )
    s.add_argument(
        "--group-by-publisher",
        action="store_true",
        help="sort the queue by DOI prefix so consecutive papers share a publisher domain — "
        "minimises SAML/OAuth handshakes (one per publisher instead of one per paper).",
    )
    s.set_defaults(fn=_cmd_browser_harvest)

    vp = sub.add_parser("validate", help="human-in-the-loop validation of AI screening/extraction decisions")
    vsub = vp.add_subparsers(dest="vcmd", required=True)

    w = vsub.add_parser("workbook", help="decisions + self-audit + rubric -> scroll-through HTML workbook")
    w.add_argument("--decisions", required=True, help="decisions JSONL (screening.jsonl / extraction.jsonl)")
    w.add_argument("--self-audit", help="self-audit JSONL precomputed by a SelfAuditor (flagged items sort to top)")
    w.add_argument("--rubric", help="friction-point rubric YAML (default: generic agree/flag)")
    w.add_argument("--records", help="records JSONL for source context (default: <corpus>/records.jsonl)")
    w.add_argument("--corpus", help="corpus dir (for records.jsonl)")
    w.add_argument("--include-fulltext", action="store_true",
                   help="backfill OPEN-ACCESS abstracts from Europe PMC for records lacking them (never paywalled full text)")
    w.add_argument("--title", help="workbook title")
    w.add_argument("--wb-id", help="workbook id (localStorage namespace)")
    w.add_argument("--out", required=True, help="output HTML path")
    w.set_defaults(fn=_cmd_validate_workbook)

    r = vsub.add_parser("reconcile", help="human export -> validation-overrides + requeue (append-only)")
    r.add_argument("--decisions", required=True, help="original decisions JSONL")
    r.add_argument("--human-export", required=True, help="JSON export from the workbook")
    r.add_argument("--out", default="validation-overrides.jsonl", help="overrides JSONL out")
    r.add_argument("--requeue", default="requeue.jsonl", help="requeue JSONL out")
    r.set_defaults(fn=_cmd_validate_reconcile)

    su = vsub.add_parser("summary", help="validation-overrides -> calibration summary JSON")
    su.add_argument("--validation", required=True, help="validation-overrides JSONL")
    su.add_argument("--out", default="validation-summary.json", help="summary JSON out")
    su.set_defaults(fn=_cmd_validate_summary)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
