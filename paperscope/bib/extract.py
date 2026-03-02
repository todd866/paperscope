"""
Citation extractor for LaTeX projects.

Walks all .tex and .bib files, extracts structured reference data,
deduplicates, and outputs bibliography.json.

Handles two citation formats:
1. Embedded: thebibliography blocks with bibitem entries
2. External: .bib files with @article{key, ...}, @book{key, ...}, etc.
"""

import json
import os
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class Reference:
    """A single bibliographic reference extracted from .tex or .bib."""

    cite_key: str
    title: str = ""
    authors: str = ""
    year: str = ""
    journal: str = ""
    volume: str = ""
    number: str = ""
    pages: str = ""
    doi: str = ""
    publisher: str = ""
    entry_type: str = ""  # article, book, inproceedings, etc.
    source_file: str = ""  # which .tex or .bib file this came from
    source_format: str = ""  # "bibitem" or "bibtex"
    raw_text: str = ""  # original text for debugging
    url: str = ""
    arxiv_id: str = ""
    alternate_keys: List[str] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)

    @property
    def normalized_title(self) -> str:
        """Title stripped of LaTeX markup and lowercased for dedup."""
        t = self.title
        t = re.sub(r"\\textit\{([^}]*)\}", r"\1", t)
        t = re.sub(r"\\textbf\{([^}]*)\}", r"\1", t)
        t = re.sub(r"\\emph\{([^}]*)\}", r"\1", t)
        t = re.sub(r"\{([^}]*)\}", r"\1", t)
        t = re.sub(r"\\[a-zA-Z]+", "", t)
        t = re.sub(r"[{}$\\]", "", t)
        t = re.sub(r"\s+", " ", t).strip().lower()
        return t

    def merge_from(self, other: "Reference") -> None:
        """Fill in missing fields from another reference to the same work."""
        for f in [
            "title", "authors", "year", "journal", "volume", "number",
            "pages", "doi", "publisher", "entry_type", "url", "arxiv_id",
        ]:
            mine = getattr(self, f)
            theirs = getattr(other, f)
            if not mine and theirs:
                setattr(self, f, theirs)
            elif (
                mine and theirs
                and self.source_format == "bibitem"
                and other.source_format == "bibtex"
            ):
                setattr(self, f, theirs)


# ---------------------------------------------------------------------------
# BibTeX (.bib) parser
# ---------------------------------------------------------------------------


def parse_bib_file(path: Path) -> List[Reference]:
    """Parse a .bib file into Reference objects."""
    text = path.read_text(encoding="utf-8", errors="replace")
    refs = []

    entry_starts = list(
        re.finditer(r"@(\w+)\s*\{([^,\s]+)\s*,", text, re.IGNORECASE)
    )

    for match in entry_starts:
        entry_type = match.group(1).lower()
        cite_key = match.group(2).strip()

        body = _extract_braced_body(text, match.start())
        if body is None:
            continue

        ref = Reference(
            cite_key=cite_key,
            entry_type=entry_type,
            source_file=str(path),
            source_format="bibtex",
            raw_text=body[:500],
        )

        fields = _parse_bib_fields(body)
        ref.title = _clean_bib_value(fields.get("title", ""))
        ref.authors = _clean_bib_value(fields.get("author", ""))
        ref.year = _clean_bib_value(fields.get("year", ""))
        ref.journal = _clean_bib_value(fields.get("journal", ""))
        ref.volume = _clean_bib_value(fields.get("volume", ""))
        ref.number = _clean_bib_value(fields.get("number", ""))
        ref.pages = _clean_bib_value(fields.get("pages", ""))
        ref.doi = _clean_bib_value(fields.get("doi", ""))
        ref.publisher = _clean_bib_value(fields.get("publisher", ""))
        ref.url = _clean_bib_value(fields.get("url", ""))

        eprint = _clean_bib_value(fields.get("eprint", ""))
        if eprint and "arxiv" in fields.get("archiveprefix", "").lower():
            ref.arxiv_id = eprint
        elif not ref.arxiv_id:
            note = fields.get("note", "")
            arxiv_match = re.search(r"arXiv[:\s]*(\d{4}\.\d{4,5})", note)
            if arxiv_match:
                ref.arxiv_id = arxiv_match.group(1)

        refs.append(ref)

    return refs


def _extract_braced_body(text: str, start: int) -> Optional[str]:
    """Extract content between matched braces starting from position."""
    brace_pos = text.find("{", start)
    if brace_pos == -1:
        return None

    depth = 0
    for i in range(brace_pos, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_pos + 1 : i]
    return None


