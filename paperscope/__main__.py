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

    elif args.command == "analyze":
        return _run_analyze(args)

    elif args.command == "journal-fit":
        return _run_journal_fit(args)

    elif args.command == "abstract-check":
        return _run_abstract_check(args)

    elif args.command == "argument-graph":
        return _run_argument_graph(args)

    elif args.command == "revision-diff":
        return _run_revision_diff(args)

    elif args.command == "related":
        return _run_related(args)

    elif args.command == "critical-read":
        return _run_critical_read(args)

    else:
        parser.print_help()
        return 1


def _run_analyze(args) -> int:
    """Run full embedding analysis suite on a paper."""
    import json
    from .analysis._common import (
        load_paper, load_reference_texts,
        prepare_paper_chunks, prepare_reference_chunks,
    )
    from .analysis.citation_alignment import citation_alignment, uncited_relevance
    from .analysis.novelty import novelty_analysis
    from .analysis.reviewer_probes import reviewer_probes
    from .analysis.strength_heatmap import strength_heatmap, plot_strength_heatmap
    from .text.parsing import extract_citation_contexts, extract_claims
    from .embed import embed_texts

    tex_path = args.tex_file.resolve()
    tex_text = load_paper(tex_path)
    out_dir = args.output or tex_path.parent / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Find literature directory
    lit_dir = args.literature
    if lit_dir is None:
        for candidate in [tex_path.parent / "literature" / "text",
                          tex_path.parent / "text"]:
            if candidate.is_dir():
                lit_dir = candidate
                break

    print("Extracting citation contexts...")
    contexts = extract_citation_contexts(tex_text)
    print(f"  {len(contexts)} citation contexts")

    print("Extracting claims...")
    claims = extract_claims(tex_text)
    print(f"  {len(claims)} claims")

    print("Extracting paragraphs...")
    paper_chunks = prepare_paper_chunks(tex_text)
    print(f"  {len(paper_chunks)} paragraphs")

    # Load and chunk literature
    ref_texts = load_reference_texts(lit_dir) if lit_dir else {}
    print(f"Loading literature: {len(ref_texts)} references")
    chunk_texts, chunk_keys = prepare_reference_chunks(ref_texts)
    print(f"  {len(chunk_texts)} chunks")

    # Embed everything
    print("Embedding...")
    all_texts = (
        [c["text"] for c in contexts]
        + [c["text"] for c in claims]
        + [c["text"] for c in paper_chunks]
        + chunk_texts
    )
    emb, backend = embed_texts(all_texts)
    n_ctx = len(contexts)
    n_clm = len(claims)
    n_par = len(paper_chunks)
    ctx_emb = emb[:n_ctx]
    claim_emb = emb[n_ctx:n_ctx + n_clm]
    paper_emb = emb[n_ctx + n_clm:n_ctx + n_clm + n_par]
    chunk_emb = emb[n_ctx + n_clm + n_par:]

    # Run analyses
    print("Running citation alignment...")
    alignment = citation_alignment(contexts, ctx_emb, chunk_keys, chunk_emb)

    print("Running novelty analysis...")
    novelty = novelty_analysis(claims, claim_emb, chunk_keys, chunk_emb)

    print("Finding uncited relevant references...")
    uncited = uncited_relevance(
        contexts, ctx_emb, list(ref_texts.keys()), chunk_keys, chunk_emb,
    )

    print("Computing strength heatmap...")
    heatmap = strength_heatmap(paper_chunks, paper_emb, chunk_keys, chunk_emb)
    plot_strength_heatmap(heatmap, out_dir / "strength_heatmap.png")

    # Summary
    top3_hits = sum(1 for c in alignment if c["any_cited_in_top3"])
    cited_sims = [c["best_cited_sim"] for c in alignment if c["best_cited_sim"] > 0]
    import numpy as np
    results = {
        "backend": backend,
        "summary": {
            "n_contexts": len(contexts),
            "n_claims": len(claims),
            "n_paragraphs": len(paper_chunks),
            "n_refs": len(ref_texts),
            "n_chunks": len(chunk_texts),
            "top3_rate": top3_hits / max(len(alignment), 1),
            "mean_cited_sim": float(np.mean(cited_sims)) if cited_sims else 0.0,
            "weak_paragraphs": heatmap["summary"].get("weak_paragraphs", 0),
        },
        "citation_alignment": alignment,
        "novelty": novelty,
        "uncited_relevance": uncited,
        "strength_heatmap": heatmap,
    }

    results_path = out_dir / "analysis_results.json"
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    # Print summary
    print(f"\n{'='*60}")
    print("Analysis Summary")
    print(f"{'='*60}")
    print(f"  Citation contexts:    {len(contexts)}")
    print(f"  Claims:               {len(claims)}")
    print(f"  Top-3 alignment:      {top3_hits}/{len(alignment)} ({top3_hits/max(len(alignment),1):.0%})")
    if cited_sims:
        print(f"  Mean cited sim:       {np.mean(cited_sims):.3f}")
    print(f"  Novel claims (<0.4):  {sum(1 for c in novelty if c['novelty_flag'])}")
    print(f"  Uncited relevant:     {len(uncited)}")
    print(f"  Weak paragraphs:      {heatmap['summary'].get('weak_paragraphs', 0)}")
    print(f"{'='*60}")
    print(f"Results: {results_path}")
    return 0


