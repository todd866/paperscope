"""Charting schema: parses a markdown table describing the fields the
extraction agent should fill per included study, plus the rules sidebar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SchemaField:
    name: str
    type: str  # string | integer | list[string] | category | boolean | null-or-T
    notes: str = ""


@dataclass
class Schema:
    fields: list[SchemaField] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    source_path: Path | None = None

    def names(self) -> set[str]:
        return {f.name for f in self.fields}

    def validate_extraction(self, extraction: dict) -> list[str]:
        """Returns warnings; empty list = OK."""
        warnings: list[str] = []
        unknown = set(extraction) - self.names()
        if unknown:
            warnings.append(f"extra field(s) not in schema: {sorted(unknown)}")
        missing = self.names() - set(extraction)
        if missing:
            warnings.append(f"missing field(s): {sorted(missing)}")
        return warnings


def load_schema(path: str | Path) -> Schema:
    """Parse a markdown schema file. Expects a table with columns Field / Type /
    Notes and a `## Rules` section."""
    path = Path(path)
    text = path.read_text()
    schema = Schema(source_path=path)

    # Table rows: | `field` | type | notes |
    for m in re.finditer(
        r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|\s*$",
        text,
        re.M,
    ):
        schema.fields.append(
            SchemaField(name=m.group(1), type=m.group(2).strip(), notes=m.group(3).strip())
        )

    # Rules section bullets
    rules_match = re.search(r"##\s*Rules\b(.+?)(?:\n##\s|\Z)", text, re.S)
    if rules_match:
        for b in re.findall(
            r"^\s*[-*]\s+(.+?)(?=\n\s*[-*]|\n##|\Z)", rules_match.group(1), re.S | re.M
        ):
            schema.rules.append(re.sub(r"\s+", " ", b).strip())

    return schema
