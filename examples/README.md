# Forensic Statistics Examples

Worked examples comparing Paperscope's automated forensic checks against
published expert analyses by [Gideon Meyerowitz-Katz](https://pubpeer.com/)
and other forensic statisticians.

Each example is a self-contained Python script that:

1. **Transcribes** the summary statistics from a published paper
2. **Runs** Paperscope's forensic checks on them
3. **Compares** the results to the expert's published findings
4. **Explains** how each check works and what it means

## Examples

| # | Script | Paper | Expert | Key findings | Agreement |
|---|--------|-------|--------|--------------|-----------|
| 1 | `01_rajizadeh_magnesium.py` | Rajizadeh et al., Nutrition (2017) | Meyerowitz-Katz | GRIM failures, impossible correlation, arithmetic errors | 5/6 confirmed |
| 2 | `02_haghighian_ala.py` | Haghighian et al., Fertil Steril (2015) | Meyerowitz-Katz | 16/18 GRIM failures, duplicate ANCOVA p-values, d>2 | 4/4 confirmed |
| 3 | `03_fallah_zinc.py` | Fallah et al., Nutrition (2015) | Meyerowitz-Katz | p-value off by 6 orders of magnitude, count inconsistencies | 6/6 confirmed |
| 4 | `04_azhar_omega3.py` | Azhar et al., J Affect Disord (2026) | Plöderl, Hussey, Cristea, Meyerowitz-Katz | d=6.04, d up to 21, table discrepancies, frozen p-values | 6/6 confirmed |

## Running

```bash
cd paperscope/
PYTHONPATH=. python3 examples/01_rajizadeh_magnesium.py
PYTHONPATH=. python3 examples/02_haghighian_ala.py
PYTHONPATH=. python3 examples/03_fallah_zinc.py
PYTHONPATH=. python3 examples/04_azhar_omega3.py
```

## Aggregate results

Across 4 examples comparing against expert forensic analyses:
- **21 of 22 expert findings confirmed** (95.5%)
- **1 numeric discrepancy** (Carlisle p-value formula difference, Example 01)
- **Multiple new findings** not in the original expert analyses (DEBIT, extended GRIM)

## How to add a new example

1. Find a paper with a published forensic analysis (PubPeer, blog post, etc.)
2. Transcribe the summary statistics from the paper's tables
3. Run the relevant Paperscope checks
4. Compare results to the expert's findings
5. Document agreement and any discrepancies

## Note on data entry

All values are manually transcribed from the published papers. This is the
same workflow a reviewer would use. Automated PDF table extraction is a
separate capability not used here.
