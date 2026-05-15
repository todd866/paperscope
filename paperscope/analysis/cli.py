"""CLI runners for the analysis subcommands.

Pulled out of ``paperscope/__main__.py`` to keep the top-level entrypoint to
just argparse + dispatch (mirrors what ``systematic_review/__main__.py``
already does). Each ``run_*`` is the body of one ``paperscope <cmd>``
subcommand. Imports are lazy so CLI startup stays fast.
"""

from __future__ import annotations


def run_analyze(args) -> int:
    """Run full embedding analysis suite on a paper."""
    import json

    import numpy as np

    from ._common import (
        load_paper, load_reference_texts,
        prepare_paper_chunks, prepare_reference_chunks,
    )
    from .citation_alignment import citation_alignment, uncited_relevance
    from .novelty import novelty_analysis
    from .strength_heatmap import strength_heatmap, plot_strength_heatmap
    from ..text.parsing import extract_citation_contexts, extract_claims
    from ..embed import embed_texts

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


def run_journal_fit(args) -> int:
    """Rank journals by semantic fit."""
    import json
    from ._common import load_paper
    from .journal_targeting import journal_fit

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


def run_abstract_check(args) -> int:
    """Check abstract coverage of paper sections."""
    import json
    from ._common import load_paper
    from .abstract_alignment import abstract_alignment

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


def run_argument_graph(args) -> int:
    """Build cross-paper argument graph."""
    import json
    from .argument_graph import build_argument_graph, plot_argument_graph

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


def run_revision_diff(args) -> int:
    """Semantic diff between two paper revisions."""
    import json
    from ._common import load_paper
    from .revision_diff import revision_diff

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


def run_related(args) -> int:
    """Find potentially missing related work."""
    import json
    from ._common import load_paper
    from .related_radar import related_radar

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


def run_critical_read(args) -> int:
    """Run critical read analysis on an external paper."""
    from .critical_read import critical_read, extract_author_names

    paper_path = args.paper.resolve()

    # Extract text from PDF or read text file
    if paper_path.suffix.lower() == ".pdf":
        try:
            from ..ingest.extract_text import extract_text
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
    critical_read(
        paper_text=paper_text,
        author_names=author_names,
        methods_used=args.methods,
        question_resolution=args.question_resolution,
        output_dir=output_dir,
        skip_author_lookup=args.skip_author_lookup,
    )

    return 0