def _run_journal_fit(args) -> int:
    """Rank journals by semantic fit."""
    import json
    from .analysis._common import load_paper
    from .analysis.journal_targeting import journal_fit

    tex_text = load_paper(args.tex_file.resolve())
    print(f"Analyzing journal fit for: {args.tex_file.name}")

    result = journal_fit(
        tex_text,
        journal_queries=args.journals,
        n_per_journal=args.n_abstracts,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print(f"\n{'='*60}")
    print("Journal Fit Rankings")
    print(f"{'='*60}")
    for r in result["rankings"]:
        if "error" in r:
            print(f"  {r['journal']}: {r['error']}")
        else:
            print(f"  {r['journal']}: {r['fit_score']:.3f} "
                  f"(n={r['n_abstracts']}, range={r.get('min_paragraph_fit',0):.2f}-{r.get('max_paragraph_fit',0):.2f})")
    print(f"{'='*60}")

    out_path = args.tex_file.resolve().parent / "journal_fit.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Details: {out_path}")
    return 0


def _run_abstract_check(args) -> int:
    """Check abstract coverage of paper sections."""
    import json
    from .analysis._common import load_paper
    from .analysis.abstract_alignment import abstract_alignment

    tex_text = load_paper(args.tex_file.resolve())
    print(f"Checking abstract alignment for: {args.tex_file.name}")

    result = abstract_alignment(tex_text)

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print(f"\n{'='*60}")
    print("Abstract Section Coverage")
    print(f"{'='*60}")
    print(f"  Overall coverage: {result['overall_coverage']:.3f}")
    print(f"  Median coverage:  {result['median_coverage']:.3f}")
    print()
    for s in result["sections"]:
        marker = " **" if s in result.get("underrepresented", []) else ""
        print(f"  {s['abstract_similarity']:.3f}  {s['title']}{marker}")
    if result.get("underrepresented"):
        print(f"\n  ** = underrepresented in abstract")
    print(f"{'='*60}")

    out_path = args.tex_file.resolve().parent / "abstract_alignment.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Details: {out_path}")
    return 0


