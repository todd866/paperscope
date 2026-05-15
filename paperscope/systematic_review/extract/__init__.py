"""Data charting (extraction) layer — the same shape as screening.

A charting schema describes the fields to extract from each included paper. An
agent applies the schema to title+abstract (and later, to full text) and emits
one extraction dict per study. Same human-audit principle as screening.
"""

from paperscope.systematic_review.extract.schema import Schema, load_schema

__all__ = ["Schema", "load_schema"]
