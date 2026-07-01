"""AI-agent extraction interface. Mirror of `screen.ai_screen` for charting.

The caller wires their agent SDK in; this module fixes the function shape:
extraction agent reads a record + schema, returns the extraction dict.
"""

from __future__ import annotations

from typing import Callable, Protocol

from paperscope.systematic_review.extract.schema import Schema


class Extractor(Protocol):
    def extract_record(self, record: dict, schema: Schema) -> dict:
        ...


def stub_extractor(record: dict, schema: Schema) -> dict:
    """Placeholder that returns an empty extraction. Wire your real SDK call
    into a function with the same signature and pass it to `extract_corpus`."""
    out = {"pmid": record.get("pmid", "")}
    for f in schema.fields:
        if f.name == "pmid":
            continue
        if "list" in f.type:
            out[f.name] = []
        elif f.type == "integer":
            out[f.name] = None
        elif f.type == "boolean":
            out[f.name] = False
        else:
            out[f.name] = ""
    return out


def extract_corpus(
    included: list[dict],
    schema: Schema,
    extractor: Callable[[dict, Schema], dict] = stub_extractor,
) -> list[dict]:
    """Apply `extractor` to every included record."""
    return [extractor(r, schema) for r in included]
