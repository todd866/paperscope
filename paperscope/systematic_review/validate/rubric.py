"""Friction-point rubric: the dimensions a human rates when adjudicating an
AI decision. This is the generalisation of "rate different friction points" —
each dimension is one way an AI decision can be wrong (eligibility, extraction
fidelity, claimed-vs-supported task, comparator realism, ...).

A rubric is a small YAML file so it travels with the review config:

    dimensions:
      - id: eligible
        label: Eligibility correct?
        question: AI/ML diagnostic or surveillance tool, human data, discrimination metric?
        scale: [yes, no, unsure]
      - id: extraction
        label: Extraction faithful?
        question: Does the extracted operating point match the source?
        scale: [yes, no, unsure]

If no rubric is supplied, `default_rubric()` provides a generic agree/flag pair,
so the workbook still works for a plain "do you agree with this decision?" pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Dimension:
    id: str
    label: str
    question: str = ""
    scale: list[str] = field(default_factory=lambda: ["yes", "no", "unsure"])


@dataclass
class FrictionRubric:
    """A parsed friction-point rubric: the dimensions to rate per decision."""

    dimensions: list[Dimension] = field(default_factory=list)
    source_path: Path | None = None

    def ids(self) -> list[str]:
        return [d.id for d in self.dimensions]

    def validate_rating(self, rating: dict) -> list[str]:
        """Check one human rating dict {dim_id: value} against the rubric.
        Returns warnings; empty list = OK."""
        warnings: list[str] = []
        known = set(self.ids())
        for dim_id, value in rating.items():
            if dim_id not in known:
                warnings.append(f"unknown dimension: {dim_id!r}")
                continue
            dim = next(d for d in self.dimensions if d.id == dim_id)
            if value not in dim.scale and value not in ("", None):
                warnings.append(f"{dim_id}: value {value!r} not in scale {dim.scale}")
        return warnings


def default_rubric() -> FrictionRubric:
    """A generic agree/flag rubric when the caller supplies none."""
    return FrictionRubric(
        dimensions=[
            Dimension(
                id="agree",
                label="Agree with the decision?",
                question="Do you agree with the AI decision shown?",
                scale=["yes", "no", "unsure"],
            )
        ]
    )


def load_friction_rubric(path: str | Path | None) -> FrictionRubric:
    """Load a friction rubric from YAML, or the default if path is None."""
    if path is None:
        return default_rubric()
    path = Path(path)
    data = yaml.safe_load(path.read_text()) or {}
    dims = [
        Dimension(
            id=str(d["id"]),
            label=str(d.get("label", d["id"])),
            question=str(d.get("question", "")),
            # str() each scale value: YAML 1.1 parses bare yes/no/on/off as booleans.
            scale=[str(s) for s in d.get("scale", ["yes", "no", "unsure"])],
        )
        for d in data.get("dimensions", [])
    ]
    if not dims:
        return default_rubric()
    return FrictionRubric(dimensions=dims, source_path=path)
