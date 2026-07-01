"""CINAHL / EBSCO: import records from a manual EBSCOhost export.

CINAHL via EBSCO has no clean API. Workflow: translate the query into CINAHL
syntax (`MH` headings, `+` explode, `TI`/`AB` field tags), run via OpenAthens,
export. This module ingests the RIS export.

NOT YET IMPLEMENTED — staged for when an EBSCO export is in hand.
"""

from __future__ import annotations

from pathlib import Path


def import_ris(path: str | Path) -> list[dict]:
    """Parse an EBSCO RIS export into the standard record dict shape.

    Target record shape matches `medline.harvest` plus `_source_db: "cinahl"`.
    """
    raise NotImplementedError(
        "EBSCO RIS import not yet implemented. Run the CINAHL search via "
        "EBSCOhost, export as RIS, then wire this up."
    )
