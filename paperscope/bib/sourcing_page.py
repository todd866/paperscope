"""Generate an HTML page with clickable links for manually sourcing missing PDFs."""

import html
import json
import os
import re
import urllib.parse
from datetime import date
from pathlib import Path


def _esc(s: str) -> str:
    return html.escape(s.replace("{", "").replace("}", "").replace("\\", ""))


def _build_card(ref: dict) -> str:
    key = ref["cite_key"]
    title = _esc(ref.get("title", ""))
    authors = _esc(ref.get("authors", ""))
    year = ref.get("year", "")
    doi = ref.get("doi", "")
    journal = _esc(ref.get("journal", ""))

    title_q = urllib.parse.quote_plus(
        ref.get("title", "").replace("{", "").replace("}", "").replace("\\", "")
    )
    author_q = urllib.parse.quote_plus(
        authors.split(",")[0].split(" and ")[0].strip()
    )

    entry_type = ref.get("entry_type", "")

    links = []
    if doi:
        links.append(f'<a class="button" href="https://doi.org/{doi}">DOI</a>')
    links.append(
        f'<a class="button alt" href="https://scholar.google.com/scholar?q={title_q}+{author_q}">Scholar</a>'
    )
    links.append(
        f'<a class="button alt" href="https://www.google.com/search?q={title_q}+{author_q}+pdf">Google PDF</a>'
    )
    if doi:
        links.append(f'<a class="button alt" href="https://sci-hub.se/{doi}">Sci-Hub</a>')
    # Anna's Archive for books and hard-to-find items
    anna_q = urllib.parse.quote_plus(
        ref.get("title", "").replace("{", "").replace("}", "").replace("\\", "")
    )
    links.append(
        f'<a class="button anna" href="https://annas-archive.li/search?q={anna_q}">Anna\'s Archive</a>'
    )

    badges = []
    if not doi:
        badges.append('<span class="badge warn">No DOI</span>')
    if entry_type == "book":
        badges.append('<span class="badge book">Book</span>')
    if journal:
        badges.append(f'<span class="badge">{journal}</span>')

    return f"""<article class="card">
<div class="topline"><span class="key">{key}</span><div class="title">{title}</div></div>
<div class="meta">{authors} ({year})</div>
<div class="badges">{"".join(badges)}</div>
<div class="links">{"".join(links)}</div>
</article>"""


_CSS = """
body { font-family: Georgia, 'Times New Roman', serif; margin: 0; background: #f5f2ea; color: #1f1b16; }
main { max-width: 1100px; margin: 0 auto; padding: 32px 24px 72px; }
h1 { margin: 0 0 8px; font-size: 2.4rem; }
.subtitle { color: #5a5044; max-width: 800px; }
.stats { display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap: 12px; margin: 24px 0 28px; }
.stat { background: #fffaf1; border: 1px solid #d9ccb7; border-radius: 14px; padding: 14px 16px; box-shadow: 0 4px 14px rgba(50,40,20,0.06); }
.card { background: #fffdf8; border: 1px solid #d9ccb7; border-radius: 16px; padding: 18px 18px 12px; margin: 0 0 18px; box-shadow: 0 6px 18px rgba(50,40,20,0.07); }
.topline { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; }
.key { font-family: 'Menlo', monospace; font-size: 0.9rem; background: #efe4d2; border-radius: 999px; padding: 4px 10px; }
.title { font-size: 1.25rem; font-weight: 700; }
.meta { color: #6b5e50; margin-top: 6px; }
.badges { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 14px; }
.badge { background: #e7f1e6; color: #234326; border-radius: 999px; padding: 5px 10px; font-size: 0.88rem; }
.badge.warn { background: #f7e7d1; color: #6e4d16; }
.links { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0 10px; }
.button { text-decoration: none; color: #fff; background: #8c3d2d; padding: 8px 12px; border-radius: 10px; }
.button.alt { background: #446; }
.button.anna { background: #2d6e8c; }
.badge.book { background: #e0d6f1; color: #3b2566; }
footer { margin-top: 32px; color: #6b5e50; }
"""


