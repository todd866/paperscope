"""Embase / Ovid: import records from a manual Ovid Advanced Search export.

Embase has no clean API and Ovid caps automated bulk exports, so the workflow
is: run the line-by-line numbered search in Ovid (translated from the MEDLINE
query blocks; `.ti,ab.` field tags, `exp` for exploded subject headings), then
export the final result set as RIS or CSV. This module ingests that export.

NOT YET IMPLEMENTED — staged for when an Ovid export is in hand. The interface
is fixed; the parsing is RIS-tag-table standard.
"""

from __future__ import annotations

from pathlib import Path


def import_ris(path: str | Path) -> list[dict]:
    """Parse an Ovid RIS export into the standard record dict shape.

    Target record shape (matches `medline.harvest` output):
        {"pmid": str, "title": str, "abstract": str, "journal": str,
         "year": str, "authors": list[str], "doi": str,
         "pub_types": list[str], "mesh": list[str], "_source_db": "embase"}

    Ovid PMID is in tag `AN` (accession); DOI in `DO`; abstract in `AB`;
    title in `T1`/`TI`; authors in `AU` (one per line); journal in `JF`/`JA`.
    """
    raise NotImplementedError(
        "Ovid RIS import not yet implemented. Run the search in Ovid, export "
        "the result set as RIS, and wire this up in a follow-up commit."
    )


def import_csv(path: str | Path) -> list[dict]:
    """Parse an Ovid CSV export. Same target record shape as `import_ris`."""
    raise NotImplementedError("Ovid CSV import not yet implemented.")
