"""CLI entry: `python -m paperscope.systematic_review <subcommand> [args]`.

Lightweight dispatcher — each subcommand is one well-scoped operation against
a ReviewConfig + a corpus directory. Heavy LLM-orchestrated steps (screen,
extract) live outside this CLI since their implementation depends on which
agent SDK the caller wires in.
"""

from __future__ import annotations

import argparse
import json
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
            verbose=True,
        )
    )
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
    s.add_argument("--ezproxy-host", default="ezproxy.library.usyd.edu.au", help="institutional EZProxy hostname")
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
    s.add_argument("--ezproxy-host", default="ezproxy.library.usyd.edu.au", help="institutional EZProxy host")
    s.add_argument("--concurrency", type=int, default=4, help="parallel pages (default: 4)")
    s.add_argument("--headless", action="store_true", help="run headless (after initial warmup)")
    s.add_argument("--limit", type=int, default=0, help="cap records (0 = all)")
    s.add_argument("--no-skip-existing", action="store_true", help="re-attempt papers already in papers/")
    s.add_argument("--warmup-doi", help="warmup DOI for the first headed-mode auth flow")
    s.set_defaults(fn=_cmd_browser_harvest)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
