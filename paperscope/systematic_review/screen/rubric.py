"""Screening rubric: a markdown document with INCLUDE / EXCLUDE / MAYBE rules,
plus the theme set that included records can be tagged with.

The rubric is intentionally human-readable markdown — agents read it directly
as the screening prompt. This module parses it into a structured object that
can be programmatically inspected and validated against decisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Rubric:
    """A parsed screening rubric."""

    review_question: str = ""
    include_rules: list[str] = field(default_factory=list)
    exclude_rules: list[str] = field(default_factory=list)
    maybe_rules: list[str] = field(default_factory=list)
    themes: dict[str, str] = field(default_factory=dict)  # {letter or id: description}
    source_path: Path | None = None

    def validate_decision(self, decision: dict) -> list[str]:
        """Check a single screening decision dict against this rubric.

        Returns a list of warning strings (empty list = no issues). Checked:
        - `decision` field is one of include / exclude / maybe
        - `themes` only contains theme IDs defined in the rubric
        - include / maybe decisions have at least one theme
        - exclude decisions have no themes
        """
        warnings: list[str] = []
        d = decision.get("decision")
        if d not in {"include", "exclude", "maybe"}:
            warnings.append(f"bad decision: {d!r}")
            return warnings
        themes = decision.get("themes") or []
        unknown = [t for t in themes if t not in self.themes]
        if unknown:
            warnings.append(f"unknown theme(s): {unknown}")
        if d in {"include", "maybe"} and not themes:
            warnings.append(f"{d} decision has no themes")
        if d == "exclude" and themes:
            warnings.append("exclude decision should not list themes")
        return warnings


def load_rubric(path: str | Path) -> Rubric:
    """Parse a markdown rubric file into a Rubric object.

    The parser is intentionally permissive — it pulls structure from the
    canonical section headings (`## INCLUDE if`, `## EXCLUDE if`, `## MAYBE if`)
    and from `**theme letter — description**` style theme list items. Anything
    else stays in markdown for the agent to read.
    """
    path = Path(path)
    text = path.read_text()
    rubric = Rubric(source_path=path)

    # Review question (first blockquote after the title)
    rq = re.search(r"^\*\*Review question:\*\*\s*(.+?)(?:\n\n|\Z)", text, re.S | re.M)
    if rq:
        rubric.review_question = re.sub(r"\s+", " ", rq.group(1)).strip()

    # Section parsing
    sections = {
        "include_rules": r"##\s*INCLUDE\s+if\b",
        "exclude_rules": r"##\s*EXCLUDE\s+if\b",
        "maybe_rules": r"##\s*MAYBE\s+if\b",
    }
    for attr, pattern in sections.items():
        m = re.search(pattern + r"(.+?)(?:\n##\s|\Z)", text, re.S)
        if not m:
            continue
        body = m.group(1)
        bullets = re.findall(r"^\s*[-*]\s+(.+?)(?=\n\s*[-*]|\n##|\Z)", body, re.S | re.M)
        cleaned = [re.sub(r"\s+", " ", b).strip() for b in bullets]
        setattr(rubric, attr, [c for c in cleaned if c])

    # Themes: lines like "- **a — early features**: ..."
    for m in re.finditer(
        r"^\s*[-*]\s*\*\*([a-z0-9]+)\s*[—\-]\s*(.+?)\*\*\s*:?\s*(.*?)$",
        text,
        re.M | re.I,
    ):
        theme_id = m.group(1).strip().lower()
        short = m.group(2).strip()
        long_desc = m.group(3).strip()
        rubric.themes[theme_id] = f"{short} — {long_desc}" if long_desc else short

    return rubric
