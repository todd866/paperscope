# Forensic statistics — worked demo

A synthetic two-page mini-paper ("The Effect of X on Y", fake authors, clearly
marked SYNTHETIC) with deliberately planted errors, plus its Table 1
transcribed into the table-mode schema. Everything here is fabricated to
exercise the checks — nothing is a real paper.

Generate the demo PDF first (generated artifacts are gitignored):

```bash
python3 examples/forensic/make_demo_paper.py    # writes demo-paper.pdf here
```

## 1. Table mode — transcribed summary statistics

`table1.json` is Table 1 typed into the schema documented in
`paperscope/analysis/forensic_report.py` (means/SDs as strings so trailing
zeros survive for decimal-place inference):

```bash
python3 -m paperscope forensic examples/forensic/table1.json
```

Expected output (the treatment mean is the classic GRIM failure — 18.72 is
unreachable by any integer sum over n = 22):

```
FAIL (2)
------------------------------------------------------------
  [grim] Q-scale / treatment  (Brown & Heathers 2017)
      FAIL: mean 18.72 x n=22 = 411.8400; nearest achievable means are 18.6818 and 18.7273
  [grimmer] Q-scale / treatment  (Anaya 2016)
      FAIL: GRIM fails first — mean 18.72 is impossible for n=22
...
7 checks: 2 impossible, 0 flagged, 5 passed, 0 undetermined
```

## 2. Text mode — statcheck-style p recalculation

Point the CLI at the PDF (or a .txt/.md); it extracts reported t/F/chi2/r/z
statistics per page and recomputes each p-value over the rounding interval of
the printed numbers:

```bash
python3 -m paperscope forensic examples/forensic/demo-paper.pdf
```

Expected output:

```
FAIL (2)
------------------------------------------------------------
  [p_recalculation] t(38) = 1.02  (Nuijten et al. 2016 (statcheck))
      FAIL: t(38) = 1.02: recomputed two-tailed p range [0.3118, 0.3165] sits entirely on the other side of alpha = .05 from reported p = .003 — decision error
  [p_recalculation] r(24) = 1.07  (Nuijten et al. 2016 (statcheck))
      FAIL: r(24) = 1.07: impossible as printed — a correlation cannot reach |r| >= 1 in a test statistic

FLAG (1)
------------------------------------------------------------
  [p_recalculation] t(38) = 2.20  (Nuijten et al. 2016 (statcheck))
      FLAG: ... reporting error, not proven impossible
...
4 checks: 2 impossible, 1 flagged, 1 passed, 0 undetermined
```

## 3. Annotated reading copy

Add `--annotate` (PDF input only) to also produce a reading copy with every
FAIL/FLAG finding highlighted on the source page it came from, each with an
"annotator's notes" commentary page:

```bash
python3 -m paperscope forensic examples/forensic/demo-paper.pdf \
    --annotate examples/forensic/demo-paper_annotated.pdf
```

```
Annotated copy: .../demo-paper_annotated.pdf | pages: 4 | notes: 3
all anchors placed cleanly.
```

## Reading the verdicts

FAIL means arithmetically impossible *as printed*: the reported numbers cannot
coexist (a GRIM-infeasible mean, an |r| ≥ 1, a p-value whose significance
decision flips when recomputed from the printed statistic). FLAG means
suspicious or inconsistent but not proven impossible — a wrong p-value that
doesn't change the significance decision, or a pattern (Carlisle) that is
merely unlikely. UNDETERMINED is never evidence of error: it means the check
could not be run (missing inputs, unparseable numbers), and a parsing problem
never hardens into an accusation. Every recomputation treats printed numbers
as rounding intervals, so honest rounding can never produce a FAIL.
