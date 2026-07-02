"""Systematic-review pipeline for paperscope.

A generalised, AI-agent-native port of the JBI / PRISMA-ScR scoping-review
pipeline: harvest → screen → extract → synthesise, with a human-in-the-loop
audit layer. Originally extracted from a working scoping review (May 2026);
generalised so the same code serves any review whose protocol (rubric + schema +
aggregation config) is supplied as data.

See `docs/systematic-review.md` for the full design + roadmap.
"""

from paperscope.systematic_review.config import ReviewConfig
from paperscope.systematic_review.records import load_jsonl, iter_jsonl, dump_jsonl

__all__ = ["ReviewConfig", "load_jsonl", "iter_jsonl", "dump_jsonl"]
