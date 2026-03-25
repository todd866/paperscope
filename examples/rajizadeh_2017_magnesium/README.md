# Example: Forensic Audit of Rajizadeh et al. (2017)

**Paper:** "Effect of magnesium supplementation on depression status in depressed patients with magnesium deficiency: A randomized, double-blind, placebo-controlled trial." *Nutrition* 35 (2017) 56-60.

This example demonstrates the full paperscope audit pipeline on a published paper with known data integrity issues (flagged independently by Meyerowitz-Katz on PubPeer).

## Files

- `analysis/forensic_report.pdf` -- The main output: a 6-page layman-readable report explaining every check, its result, and a full provenance table
- `analysis/forensic_report.tex` -- LaTeX source for the report
- `analysis/forensic_audit.txt` -- Raw console output from `forensic_stats.py`
- `analysis/critical_read.json` -- Raw JSON from `paperscope critical-read`
- `analysis/paperscope_report.md` -- Summary combining both pipelines
- `analysis/extracted_text.txt` -- Text extracted from the PDF

## Results

- 50 checks run
- 14 failures (mathematically impossible)
- 7 flags (suspicious)
- 29 passes
- Verdict: severe data integrity concerns

## How This Was Produced

The values in the forensic audit were manually transcribed from the paper's published tables (Tables 1-3, pages 58-59), then fed through the automated checks. The critical-read pipeline ran on text extracted from the PDF.

This is the typical workflow: a reviewer reads the paper, transcribes the summary statistics, and runs the checks. The math is automated; the data entry is manual.
