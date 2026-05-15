"""Title/abstract screening.

The screening method of record is **AI-agent screening against a markdown
rubric + human audit on a sample**. The AI orchestration belongs to whatever
agent SDK the caller uses (Anthropic SDK, OpenAI SDK, etc.) — this package
defines the rubric format, the decision JSONL contract, and the audit helpers,
not the LLM client.
"""

from paperscope.systematic_review.screen.rubric import Rubric, load_rubric

__all__ = ["Rubric", "load_rubric"]
