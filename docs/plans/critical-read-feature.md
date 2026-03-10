# Paperscope: Critical Read Feature

**Status:** Design sketch
**Date:** 2026-03-10
**Origin:** Manual critical read of Havens et al. 2026 (Cell) exposed the gap — we did the analysis by hand and called it "paperscope-style" but never ran any tooling.

---

## Problem

Paperscope is built for auditing your own manuscripts pre-submission. There's no workflow for critically reading someone else's published paper. That's a different activity:

- You don't have the `.tex` source (just a PDF)
- You're not checking your own citations — you're evaluating their methodology
- The output is a structured critique, not a submission checklist

## What We Did Manually (the implicit spec)

1. Read the PDF
2. Identified authors, affiliations, COI disclosures
3. Looked up author history (prior papers, public positions, funding)
4. Identified the core method and what it actually measures
5. Compared the method's resolution to the question being asked
6. Checked whether complementary methods from the same ecosystem were used
7. Assessed whether conclusions were proportionate to results
8. Wrote a structured report with strengths, critical issues, and verdict

Steps 2-3 are automatable now. Steps 4-7 are where the real value is.

## Proposed Command

```bash
python3 -m paperscope critical-read paper.pdf [--depth shallow|full]
```

**Shallow** (fast, automatable): author profiling + method identification + basic flags
**Full** (interactive, needs LLM): resolution analysis + overclaiming detection + structured report

## Module Design

### 1. `analysis/author_profile.py` — Buildable Now

**Input:** Author names + affiliations (extracted from PDF or provided)
**APIs:** OpenAlex, CrossRef, Semantic Scholar
**Output:**

```json
{
  "authors": [
    {
      "name": "...",
      "institution": "...",
      "h_index": 42,
      "recent_papers": ["..."],
      "co_author_network": ["..."],
      "method_developer": true,  // flags self-validation
      "coi_flags": ["compensated testimony", "developer of core method"]
    }
  ],
  "team_assessment": {
    "self_validation_risk": "high",  // method developer using own method
    "institutional_concentration": "3/7 authors same lab",
    "prior_position": "4 authors co-authored Proximal Origin (2020)"
  }
}
```

**Key flags:**
- Author developed the method being used (self-validation)
- Multiple authors share a prior publication on the same question (position entrenchment)
- Funding/COI disclosures that are vague relative to the paper's policy implications

### 2. `analysis/method_resolution.py` — Hard but High-Value

**The core question:** Does the method have the resolving power to distinguish the hypotheses the paper claims to address?

**Approach (embedding-based):**
1. Extract method description → embed claims about what the method measures
2. Extract conclusions → embed what the paper claims to show
3. Measure semantic distance between method-capability and conclusion-scope
4. Flag when conclusions operate at a finer resolution than the method provides

**Example from Havens et al.:**
- Method measures: "genome-wide shifts in selection intensity (single K parameter)"
- Conclusion implies: "SARS-CoV-2 did not undergo laboratory manipulation"
- Gap: genome-wide ≠ site-specific; K parameter cannot detect 12-nt indels

**This is the hardest module.** Possible approaches:
- Taxonomy of measurement types (genome-wide vs site-specific, aggregate vs individual, temporal vs cross-sectional) — match method to conclusion
- Embedding similarity between method-description and conclusion-claims with a learned threshold
- LLM-assisted: extract method capabilities as structured claims, compare against conclusion claims

### 3. `analysis/missing_methods.py` — Buildable Now

**Input:** Identified methods + their ecosystem (e.g., "RELAX" → HyPhy)
**Lookup:** What other methods exist in the same ecosystem?
**Flag:** Methods from the same toolkit that would address gaps the primary method can't.

**Data source:** Method databases, package documentation, or a curated registry.

For HyPhy specifically:
- RELAX → genome-wide selection shift
- MEME → episodic positive selection at individual sites
- FEL/FUBAR → pervasive selection at individual sites
- BUSTED → gene-wide positive selection on foreground branches

If the paper uses RELAX but the question requires site-specific resolution → flag MEME/FEL as missing.

**Implementation:** This could be a simple lookup table for common ecosystems (HyPhy, BEAST, R phylogenetics, scikit-learn, etc.) or a more ambitious method-capability database.

### 4. `analysis/overclaiming.py` — Tractable NLP

**Input:** Results section text + conclusions/abstract text
**Output:** Overclaiming score + specific flagged sentences

**Hedging detection:**
- Results: "K was not significantly different from 1" (hedged)
- Conclusion: "SARS-CoV-2 shows no evidence of pre-spillover adaptation" (strong)
- Flag: conclusion drops the hedge

**Strength escalation patterns:**
- "consistent with" → "supports" → "demonstrates" → "proves"
- Track the escalation from results → discussion → abstract → title
- Flag when strength increases without new evidence

**Scope expansion:**
- Results about X (genome-wide selection) → conclusion about Y (origins debate)
- Flag when conclusions address a broader question than the results tested

## Output Format

```
═══════════════════════════════════════════
  PAPERSCOPE CRITICAL READ
  Havens et al. 2026, Cell 189, 1-14
═══════════════════════════════════════════

AUTHOR PROFILE
  ⚠ Self-validation: Kosakovsky Pond developed RELAX
  ⚠ Position entrenchment: 4 authors co-authored Proximal Origin
  ⚠ Vague COI: compensated testimony, direction unspecified

METHOD RESOLUTION
  ❌ RESOLUTION MISMATCH
     Method resolves: genome-wide selection shifts
     Conclusion requires: site-specific changes
     Gap: 12-nt indel invisible to dN/dS framework

MISSING METHODS
  ⚠ Same ecosystem (HyPhy) includes:
    - MEME (episodic site selection) — not used
    - FEL/FUBAR (pervasive site selection) — not used
    - BUSTED (gene-wide positive selection) — not used

OVERCLAIMING
  ⚠ Strength escalation:
    Results: "K not significantly different from 1" (hedged)
    Abstract: "adaptation is not a necessary precursor" (strong)
  ⚠ Scope expansion:
    Tested: genome-wide selection regime
    Implies: origins question resolved

VERDICT: Method technically sound. Conclusions exceed method resolution.
═══════════════════════════════════════════
```

## Build Priority

| Module | Difficulty | Value | Build Order |
|--------|-----------|-------|-------------|
| `author_profile.py` | Low (API lookups) | Medium | 1st |
| `missing_methods.py` | Low-Medium (registry) | High | 2nd |
| `overclaiming.py` | Medium (NLP) | High | 3rd |
| `method_resolution.py` | High (semantic) | Very High | 4th |

## Open Questions

1. **PDF text extraction:** Paperscope already has `ingest/` for this. Reuse or extend?
2. **Method registry:** Curated list vs automated discovery? Start curated, expand later.
3. **LLM integration:** The full critical-read likely needs an LLM for method-resolution analysis. How to integrate without making the tool dependent on API keys?
4. **Scope:** Is this just paperscope, or does it feed into the peer review folder system? (The Havens analysis suggests both — the tool runs the analysis, the peer review folder stores the output.)
