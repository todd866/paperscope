"""Allow running as python -m paperscope."""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Paperscope — AI-assisted research infrastructure",
        prog="paperscope",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # extract command
    extract_parser = subparsers.add_parser(
        "extract", help="Extract citations from a LaTeX project"
    )
    extract_parser.add_argument(
        "project_root",
        type=Path,
        help="Root directory of the LaTeX project",
    )
    extract_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output path for bibliography.json (default: <project_root>/literature/bibliography.json)",
    )
    extract_parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Only print stats, don't write output",
    )

    # resolve command
    resolve_parser = subparsers.add_parser(
        "resolve", help="Resolve missing DOIs via CrossRef"
    )
    resolve_parser.add_argument(
        "bibliography",
        type=Path,
        help="Path to bibliography.json",
    )
    resolve_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without saving changes",
    )
    resolve_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max references to resolve (0 = all)",
    )
    resolve_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    # verify command
    verify_parser = subparsers.add_parser(
        "verify", help="Verify DOIs against CrossRef metadata"
    )
    verify_parser.add_argument(
        "bibliography",
        type=Path,
        help="Path to bibliography.json",
    )
    verify_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max references to verify (0 = all)",
    )

    # harvest command
    harvest_parser = subparsers.add_parser(
        "harvest", help="Discover new papers"
    )
    harvest_parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml",
    )

    # pre-submit command
    presubmit_parser = subparsers.add_parser(
        "pre-submit", help="Pre-submission citation check"
    )
    presubmit_parser.add_argument(
        "tex_file",
        type=Path,
        help="Path to main .tex file",
    )
    presubmit_parser.add_argument(
        "--bib",
        type=Path,
        default=None,
        help="Path to bibliography.json",
    )

    # ingest command
    ingest_parser = subparsers.add_parser(
        "ingest", help="Acquire OA PDFs and extract text"
    )
    ingest_parser.add_argument(
        "data_dir",
        type=Path,
        help="Path to literature-data directory (contains bibliography.json)",
    )
    ingest_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max references to process (0 = all)",
    )
    ingest_parser.add_argument(
        "--paper",
        type=str,
        default=None,
        help="Filter to refs from a specific paper folder (e.g. 'biosystems/40_simulated_geometry')",
    )
    ingest_parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip OA download, only extract text from existing PDFs",
    )
    ingest_parser.add_argument(
        "--upload-b2",
        action="store_true",
        help="Upload acquired PDFs to Backblaze B2",
    )
    ingest_parser.add_argument(
        "--audit",
        action="store_true",
        help="Run the type-routed per-paper validity audit after extraction "
             "(writes <stem>.audit.json; analysis.audit_router)",
    )

    # depth2 command
    depth2_parser = subparsers.add_parser(
        "depth2", help="Harvest depth-2 references from CrossRef"
    )
    depth2_parser.add_argument(
        "data_dir",
        type=Path,
        help="Path to literature-data directory (contains bibliography.json)",
    )
    depth2_parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max depth-1 refs to harvest from (0 = all)",
    )

    # sourcing-page command
    sourcing_parser = subparsers.add_parser(
        "sourcing-page", help="Generate HTML page for manually sourcing missing PDFs"
    )
    sourcing_parser.add_argument(
        "data_dir",
        type=Path,
        help="Path to literature-data directory (contains bibliography.json)",
    )
    sourcing_parser.add_argument(
        "tex_file",
        type=Path,
        help="Path to main .tex file",
    )
    sourcing_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output HTML path (default: ~/Desktop/<paper>_papers_to_source.html)",
    )

    # status command
    status_parser = subparsers.add_parser(
        "status", help="Show pipeline status"
    )
    status_parser.add_argument(
        "data_dir",
        type=Path,
        help="Path to literature-data directory",
    )
    status_parser.add_argument(
        "--by-paper",
        action="store_true",
        help="Show breakdown by paper",
    )

    # === Embedding analysis commands ===

    # analyze command
    analyze_parser = subparsers.add_parser(
        "analyze", help="Run full embedding analysis on a paper"
    )
    analyze_parser.add_argument(
        "tex_file",
        type=Path,
        help="Path to main .tex file",
    )
    analyze_parser.add_argument(
        "--literature", "-l",
        type=Path,
        default=None,
        help="Path to literature/text directory",
    )
    analyze_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output directory (default: alongside .tex file)",
    )

    # journal-fit command
    journal_parser = subparsers.add_parser(
        "journal-fit", help="Rank journals by semantic fit to a paper"
    )
    journal_parser.add_argument(
        "tex_file",
        type=Path,
        help="Path to main .tex file",
    )
    journal_parser.add_argument(
        "--journals", "-j",
        nargs="+",
        required=True,
        help="Journal names or OpenAlex source IDs",
    )
    journal_parser.add_argument(
        "--n-abstracts",
        type=int,
        default=100,
        help="Abstracts to fetch per journal (default: 100)",
    )

    # abstract-check command
    abstract_parser = subparsers.add_parser(
        "abstract-check", help="Check abstract coverage of paper sections"
    )
    abstract_parser.add_argument(
        "tex_file",
        type=Path,
        help="Path to main .tex file",
    )

    # argument-graph command
    graph_parser = subparsers.add_parser(
        "argument-graph", help="Build cross-paper dependency graph"
    )
    graph_parser.add_argument(
        "project_root",
        type=Path,
        help="Root directory containing paper subdirectories",
    )
    graph_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output PNG path",
    )
    graph_parser.add_argument(
        "--threshold",
        type=float,
        default=0.7,
        help="Similarity threshold for edges (default: 0.7)",
    )

    # revision-diff command
    diff_parser = subparsers.add_parser(
        "revision-diff", help="Semantic diff between two paper revisions"
    )
    diff_parser.add_argument(
        "old_tex",
        type=Path,
        help="Path to old version .tex file",
    )
    diff_parser.add_argument(
        "new_tex",
        type=Path,
        help="Path to new version .tex file",
    )
    diff_parser.add_argument(
        "--literature", "-l",
        type=Path,
        default=None,
        help="Path to literature/text directory (for direction check)",
    )

    # related command
    related_parser = subparsers.add_parser(
        "related", help="Find potentially missing related work"
    )
    related_parser.add_argument(
        "tex_file",
        type=Path,
        help="Path to main .tex file",
    )
    related_parser.add_argument(
        "--n-results",
        type=int,
        default=50,
        help="Number of candidate papers to return (default: 50)",
    )

    # critical-read command
    cr_parser = subparsers.add_parser(
        "critical-read", help="Critical read of an external paper (PDF or text)"
    )
    cr_parser.add_argument(
        "paper",
        type=Path,
        help="Path to paper (PDF or .txt extracted text)",
    )
    cr_parser.add_argument(
        "--authors",
        nargs="+",
        default=None,
        help="Author names (auto-extracted from text if not provided)",
    )
    cr_parser.add_argument(
        "--methods",
        nargs="+",
        default=None,
        help="Method names used in the paper (auto-detected if not provided)",
    )
    cr_parser.add_argument(
        "--question-resolution",
        nargs="+",
        default=None,
        help="Resolution levels the paper's question requires (e.g., site_specific individual)",
    )
    cr_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output directory (default: alongside paper file)",
    )
    cr_parser.add_argument(
        "--skip-author-lookup",
        action="store_true",
        help="Skip OpenAlex author lookup (offline mode)",
    )

    # annotate command
    annotate_parser = subparsers.add_parser(
        "annotate", help="Build an annotated reading copy of a PDF from a notes spec"
    )
    annotate_parser.add_argument(
        "pdf",
        type=Path,
        help="Source PDF to annotate",
    )
    annotate_parser.add_argument(
        "notes",
        type=Path,
        help="Notes spec (JSON or YAML): notes + optional front-matter / summary / appendix",
    )
    annotate_parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output PDF (default: <pdf-stem>_annotated.pdf)",
    )

    args = parser.parse_args()

    if args.command == "extract":
        from .bib.extract import extract_all, write_output
        refs, stats = extract_all(args.project_root.resolve())
        _print_extraction_stats(stats)
        if not args.stats_only:
            output_path = args.output or (args.project_root.resolve() / "literature" / "bibliography.json")
            write_output(refs, stats, output_path)
        return 0

    elif args.command == "resolve":
        from .bib.resolve import resolve_main
        return resolve_main(
            args.bibliography.resolve(),
            dry_run=args.dry_run,
            limit=args.limit,
            verbose=not args.quiet,
        )

    elif args.command == "verify":
        from .bib.verify import verify_main
        return verify_main(args.bibliography.resolve(), limit=args.limit)

    elif args.command == "harvest":
        from .harvest.cli import discover
        return discover(config_path=args.config)

    elif args.command == "pre-submit":
        from .bib.pre_submit import pre_submit_main
        return pre_submit_main(args.tex_file.resolve(), bib_path=args.bib)

    elif args.command == "ingest":
        from .ingest.pipeline import ingest_main
        return ingest_main(
            data_dir=args.data_dir.resolve(),
            limit=args.limit,
            paper_filter=args.paper,
            skip_download=args.skip_download,
            upload_b2=args.upload_b2,
            audit=args.audit,
        )

    elif args.command == "depth2":
        from .bib.depth2 import harvest_depth2
        return harvest_depth2(
            data_dir=args.data_dir.resolve(),
            limit=args.limit,
            verbose=True,
        )

    elif args.command == "sourcing-page":
        from .bib.sourcing_page import sourcing_page_main
        return sourcing_page_main(
            data_dir=args.data_dir.resolve(),
            tex_file=args.tex_file.resolve(),
            output=args.output.resolve() if args.output else None,
        )

    elif args.command == "status":
        from .ingest.pipeline import status_main
        return status_main(
            data_dir=args.data_dir.resolve(),
            by_paper=args.by_paper,
        )

    elif args.command in {
        "analyze", "journal-fit", "abstract-check", "argument-graph",
        "revision-diff", "related", "critical-read", "annotate",
    }:
        # Analysis runners live in analysis/cli.py. Lazy import keeps the
        # CLI fast for non-analysis subcommands.
        from .analysis import cli as analysis_cli
        runner = {
            "analyze": analysis_cli.run_analyze,
            "journal-fit": analysis_cli.run_journal_fit,
            "abstract-check": analysis_cli.run_abstract_check,
            "argument-graph": analysis_cli.run_argument_graph,
            "revision-diff": analysis_cli.run_revision_diff,
            "related": analysis_cli.run_related,
            "critical-read": analysis_cli.run_critical_read,
            "annotate": analysis_cli.run_annotate,
        }[args.command]
        return runner(args)

    else:
        parser.print_help()
        return 1


def _print_extraction_stats(stats: dict) -> None:
    print(f"\n{'='*60}")
    print("Citation Extraction Report")
    print(f"{'='*60}")
    print(f"  .tex files scanned:     {stats['tex_files_scanned']}")
    print(f"  .bib files scanned:     {stats['bib_files_scanned']}")
    print(f"  bibitem refs found:     {stats['bibitem_refs_found']}")
    print(f"  bibtex refs found:      {stats['bibtex_refs_found']}")
    print(f"  total before dedup:     {stats['total_before_dedup']}")
    print(f"  total after dedup:      {stats['total_after_dedup']}")
    total = max(stats['total_after_dedup'], 1)
    print(f"  with DOI:               {stats['with_doi']} ({100*stats['with_doi']//total}%)")
    print(f"  with arXiv ID:          {stats['with_arxiv']}")
    print(f"  with title extracted:   {stats['with_title']} ({100*stats['with_title']//total}%)")
    print(f"{'='*60}")


if __name__ == "__main__":
    raise SystemExit(main())