def generate_sourcing_page(
    bib_path: Path,
    tex_path: Path,
    pdf_dir: Path,
    output_path: Path,
    skip_books: bool = True,
    skip_web_only: bool = True,
    skip_own_unpublished: bool = True,
) -> int:
    """Generate HTML sourcing page for missing PDFs.

    Args:
        bib_path: Path to bibliography.json
        tex_path: Path to main .tex file (to check which refs are cited)
        pdf_dir: Path to pdfs/ directory
        output_path: Where to write the HTML file
        skip_books: Exclude book entries (no PDF expected)
        skip_web_only: Exclude web-only resources (Distill, blog posts)
        skip_own_unpublished: Exclude own unpublished papers

    Returns:
        Number of missing references listed.
    """
    with open(bib_path) as f:
        bib = json.load(f)

    existing_pdfs = set(
        os.path.splitext(f)[0]
        for f in os.listdir(pdf_dir)
        if f.endswith(".pdf")
    ) if pdf_dir.is_dir() else set()

    # Also check text/ directory for web-harvested articles
    text_dir = pdf_dir.parent / "text"
    existing_text = set(
        os.path.splitext(f)[0]
        for f in os.listdir(text_dir)
        if f.endswith(".txt")
    ) if text_dir.is_dir() else set()

    # Combined: anything with a PDF or text file is "acquired"
    acquired = existing_pdfs | existing_text

    with open(tex_path) as f:
        tex = f.read()

    cited_keys: set[str] = set()
    for match in re.findall(r"\\cite[tp]?\{([^}]+)\}", tex):
        for part in match.split(","):
            cited_keys.add(part.strip())

    total_refs = len(bib["references"])
    total_dois = sum(1 for r in bib["references"] if r.get("doi"))
    total_pdfs = len(acquired)

    # Identify skip sets
    skip_keys: set[str] = set()
    for r in bib["references"]:
        key = r["cite_key"]
        entry_type = r.get("entry_type", "")
        journal = r.get("journal", "").lower()

        if skip_books and entry_type == "book":
            skip_keys.add(key)
        if skip_web_only and any(
            s in journal
            for s in ["distill", "transformer circuits", "blog", "url{"]
        ):
            skip_keys.add(key)
        if skip_own_unpublished and key.startswith("todd") and r.get("note", "").lower() in ("accepted", "in press", "submitted"):
            skip_keys.add(key)

    missing = [
        r
        for r in bib["references"]
        if r["cite_key"] not in acquired
        and r["cite_key"] in cited_keys
        and r["cite_key"] not in skip_keys
    ]

    cards = "".join(_build_card(r) for r in missing)

    paper_name = tex_path.stem.replace("_", " ").title()

    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>{_esc(paper_name)} — Papers To Source</title>
<style>{_CSS}</style></head><body><main>
<h1>{_esc(paper_name)} — Papers To Source</h1>
<p class="subtitle">Cited references that still need PDFs sourced manually. Books, web-only resources, and own unpublished papers excluded.</p>
<div class="stats">
<div class="stat"><b>{total_pdfs}</b> PDFs acquired</div>
<div class="stat"><b>{len(missing)}</b> Still need sourcing</div>
<div class="stat"><b>{total_dois}/{total_refs}</b> DOIs resolved</div>
<div class="stat"><b>{total_pdfs}/{total_refs}</b> Full text available</div>
</div>
{cards}
<footer>Generated on {date.today().isoformat()}. Drop PDFs into <code>{pdf_dir}</code> named as <code>cite_key.pdf</code>.</footer>
</main></body></html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(page)

    return len(missing)


def sourcing_page_main(
    data_dir: Path,
    tex_file: Path,
    output: Path | None = None,
) -> int:
    """CLI entry point."""
    bib_path = data_dir / "bibliography.json"
    pdf_dir = data_dir / "pdfs"

    if output is None:
        output = Path.home() / "Desktop" / f"{tex_file.stem}_papers_to_source.html"

    count = generate_sourcing_page(
        bib_path=bib_path,
        tex_path=tex_file,
        pdf_dir=pdf_dir,
        output_path=output,
        skip_books=False,
    )

    print(f"Wrote {count} missing references to {output}")
    return 0