def _parse_bib_fields(body: str) -> Dict[str, str]:
    """Parse field = {value} or field = "value" or field = number from bib body."""
    fields: Dict[str, str] = {}

    pos = 0
    while pos < len(body):
        field_match = re.search(r"(\w+)\s*=\s*", body[pos:])
        if not field_match:
            break

        field_name = field_match.group(1).lower()
        value_start = pos + field_match.end()

        if value_start >= len(body):
            break

        char = body[value_start]
        if char == "{":
            depth = 0
            end = value_start
            for i in range(value_start, len(body)):
                if body[i] == "{":
                    depth += 1
                elif body[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            value = body[value_start + 1 : end]
            pos = end + 1
        elif char == '"':
            end = body.find('"', value_start + 1)
            if end == -1:
                end = len(body)
            value = body[value_start + 1 : end]
            pos = end + 1
        else:
            end_match = re.search(r"[,\s}]", body[value_start:])
            if end_match:
                value = body[value_start : value_start + end_match.start()]
                pos = value_start + end_match.start()
            else:
                value = body[value_start:]
                pos = len(body)

        fields[field_name] = value.strip()
        pos = max(pos, value_start + 1)

    return fields


def _clean_bib_value(value: str) -> str:
    """Clean a BibTeX field value."""
    if not value:
        return ""
    value = re.sub(r"^\{(.*)\}$", r"\1", value.strip())
    value = re.sub(r"\s+", " ", value).strip()
    return value


# ---------------------------------------------------------------------------
# \bibitem parser (embedded bibliography in .tex)
# ---------------------------------------------------------------------------


def parse_bibitem_block(tex_path: Path) -> List[Reference]:
    """Extract references from \\begin{thebibliography} blocks in a .tex file."""
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    refs = []

    bib_blocks = re.findall(
        r"\\begin\{thebibliography\}.*?\n(.*?)\\end\{thebibliography\}",
        text,
        re.DOTALL,
    )

    for block in bib_blocks:
        items = re.split(r"\\bibitem\{([^}]+)\}", block)

        for i in range(1, len(items) - 1, 2):
            cite_key = items[i].strip()
            body = items[i + 1].strip()

            body = re.sub(r"\\end\{thebibliography\}.*", "", body, flags=re.DOTALL)
            body = body.strip()

            ref = Reference(
                cite_key=cite_key,
                source_file=str(tex_path),
                source_format="bibitem",
                raw_text=body[:500],
            )

            _parse_bibitem_body(ref, body)
            refs.append(ref)

    return refs


def _parse_bibitem_body(ref: Reference, body: str) -> None:
    """Parse an unstructured bibitem text into structured fields."""
    # Extract DOI
    doi_match = re.search(
        r"(?:doi[:\s]*|https?://doi\.org/)([0-9]+\.[^\s}]+)", body, re.IGNORECASE
    )
    if doi_match:
        ref.doi = doi_match.group(1).rstrip(".")

    # Extract URL
    url_match = re.search(r"\\(?:url|href)\{([^}]+)\}", body)
    if url_match:
        ref.url = url_match.group(1)

    # Extract arXiv ID
    arxiv_match = re.search(
        r"arXiv[:\s]*(?:preprint\s*)?(?:arXiv:)?(\d{4}\.\d{4,5}|[a-z-]+/\d{7})",
        body,
        re.IGNORECASE,
    )
    if arxiv_match:
        ref.arxiv_id = arxiv_match.group(1)

    # Backtick-quoted title (PRL/physics style)
    backtick_match = re.search(r"``(.*?)(?:,\s*)?''", body)
    if backtick_match:
        ref.title = backtick_match.group(1).strip()
        before_title = body[: backtick_match.start()].strip().rstrip(",").strip()
        before_title = re.sub(r"~", " ", before_title)
        before_title = re.sub(r"\\textit\{[^}]*\}", "", before_title)
        before_title = re.sub(r"[{}]", "", before_title)
        before_title = re.sub(r"\s+", " ", before_title).strip()
        if before_title:
            ref.authors = before_title
        after_title = body[backtick_match.end() :].strip()
        after_clean = re.sub(r"\\textit\{([^}]*)\}", r"\1", after_title)
        after_clean = re.sub(r"\\textbf\{([^}]*)\}", r"\1", after_clean)
        after_clean = re.sub(r"\\href\{[^}]*\}\{[^}]*\}", "", after_clean)
        after_clean = re.sub(r"[{}]", "", after_clean)
        after_clean = re.sub(r"\s+", " ", after_clean).strip()
        jvpy = re.match(
            r"^(.*?)\s+(\d+),\s*([\d\-\u2013]+)\s*\((\d{4})\)", after_clean
        )
        if jvpy:
            ref.journal = jvpy.group(1).strip().rstrip(",")
            ref.volume = jvpy.group(2)
            ref.pages = jvpy.group(3).replace("\u2013", "--")
            ref.year = jvpy.group(4)
        else:
            year_m = re.search(r"\((\d{4})\)", after_clean)
            if year_m:
                ref.year = year_m.group(1)
        return

    # Strip LaTeX for parsing
    clean = body
    clean = re.sub(r"\\href\{[^}]*\}\{[^}]*\}", "", clean)
    clean = re.sub(r"\\url\{[^}]*\}", "", clean)
    clean = re.sub(r"\\textit\{([^}]*)\}", r"\1", clean)
    clean = re.sub(r"\\textbf\{([^}]*)\}", r"\1", clean)
    clean = re.sub(r"\\emph\{([^}]*)\}", r"\1", clean)
    clean = re.sub(r"\\&", "&", clean)
    clean = re.sub(r"~", " ", clean)
    clean = re.sub(r"[{}]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    # APA style: Author(s) (year). Title. Journal...
    apa = re.match(
        r"^(.*?)\s*\((\d{4}(?:,\s*in press)?)\)\.\s*(.*?)$", clean, re.DOTALL
    )
    if apa:
        ref.authors = apa.group(1).strip().rstrip(",").rstrip(".")
        ref.year = apa.group(2).strip()
        _parse_title_and_journal(ref, apa.group(3).strip())
        return

    # Medical style: Author. Title. Journal year;vol:pages.
    med_match = re.match(
        r"^(.*?)\.\s+(.*?)\.\s+(.*?)\s+((?:19|20)\d{2})\s*;\s*(\d+)\s*:\s*([\d\-\u2013]+)",
        clean,
    )
    if med_match:
        ref.authors = med_match.group(1).strip()
        ref.title = med_match.group(2).strip()
        ref.journal = med_match.group(3).strip()
        ref.year = med_match.group(4)
        ref.volume = med_match.group(5)
        ref.pages = med_match.group(6).replace("\u2013", "--")
        return

    # Medical book style
    med_book = re.match(
        r"^(.*?)\.\s+(.*?)\.\s+(.*?):\s*(.*?);\s*((?:19|20)\d{2})\.",
        clean,
    )
    if med_book:
        ref.authors = med_book.group(1).strip()
        ref.title = med_book.group(2).strip()
        ref.publisher = f"{med_book.group(3).strip()}: {med_book.group(4).strip()}"
        ref.year = med_book.group(5)
        return

    # Physics style: Author, Title, Journal vol, pages (year).
    physics = re.search(r"\((\d{4})\)\s*\.?\s*$", clean)
    if physics:
        ref.year = physics.group(1)
        before_year = clean[: physics.start()].strip().rstrip(",").rstrip(".")

        author_title_split = re.match(
            r"^((?:[A-Z]\.\s*(?:[A-Z]\.\s*)?[A-Za-z\-\']+(?:\s+(?:et\s+al\.?|and\s+[A-Z]\.))?(?:,\s*)?)+),\s*(.*)",
            before_year,
        )
        if author_title_split:
            ref.authors = author_title_split.group(1).strip().rstrip(",")
            _parse_title_and_journal(ref, author_title_split.group(2).strip())
        else:
            parts = before_year.split(",", 1)
            if len(parts) == 2:
                potential_author = parts[0].strip()
                if _looks_like_author(potential_author):
                    ref.authors = potential_author
                    _parse_title_and_journal(ref, parts[1].strip())
                else:
                    _parse_title_and_journal(ref, before_year)
            else:
                _parse_title_and_journal(ref, before_year)
        return

    # Physics math style: year in middle
    mid_year = re.search(r",\s*((?:19|20)\d{2})\b", clean)
    if mid_year:
        ref.year = mid_year.group(1)
        before_year = clean[: mid_year.start()].strip()
        parts = before_year.split(",", 1)
        if len(parts) == 2:
            ref.authors = parts[0].strip()
            _parse_title_and_journal(ref, parts[1].strip())
        return

    # Fallback
    year_match = re.search(r"\b(19|20)\d{2}\b", clean)
    if year_match:
        ref.year = year_match.group(0)

    italic_match = re.search(r"\\(?:textit|emph)\{([^}]+)\}", body)
    if italic_match:
        candidate = italic_match.group(1)
        if len(candidate) > 10:
            ref.title = candidate


def _looks_like_author(text: str) -> bool:
    """Heuristic: does this look like author name(s)?"""
    if re.search(r"[A-Z]\.\s*[A-Z]", text):
        return True
    if "et al" in text.lower():
        return True
    if len(text) < 80 and re.search(r"[A-Z][a-z]+", text):
        return True
    return False


def _parse_title_and_journal(ref: Reference, text: str) -> None:
    """Split remainder into title and journal/publication info."""
    parts = re.split(r"\.\s+", text, maxsplit=1)
    if len(parts) == 2:
        ref.title = parts[0].strip()
        journal_part = parts[1].strip()

        jvp = re.match(r"^(.*?),\s*(\d+)(?:\((\d+)\))?,\s*([\d\-\u2013]+)", journal_part)
        if jvp:
            ref.journal = jvp.group(1).strip()
            ref.volume = jvp.group(2)
            ref.number = jvp.group(3) or ""
            ref.pages = jvp.group(4).replace("\u2013", "--")
        else:
            jp = re.match(r"^(.*?),\s*([\d\-\u2013]+)\s*$", journal_part)
            if jp:
                ref.journal = jp.group(1).strip()
                ref.pages = jp.group(2).replace("\u2013", "--")
            else:
                ref.journal = journal_part.rstrip(".")
    elif len(parts) == 1:
        ref.title = text.strip()

    vol_match = re.search(r",\s*(\d+),\s*([\d\-\u2013]+)\s*$", ref.title)
    if vol_match:
        ref.volume = vol_match.group(1)
        ref.pages = vol_match.group(2).replace("\u2013", "--")
        ref.title = ref.title[: vol_match.start()].strip()


# ---------------------------------------------------------------------------
# .tex file scanner
# ---------------------------------------------------------------------------


def find_bib_references(tex_path: Path) -> List[Path]:
    """Find .bib files referenced by \\bibliography{} commands in a .tex file."""
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    bib_paths = []

    for match in re.finditer(r"\\bibliography\{([^}]+)\}", text):
        names = match.group(1).split(",")
        for name in names:
            name = name.strip()
            if not name.endswith(".bib"):
                name += ".bib"
            bib_path = tex_path.parent / name
            if bib_path.exists():
                bib_paths.append(bib_path)

    return bib_paths


def extract_cite_keys(tex_path: Path) -> Set[str]:
    """Extract all citation keys used in a .tex file."""
    text = tex_path.read_text(encoding="utf-8", errors="replace")
    keys: Set[str] = set()

    for match in re.finditer(r"\\(?:cite[tp]?|nocite)\{([^}]+)\}", text):
        for key in match.group(1).split(","):
            key = key.strip()
            if key and key != "*":
                keys.add(key)

    return keys


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _title_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _merge_group(group: List[Reference]) -> Reference:
    base = next((r for r in group if r.source_format == "bibtex"), group[0])
    for other in group:
        if other is not base:
            base.merge_from(other)

    all_sources = sorted({r.source_file for r in group})
    base.source_files = all_sources
    base.source_file = all_sources[0]

    all_keys = sorted({r.cite_key for r in group})
    if len(all_keys) > 1:
        base.alternate_keys = [k for k in all_keys if k != base.cite_key]

    return base


def deduplicate(refs: List[Reference]) -> List[Reference]:
    """Two-pass deduplication: by cite_key, then by fuzzy title+year."""
    # Pass 1: group by cite_key
    key_groups: Dict[str, List[Reference]] = {}
    for ref in refs:
        key_groups.setdefault(ref.cite_key, []).append(ref)

    pass1: List[Reference] = []
    for group in key_groups.values():
        pass1.append(_merge_group(group))

    # Pass 2: group by fuzzy title + year
    title_groups: Dict[str, List[Reference]] = {}
    ungrouped: List[Reference] = []

    for ref in pass1:
        if not ref.normalized_title:
            ungrouped.append(ref)
            continue

        key = f"{ref.normalized_title}|{ref.year}"
        placed = False

        for group_key in list(title_groups.keys()):
            existing_title, existing_year = group_key.rsplit("|", 1)
            if ref.year == existing_year and _title_similarity(
                ref.normalized_title, existing_title
            ) > 0.85:
                title_groups[group_key].append(ref)
                placed = True
                break

        if not placed:
            title_groups[key] = [ref]

    merged: List[Reference] = []
    for group in title_groups.values():
        base = _merge_group(group)
        all_alt_keys: Set[str] = set()
        for r in group:
            all_alt_keys.add(r.cite_key)
            all_alt_keys.update(r.alternate_keys)
        all_alt_keys.discard(base.cite_key)
        base.alternate_keys = sorted(all_alt_keys)
        all_sources: Set[str] = set()
        for r in group:
            all_sources.update(r.source_files or [r.source_file])
        base.source_files = sorted(all_sources)
        merged.append(base)

    merged.extend(ungrouped)
    return merged


# ---------------------------------------------------------------------------
# Main extraction pipeline
# ---------------------------------------------------------------------------


def extract_all(project_root: Path) -> Tuple[List[Reference], Dict]:
    """Walk a project tree and extract all references.

    Returns:
        (references, stats)
    """
    all_refs: List[Reference] = []
    tex_files: List[Path] = []
    bib_files_seen: Set[str] = set()
    stats = {
        "tex_files_scanned": 0,
        "bib_files_scanned": 0,
        "bibitem_refs_found": 0,
        "bibtex_refs_found": 0,
        "total_before_dedup": 0,
        "total_after_dedup": 0,
        "with_doi": 0,
        "with_arxiv": 0,
        "with_title": 0,
        "papers_with_refs": {},
    }

    skip_dirs = {
        ".git", "__pycache__", "node_modules", ".devcontainer", "archive", "tools",
    }

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if fname.endswith(".tex"):
                tex_files.append(Path(root) / fname)

    for tex_path in sorted(tex_files):
        stats["tex_files_scanned"] += 1
        rel_path = tex_path.relative_to(project_root)

        bibitem_refs = parse_bibitem_block(tex_path)
        if bibitem_refs:
            all_refs.extend(bibitem_refs)
            stats["bibitem_refs_found"] += len(bibitem_refs)
            stats["papers_with_refs"][str(rel_path)] = len(bibitem_refs)

        for bib_path in find_bib_references(tex_path):
            bib_key = str(bib_path.resolve())
            if bib_key not in bib_files_seen:
                bib_files_seen.add(bib_key)
                bibtex_refs = parse_bib_file(bib_path)
                all_refs.extend(bibtex_refs)
                stats["bib_files_scanned"] += 1
                stats["bibtex_refs_found"] += len(bibtex_refs)
                rel_bib = bib_path.relative_to(project_root)
                stats["papers_with_refs"][str(rel_bib)] = len(bibtex_refs)

    # Also scan orphan .bib files
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if fname.endswith(".bib"):
                bib_path = Path(root) / fname
                bib_key = str(bib_path.resolve())
                if bib_key not in bib_files_seen:
                    bib_files_seen.add(bib_key)
                    bibtex_refs = parse_bib_file(bib_path)
                    all_refs.extend(bibtex_refs)
                    stats["bib_files_scanned"] += 1
                    stats["bibtex_refs_found"] += len(bibtex_refs)

    stats["total_before_dedup"] = len(all_refs)
    all_refs = deduplicate(all_refs)
    stats["total_after_dedup"] = len(all_refs)

    for ref in all_refs:
        if ref.doi:
            stats["with_doi"] += 1
        if ref.arxiv_id:
            stats["with_arxiv"] += 1
        if ref.title:
            stats["with_title"] += 1

    return all_refs, stats


def write_output(refs: List[Reference], stats: Dict, output_path: Path) -> None:
    """Write bibliography.json and missing_dois.json."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "metadata": {
            "total_references": stats["total_after_dedup"],
            "with_doi": stats["with_doi"],
            "with_arxiv": stats["with_arxiv"],
            "duplicates_removed": stats["total_before_dedup"] - stats["total_after_dedup"],
            "tex_files_scanned": stats["tex_files_scanned"],
            "bib_files_scanned": stats["bib_files_scanned"],
        },
        "references": [asdict(r) for r in sorted(refs, key=lambda r: r.cite_key)],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(refs)} references to {output_path}")

    # Write missing DOIs summary
    missing_doi_path = output_path.parent / "missing_dois.json"
    missing = [
        {"cite_key": r.cite_key, "title": r.title, "authors": r.authors, "year": r.year}
        for r in refs
        if not r.doi and r.title
    ]
    with open(missing_doi_path, "w", encoding="utf-8") as f:
        json.dump(missing, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(missing)} refs needing DOI resolution to {missing_doi_path}")
