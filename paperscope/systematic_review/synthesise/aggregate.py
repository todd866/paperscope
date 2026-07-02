"""Generic aggregator: charted JSONL → synthesis tables.

Mechanical aggregation only — the *interpretive* narrative lives in a
human-written SYNTHESIS.md on top of these tables. The four aggregation types
below are declared in `AggregationConfig`; this module reads that config and
applies them.

## Aggregation types

### `list_counters`
Frequency Counter over a list-of-strings field (e.g. `warning_indicators`,
`confounders_named`). Spec:

    {
      "field": "warning_indicators", # required: source field name
      "name": "warning_indicators_top40", # output key (default: <field>_top<top_n>)
      "top_n": 40,                    # optional: most-common N; null = full dict
      "drop_values": [...],           # optional: normalised values to skip
                                      # (e.g. drop the index topic from
                                      # a confounders list)
      "drop_count_name": "confounders_index_labels_dropped",  # optional:
                                      # emits the drop count under this key
    }

### `scalar_counters`
Frequency Counter over a single-value field (e.g. `study_design`, `country`).
Spec:

    {
      "field": "country",
      "name": "countries_top15",
      "top_n": 15,                    # optional
      "drop_empty": true,             # skip empty strings
      "normalize": false,             # lowercase + collapse whitespace; default off
      "default": "uncharted",         # value used when field is missing/empty
                                      # (e.g. "uncharted" for model_based_forecast)
    }

### `text_collections`
Collect non-empty string values with companion fields (e.g. lead-time detail
rows, impact-summary texts). Spec:

    {
      "field": "catchment_breakdown",
      "name": "region_breakdowns",
      "include_fields": ["pmid", "country", "study_design", "relevance_tier"],
                                      # source fields to carry along
      "rename_fields": {"relevance_tier": "tier",
                        "study_design": "design"},  # optional output renames
      "text_key": "text",             # output key for the field's value; default "text"
    }

### `numeric_extractors`
Regex-extract numeric values (with optional unit conversion) from a free-text
field, summarise. Two known limitations inherited from the source review
pipeline, kept for regression equivalence and flagged in-line:

- `median_of_reported` uses the *upper-middle* convention for even-length
  inputs (returns `values[len(v)//2]`), not the statistical median.
- `n_studies_with_figure` counts rows with non-empty source text, *including*
  rows where no numeric value was actually extracted.

A future correctness pass should fix both — in this module and in the source
pipeline together, so the regression remains meaningful.

Spec:

    {
      "field": "warning_lead_time",
      "name": "lead_time",            # emits <name> (summary) AND <name>_detail
      "units": {                       # named regex per unit; capture-group 1 = number
        "hours": "(\\d+(?:\\.\\d+)?)\\s*(?:hours?|hrs?|h\\b)",
        "days":  "(\\d+(?:\\.\\d+)?)\\s*(?:days?|d\\b)",
      },
      "convert_to": "hours",           # all values normalised to this unit
      "conversions": {"days": 24},     # multipliers from source unit → convert_to
      "band": [6, 48],                 # emits "values_in_6_to_48_band" count
      "detail_fields": ["pmid", "country", "study_design", "relevance_tier"],
      "detail_rename": {"relevance_tier": "tier", "study_design": "design"},
      "detail_text_key": "text",
    }
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from paperscope.systematic_review.config import AggregationConfig


# ---- utilities -------------------------------------------------------------


def _norm(s: Any) -> str:
    """Normalise: stringify, collapse whitespace, lowercase, strip."""
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _project(row: dict, fields: list[str], rename: dict[str, str] | None = None) -> dict:
    """Pull selected fields out of a row, optionally renaming output keys."""
    rename = rename or {}
    return {rename.get(f, f): row.get(f, "") for f in fields}


# ---- aggregation handlers --------------------------------------------------


def _list_counter(rows: list[dict], spec: dict) -> dict[str, Any]:
    field_name = spec["field"]
    top_n = spec.get("top_n")
    out_name = spec.get("name", f"{field_name}_top{top_n if top_n else 'all'}")
    drop_values = {_norm(v) for v in (spec.get("drop_values") or [])}

    counter: Counter[str] = Counter()
    dropped = 0
    for r in rows:
        for item in r.get(field_name) or []:
            n = _norm(item)
            if not n:
                continue
            if n in drop_values:
                dropped += 1
                continue
            counter[n] += 1

    if top_n is not None:
        # Return list-of-lists (not list-of-tuples) so JSON round-trips
        # equal regardless of whether the caller compares pre- or post-serialisation.
        result: Any = [[k, v] for k, v in counter.most_common(top_n)]
    else:
        result = dict(counter)

    out: dict[str, Any] = {out_name: result}
    if drop_values:
        drop_key = spec.get("drop_count_name", f"{out_name}_dropped")
        out[drop_key] = dropped
    return out


def _scalar_counter(rows: list[dict], spec: dict) -> dict[str, Any]:
    field_name = spec["field"]
    out_name = spec.get("name", field_name)
    top_n = spec.get("top_n")
    drop_empty = spec.get("drop_empty", False)
    normalize = spec.get("normalize", False)
    default = spec.get("default")

    counter: Counter[Any] = Counter()
    for r in rows:
        v = r.get(field_name)
        if isinstance(v, str):
            v = v.strip()
        if v is None or v == "":
            if default is not None:
                counter[default] += 1
            elif not drop_empty:
                counter[v if v is not None else ""] += 1
            continue
        counter[_norm(v) if normalize else v] += 1

    if top_n is not None:
        result: Any = [[k, v] for k, v in counter.most_common(top_n)]
    else:
        result = dict(counter)
    return {out_name: result}


def _text_collection(rows: list[dict], spec: dict) -> dict[str, Any]:
    field_name = spec["field"]
    out_name = spec.get("name", f"{field_name}_texts")
    include = spec.get("include_fields") or ["pmid", "relevance_tier"]
    rename = spec.get("rename_fields") or {}
    text_key = spec.get("text_key", "text")

    out_list: list[dict] = []
    for r in rows:
        v = r.get(field_name)
        if isinstance(v, str) and v.strip():
            row = _project(r, include, rename)
            row[text_key] = v
            out_list.append(row)
    return {out_name: out_list}


def _numeric_extractor(rows: list[dict], spec: dict) -> dict[str, Any]:
    field_name = spec["field"]
    out_name = spec.get("name", f"{field_name}_summary")
    units: dict[str, str] = spec.get("units") or {}
    convert_to = spec.get("convert_to")
    conversions: dict[str, float] = spec.get("conversions") or {}
    detail_fields = spec.get("detail_fields") or [
        "pmid",
        "country",
        "study_design",
        "relevance_tier",
    ]
    detail_rename = spec.get("detail_rename") or {}
    detail_text_key = spec.get("detail_text_key", "text")

    values: list[float] = []
    detail: list[dict] = []
    for r in rows:
        text = r.get(field_name) or ""
        if not text.strip():
            continue
        for unit_name, pattern in units.items():
            for m in re.finditer(pattern, text, re.I):
                try:
                    raw = float(m.group(1))
                except (ValueError, IndexError):
                    continue
                if convert_to and unit_name != convert_to and unit_name in conversions:
                    raw = raw * conversions[unit_name]
                values.append(raw)
        row = _project(r, detail_fields, detail_rename)
        row[detail_text_key] = text
        detail.append(row)

    values_sorted = sorted(values)
    summary: dict[str, Any] = {
        # NOTE (inherited from source pipeline, kept for regression equivalence):
        # counts pmids whose source field had non-empty text — including rows
        # where the regex found no parseable number. A future "correctness
        # sweep" should split this into n_with_text vs n_with_extracted_value.
        "n_studies_with_figure": len({d.get("pmid") for d in detail}),
        "n_extracted_values": len(values_sorted),
        "min": values_sorted[0] if values_sorted else None,
        "max": values_sorted[-1] if values_sorted else None,
        # NOTE (inherited): upper-middle convention — for even-length inputs
        # returns the upper of the two middles, not the statistical median
        # (which would average them). Matches the source pipeline; revisit
        # together when correcting that one.
        "median_of_reported": (
            values_sorted[len(values_sorted) // 2] if values_sorted else None
        ),
    }
    band = spec.get("band")
    if band:
        lo, hi = band
        summary[f"values_in_{lo}_to_{hi}_band"] = sum(
            1 for v in values_sorted if lo <= v <= hi
        )
    return {out_name: summary, f"{out_name}_detail": detail}


# ---- entry point -----------------------------------------------------------


def aggregate(rows: list[dict], config: AggregationConfig) -> dict[str, Any]:
    """Run all configured aggregations over the rows.

    Returns a dict keyed by the configured output names, plus `corpus_n`. The
    structure is fully determined by the AggregationConfig — this function has
    no review-specific logic.
    """
    out: dict[str, Any] = {"corpus_n": len(rows)}
    for spec in config.list_counters:
        out.update(_list_counter(rows, spec))
    for spec in config.scalar_counters:
        out.update(_scalar_counter(rows, spec))
    for spec in config.text_collections:
        out.update(_text_collection(rows, spec))
    for spec in config.numeric_extractors:
        out.update(_numeric_extractor(rows, spec))
    return out
