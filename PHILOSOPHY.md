# Philosophy: Paper-Corpus Evaluation and Two-System Methodology

## The Core Insight

No paper is self-contained.

A paper can only be evaluated against the corpus it enters: the work it cites, the work it omits, the methods it inherits, the claims it repeats, the claims it contradicts, and the field-level patterns it compresses into its own framing. A single-paper review without corpus context can catch local errors, but it cannot answer the deeper questions:

- Is the claim novel, or only locally unfamiliar?
- Does the cited literature actually support the argument?
- Are the methods adequate by the standards of this subfield?
- Is the paper an outlier, a representative example, or a symptom of a broader literature pattern?
- Are suspicious statistics paper-specific, or part of a corpus-level reporting signature?

PaperScope therefore treats "evaluate this paper" and "evaluate this corpus" as the same task at different resolutions. A paper-level critique is a local slice through a corpus map. A corpus-level review is the global context that makes paper-level critique meaningful.

## The Two-System Method

AI-assisted research works best as a two-system process, analogous to how the brain uses different modes for different cognitive demands.

**System 1 — High-dimensional reasoning (Claude Code / Opus):**
- Framework construction and theoretical synthesis
- Detecting structural analogies across distant fields
- Generating novel mathematical formalisms
- Navigating large conceptual spaces

**System 2 — Low-dimensional verification (Codex / independent review):**
- Fact-checking specific claims against literature
- Catching arithmetic errors in derivations
- Grounding abstract frameworks in concrete examples
- Detecting when "elegant" theory doesn't match data

## Why Two Systems

No single model excels at both. The failure modes are complementary:

| Mode | Strength | Failure mode |
|------|----------|-------------|
| High-D (Claude) | Finds deep structural connections | Can construct beautiful but wrong theories |
| Low-D (Codex) | Catches specific errors | Can miss the forest for the trees |

The toolchain supports both, at both paper and corpus scales:
- **Discovery tools** (harvest, ingest, embed, analysis) feed the high-D system with raw material
- **Audit tools** (verify, pre_submit, critical_read, forensic_stats) enable the low-D system to check the output
- **Review tools** (systematic_review, methodological_audit, forensic_scan, knowledge-base export) turn the corpus into the context needed to judge individual papers

## How to Tell If a Paper Is Close

A paper is ready for submission when:

1. **The math is independently verifiable.** Every derivation can be checked by a different model without context about "what we're trying to show."

2. **Citations actually support the claims.** `verify` and `pre-submit` catch ghost citations and metadata mismatches (paper exists? title/year correct? retracted?). The deeper claim-content audit — confirming a cited paper actually says what you quoted it for — is the highest-value next analysis pass; today it's a manual / model-in-the-loop step on top of the extracted text. Misattributions are the most common AI-assisted failure mode.

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

PaperScope addresses this at every stage:
1. **Extract** — pull actual citations from your LaTeX, not from model memory
2. **Resolve** — verify DOIs against CrossRef (the authoritative registry)
3. **Verify** — cross-check resolved DOIs against CrossRef metadata; catches title mismatches, year discrepancies, retractions
4. **Pre-submit** — checklist for DOI coverage, broken refs, duplicate citations, missing fields
5. **Critical read** — for external papers, runs the same checks plus method/resolution mismatch and overclaiming detection

This is the difference between "I used AI" and "I used AI responsibly."

## On Closeness to Truth

The embedding space (`embed/`) serves a specific purpose: detecting when your bibliography or review corpus has gaps, contradictions, or hidden structure.

If you claim X and your own cited literature contains evidence against X, you should know that before reviewers do. If a highly relevant paper exists that you didn't cite, you should know that too.

The tools don't judge whether your theory is correct. They ensure you haven't missed obvious evidence for or against it, and they make the field-level background visible enough that individual-paper judgments are not made in isolation. The judgment is yours.
