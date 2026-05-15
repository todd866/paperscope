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

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
