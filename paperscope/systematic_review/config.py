"""Review configuration: PCC, search strategy, screening rubric, charting schema, aggregations.

A ReviewConfig is the single declarative artefact that defines a review's
*protocol*. Everything in the pipeline reads from it; nothing is hardcoded to a
particular review's question or schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PCC:
    """Population, Concept, Context — JBI's scoping-review framing."""

    population: str
    concept: str
    context: str = ""


@dataclass
class SearchConfig:
    """Database search configuration.

    `query_blocks` holds named PubMed-syntax fragments that database adapters
    translate into their own syntax (Ovid/Embase, EBSCO/CINAHL). MEDLINE uses
    them directly. `filters` is appended to the full Boolean.
    """

    databases: list[str] = field(default_factory=list)
    query_blocks: dict[str, str] = field(default_factory=dict)
    full_query: str = ""
    filters: str = ""
    date_range: list[int] = field(default_factory=lambda: [2000, 2026])


@dataclass
class AggregationConfig:
    """Declarative aggregations from extraction.jsonl → synthesis-tables.json.

    Four aggregation types — each entry is a dict with the spec for one output
    table. See `synthesise.aggregate` for the spec schemas.
    """

    list_counters: list[dict[str, Any]] = field(default_factory=list)
    scalar_counters: list[dict[str, Any]] = field(default_factory=list)
    text_collections: list[dict[str, Any]] = field(default_factory=list)
    numeric_extractors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReviewConfig:
    """The full review protocol — loaded from a single YAML file."""

    name: str
    pcc: PCC
    search: SearchConfig = field(default_factory=SearchConfig)
    aggregation: AggregationConfig = field(default_factory=AggregationConfig)
    rubric_path: Path | None = None
    schema_path: Path | None = None
    corpus_dir: Path = field(default_factory=lambda: Path("corpus"))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ReviewConfig":
        """Load a ReviewConfig from a YAML file. Paths in the YAML are resolved
        relative to the YAML file's parent directory."""
        path = Path(path).resolve()
        data = yaml.safe_load(path.read_text())
        base = path.parent

        def _abs(p: str | None) -> Path | None:
            return (base / p).resolve() if p else None

        return cls(
            name=data["name"],
            pcc=PCC(**data["pcc"]),
            search=SearchConfig(**data.get("search", {})),
            aggregation=AggregationConfig(**data.get("aggregation", {})),
            rubric_path=_abs(data.get("rubric_path")),
            schema_path=_abs(data.get("schema_path")),
            corpus_dir=(base / data.get("corpus_dir", "corpus")).resolve(),
        )
