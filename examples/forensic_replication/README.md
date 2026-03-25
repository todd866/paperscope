# Forensic Replication Studies

Validation of Paperscope's forensic statistics module against published
expert analyses by [Gideon Meyerowitz-Katz](https://gidmk.substack.com/)
and other forensic statisticians.

Each case is a self-contained directory with:
- `analysis.py` — runs Paperscope's forensic checks on transcribed table data
- Comparison against the expert's published findings (PubPeer, blog, etc.)
- Explanation of how each check works

## Cases

| Dir | Paper | Expert source | Key findings | Agreement |
|-----|-------|---------------|--------------|-----------|
| `rajizadeh_2017/` | Rajizadeh et al., Nutrition (2017) | [PubPeer](https://pubpeer.com/publications/AE40ABD7018121884545ECDD2A2C43) | GRIM failures, impossible correlation, arithmetic errors | 5/6 |
| `haghighian_2015/` | Haghighian et al., Fertil Steril (2015) | [PubPeer](https://pubpeer.com/publications/AE40ABD7018121884545ECDD2A2C43) + ASRM EoC | 16/18 GRIM failures, duplicate ANCOVA p-values, d>2 | 4/4 |
| `fallah_2015/` | Fallah et al., Nutrition (2015) | [PubPeer](https://pubpeer.com/publications/26429655) | p-value off by 10^6, count inconsistencies, cross-table mismatch | 6/6 |
| `azhar_2026/` | Azhar et al., J Affect Disord (2026) | [PubPeer](https://pubpeer.com/publications/799F60D117E44BAEE391AC93A216D2) (4 commenters) | d=6.04, d up to 21, table discrepancies, frozen p-values | 6/6 |

## Running

```bash
cd paperscope/
PYTHONPATH=. python3 examples/forensic_replication/rajizadeh_2017/analysis.py
PYTHONPATH=. python3 examples/forensic_replication/haghighian_2015/analysis.py
PYTHONPATH=. python3 examples/forensic_replication/fallah_2015/analysis.py
PYTHONPATH=. python3 examples/forensic_replication/azhar_2026/analysis.py
```

## Aggregate

Across 4 cases comparing against expert forensic analyses:
- **21 of 22 expert findings confirmed** (95.5%)
- **1 unable to replicate** (Carlisle p-value, rajizadeh_2017 — likely a different set of input p-values; see [note in analysis](rajizadeh_2017/analysis.py))
- **Multiple new findings** not in the original expert analyses (DEBIT, extended GRIM)

## Adding a new case

```
examples/forensic_replication/
└── authorname_year/
    ├── analysis.py           # forensic checks + scorecard
    └── pubpeer_comparison.md # optional: detailed comparison notes
```

1. Create a directory named `firstauthor_year/`
2. Transcribe summary statistics from the paper's tables into `analysis.py`
3. Run Paperscope checks and compare against the expert's published findings
4. Document agreement, discrepancies, and any new findings Paperscope catches

All values are manually transcribed from published papers — the same workflow
a reviewer would use.
