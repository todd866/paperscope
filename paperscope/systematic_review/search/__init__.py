"""Database search layer.

`medline` is a direct API harvester (NCBI E-utilities, no auth). `ovid_import`
and `ebsco_import` are file-import adapters — Embase via Ovid and CINAHL via
EBSCO are paywalled and don't have clean APIs, so the workflow is: search in
the browser, export, point the importer at the export file.

Cross-database dedup lives in `synthesise.prisma.dedup` (PMID → DOI → normalised
title) and is re-exported here for convenience.
"""

from paperscope.systematic_review.synthesise.prisma import dedup  # noqa: F401

__all__ = ["dedup"]
