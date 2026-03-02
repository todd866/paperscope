# Philosophy: Two-System Methodology

## The Core Insight

AI-assisted research works best as a two-system process, analogous to how the brain uses different modes for different cognitive demands.

**System 1 — High-dimensional reasoning (Claude Opus 4.5):**
- Framework construction and theoretical synthesis
- Detecting structural analogies across distant fields
- Generating novel mathematical formalisms
- Navigating large conceptual spaces

**System 2 — Low-dimensional verification (GPT 5.2 Pro):**
- Fact-checking specific claims against literature
- Catching arithmetic errors in derivations
- Grounding abstract frameworks in concrete examples
- Detecting when "elegant" theory doesn't match data

## Why Two Systems

No single model excels at both. The failure modes are complementary:

| Mode | Strength | Failure mode |
|------|----------|-------------|
| High-D (Opus) | Finds deep structural connections | Can construct beautiful but wrong theories |
| Low-D (GPT) | Catches specific errors | Can miss the forest for the trees |

The toolchain supports both:
- **Discovery tools** (harvest, embed, query) feed the high-D system with raw material
- **Audit tools** (verify, pre_submit, audit_usage) enable the low-D system to check the output

## How to Tell If a Paper Is Close

A paper is ready for submission when:

1. **The math is independently verifiable.** Every derivation can be checked by a different model without context about "what we're trying to show."

2. **Citations actually support the claims.** The audit tool (`audit_usage.py`) compares what you cited a paper for against what that paper actually says. Misattributions are the most common AI-assisted failure mode.

3. **The framework survives hostile reading.** Give the paper to a model with the prompt "find everything wrong with this" — not "improve this." The distinction matters.

4. **Concrete predictions exist.** If the paper makes no testable predictions, it's philosophy, not science. Philosophy is fine — but submit to philosophy journals.

## Honest Attribution

This research program uses AI extensively and says so explicitly. Every paper includes a workflow statement describing which tools were used and how.

Why honesty matters:
- **Reproducibility.** If someone can't replicate your results because they don't know you used AI, that's a methodological gap.
- **Precedent.** The field needs examples of honest AI attribution. Being early and transparent creates the norm.
- **Defense.** If reviewers later discover undisclosed AI use, the paper is retracted. If you disclosed it upfront, the work stands on its merits.

## The Bibliography Problem

AI-assisted writing has a specific failure mode with citations: models generate plausible-sounding references that don't exist, or cite real papers for claims they don't make.

Paperscope addresses this at every stage:
1. **Extract** — pull actual citations from your LaTeX, not from model memory
2. **Resolve** — verify DOIs against CrossRef (the authoritative registry)
3. **Verify** — cross-check your citation claims against the actual paper content
4. **Audit** — before submission, confirm every cited claim matches the source

This is the difference between "I used AI" and "I used AI responsibly."

## On Closeness to Truth

The embedding space (`embed/`) serves a specific purpose: detecting when your bibliography has gaps or contradictions.

If you claim X and your own cited literature contains evidence against X, you should know that before reviewers do. If a highly relevant paper exists that you didn't cite, you should know that too.

The tools don't judge whether your theory is correct. They ensure you haven't missed obvious evidence for or against it. The judgment is yours.
