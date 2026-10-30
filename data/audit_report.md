# Data Audit Report

Generated: 2026-08-09 23:25

## Scope decisions applied

- Enzymatic hydrolysis only; 5 non-enzymatic rows (E/S=0) and 2 physically impossible DH rows dropped.
- Main Batch table is authoritative: curves truncated to declared Duration; FinalDH := curve value at Duration.
- DH domain recalibrated to enzymatic ceiling (~50%); no synthetic capping.
- Bioactivity reduced to ORAC + PeptideYield_pct; all IC50 columns excluded (unit/protocol anomalies).

## Drops

| BatchID | Reason |
|---|---|
| BATCH_022 | physically impossible DH for enzymatic hydrolysis |
| BATCH_023 | non-enzymatic process (E/S = 0) |
| BATCH_024 | physically impossible DH for enzymatic hydrolysis |
| BATCH_025 | non-enzymatic process (E/S = 0) |
| BATCH_026 | dry-basis composition (protein+lipid+ash ~99%) in wet-basis file; no verifiable wet-basis value |
| BATCH_027 | dry-basis composition (protein+lipid+ash ~99%) in wet-basis file; no verifiable wet-basis value |
| BATCH_038 | non-enzymatic process (E/S = 0) |
| BATCH_039 | non-enzymatic process (E/S = 0) |
| BATCH_040 | non-enzymatic process (E/S = 0) |

## FinalDH reconciliation (Main table vs curve at Duration)

| BatchID | Action | Detail |
|---|---|---|
| BATCH_004 | recompute | FinalDH 21.0 -> 19.5 (= curve at Duration 120 min) |
| BATCH_009 | keep | no curve point at declared Duration 720 min (curve ends at 300); main FinalDH trusted |
| BATCH_011 | recompute | FinalDH 6.65 -> 5.8 (= curve at Duration 60 min) |
| BATCH_033 | recompute | FinalDH 14.98 -> 13.8 (= curve at Duration 120 min) |
| BATCH_034 | recompute | FinalDH 4.94 -> 4.7 (= curve at Duration 120 min) |
| BATCH_036 | recompute | FinalDH 12.47 -> 12.3 (= curve at Duration 120 min) |

## Time-course truncation

| BatchID | Action | Detail |
|---|---|---|
| BATCH_001 | truncate | removed 8 points beyond declared Duration 120 min |
| BATCH_004 | truncate | removed 8 points beyond declared Duration 120 min |
| BATCH_011 | truncate | removed 11 points beyond declared Duration 60 min |
| BATCH_033 | truncate | removed 8 points beyond declared Duration 120 min |
| BATCH_034 | truncate | removed 8 points beyond declared Duration 120 min |
| BATCH_036 | truncate | removed 8 points beyond declared Duration 120 min |

## Enzyme dose recode

| Action | Detail |
|---|---|
| recode | recorded E/S inconsistent with measured kinetics (per-curve activity probe: MSE 21.99 -> 0.044 with near-constant effective dose); declared lab practice: constant enzyme-to-substrate ratio. Old distinct values [np.float64(0.0015), np.float64(0.002), np.float64(0.01), np.float64(0.015), np.float64(0.06), np.float64(0.13), np.float64(0.3)] -> 0.02 for all rows. |

Consequences: `EnzymeToSubstrateRatio` is now constant (no dose-response information);
`E0_gL` varies only via `S0_gL`. E/S is removed from the EBM acquisition space.
The Phase-5 campaign must include a weighed-E/S arm to restore identifiability.

## Coverage after cleaning

- Main Batch rows: **31**
- Time-course curves: **7** (54 points)
- Bioactivity rows: **31**

## Data-quality checks

- Missing values in Main (kept rows, model columns): **0**
- Missing values in Time-Course: **0**
- Missing values in Bioactivity: **0**
- FinalDH range of kept rows: 0.3% – 50.0%
- Curve grids: points at 15-min spacing truncated at Duration; BATCH_009 curve kept to 300 min (Duration 720).