def _run_argument_graph(args) -> int:
    """Build cross-paper argument graph."""
    import json
    from .analysis.argument_graph import build_argument_graph, plot_argument_graph

    project_root = args.project_root.resolve()
    print(f"Scanning papers in: {project_root}")

    result = build_argument_graph(
        project_root,
        similarity_threshold=args.threshold,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print(f"\n{'='*60}")
    print("Argument Graph")
    print(f"{'='*60}")
    print(f"  Papers found:    {result['stats']['n_papers']}")
    print(f"  Dependencies:    {result['stats']['n_edges']}")
    if result["stats"]["n_edges"] > 0:
        print(f"  Mean similarity: {result['stats']['mean_edge_sim']:.3f}")
    print()
    for edge in result["edges"][:15]:
        print(f"  {edge['from']} -> {edge['to']} ({edge['similarity']:.3f})")
    print(f"{'='*60}")

    out_png = args.output or (project_root / "argument_graph.png")
    plot_argument_graph(result, out_png)
    print(f"Graph: {out_png}")

    out_json = out_png.with_suffix(".json")
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Details: {out_json}")
    return 0


def _run_revision_diff(args) -> int:
    """Semantic diff between two paper revisions."""
    import json
    from .analysis._common import load_paper
    from .analysis.revision_diff import revision_diff

    old_tex = load_paper(args.old_tex.resolve())
    new_tex = load_paper(args.new_tex.resolve())
    print(f"Comparing: {args.old_tex.name} -> {args.new_tex.name}")

    result = revision_diff(
        old_tex, new_tex,
        literature_dir=args.literature.resolve() if args.literature else None,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print(f"\n{'='*60}")
    print("Revision Diff")
    print(f"{'='*60}")
    summary = result.get("summary", {})
    print(f"  Sections compared: {summary.get('n_sections_compared', 0)}")
    print(f"  Sections added:    {summary.get('n_sections_added', 0)}")
    print(f"  Mean shift:        {summary.get('mean_shift', 0):.3f}")
    print(f"  Most changed:      {summary.get('most_changed', 'N/A')}")
    print()
    for d in result.get("section_diffs", []):
        wc = f" ({d['word_count_change']:+d} words)" if d.get("word_count_change") else ""
        print(f"  {d['semantic_shift']:.3f}  {d['old_title']}{wc}")

    if result.get("literature_direction"):
        ld = result["literature_direction"]
        direction = "toward" if ld["moved_toward_literature"] else "away from"
        print(f"\n  Literature direction: moved {direction} literature (delta={ld['delta']:+.3f})")
    print(f"{'='*60}")

    out_path = args.new_tex.resolve().parent / "revision_diff.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Details: {out_path}")
    return 0


def _run_related(args) -> int:
    """Find potentially missing related work."""
    import json
    from .analysis._common import load_paper
    from .analysis.related_radar import related_radar

    tex_text = load_paper(args.tex_file.resolve())
    print(f"Searching for missing related work: {args.tex_file.name}")

    result = related_radar(
        tex_text,
        n_results=args.n_results,
    )

    if "error" in result:
        print(f"Error: {result['error']}")
        return 1

    print(f"\n{'='*60}")
    print("Related Work Radar")
    print(f"{'='*60}")
    stats = result.get("stats", {})
    print(f"  Papers searched:  {stats.get('n_searched', 0)}")
    print(f"  After filtering:  {stats.get('n_after_filter', 0)}")
    print(f"  Returned:         {stats.get('n_returned', 0)}")
    print()
    for c in result.get("candidates", [])[:20]:
        year = f"({c.get('year', '?')})" if c.get("year") else ""
        print(f"  {c['relevance_score']:.3f}  {c['title'][:70]} {year}")
        if c.get("authors"):
            print(f"          {c['authors'][:60]}")
    print(f"{'='*60}")

    out_path = args.tex_file.resolve().parent / "related_radar.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Details: {out_path}")
    return 0


def _run_critical_read(args) -> int:
    """Run critical read analysis on an external paper."""
    from .analysis.critical_read import critical_read, extract_author_names

    paper_path = args.paper.resolve()

    # Extract text from PDF or read text file
    if paper_path.suffix.lower() == ".pdf":
        try:
            from .ingest.extract_text import extract_text
            print(f"Extracting text from: {paper_path.name}")
            paper_text = extract_text(paper_path)
        except ImportError:
            print("Error: PyMuPDF (fitz) required for PDF extraction.")
            print("Install with: pip install PyMuPDF")
            return 1
    else:
        paper_text = paper_path.read_text(encoding="utf-8", errors="replace")

    if not paper_text.strip():
        print("Error: no text extracted from paper")
        return 1

    print(f"Extracted {len(paper_text)} chars from {paper_path.name}")

    # Author names
    author_names = args.authors
    if author_names is None:
        author_names = extract_author_names(paper_text)
        if author_names:
            print(f"Auto-detected authors: {', '.join(author_names)}")

    output_dir = args.output or paper_path.parent
    result = critical_read(
        paper_text=paper_text,
        author_names=author_names,
        methods_used=args.methods,
        question_resolution=args.question_resolution,
        output_dir=output_dir,
        skip_author_lookup=args.skip_author_lookup,
    )

    return 0


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
