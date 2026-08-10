# Campaign Lab Overview — 15 runs

Generated from `data/campaign/campaign_design.csv` (regenerate with `python src\lab_sheets.py`).

## Recommended run order
1. **Dose-sweep first or grouped in one week**: CAMPAIGN_013, CAMPAIGN_014, CAMPAIGN_015 — same enzyme lot, same material lot, minimises lot-to-lot variance on the dose response.
2. Remaining arms in any order; batch-level assays (not the reactions) are the throughput bottleneck.

## Material sharing — composition measured once per lot
- **cod_frames** — 4 runs: CAMPAIGN_002, CAMPAIGN_003, CAMPAIGN_005, CAMPAIGN_009 → measure composition ONCE per lot, reuse across runs
- **cod_heads** — 1 run: CAMPAIGN_011 → measure composition ONCE per lot, reuse across runs
- **herring_byproduct** — 1 run: CAMPAIGN_012 → measure composition ONCE per lot, reuse across runs
- **salmon_frames** — 7 runs: CAMPAIGN_001, CAMPAIGN_004, CAMPAIGN_007, CAMPAIGN_008, CAMPAIGN_013, CAMPAIGN_014, CAMPAIGN_015 → measure composition ONCE per lot, reuse across runs
- **salmon_trimmings** — 2 runs: CAMPAIGN_006, CAMPAIGN_010 → measure composition ONCE per lot, reuse across runs

## What each arm feeds
| Arm | Runs | Purpose in the pipeline |
|---|---|---|
| gap_fill | 001–007 | Bring rare enzymes to n≥3 rows so the EBM can acquire over them |
| process_lhc | 008–012 | Alcalase process-space coverage + new material lots; time courses extend the ODE kinetic bank |
| dose_sweep | 013–015 | Real weighed E/S doses — the only way the model can learn a dose response |

## Key discipline reminders
- **FinalDH as a number (%)**, wet basis, never time-formatted cells.
- **Weigh EVERY enzyme charge**; only the dose arm treats E/S as a design variable, but recorded values are what the twin learns from.
- **Time-course samples are highest-value** on Alcalase runs (008–015): each curve is an ODE recalibration row.

## Reagents / consumables (per batch)
- Substrate per material sharing map; NaOH & HCl for pH adjustment; deionised water.
- Enzyme (Alcalase 2.4L or equivalent; Pepsin; Flavourzyme; Kojizyme; Neutrase — blends per design).
- DH assay kit (OPA/TNBS or pH-stat), composition assay train (moisture, Kjeldahl, Soxhlet, ash), hydroxyproline assay.
- After each batch: append to `data/campaign/measured_runs.csv`, run `python src\validate_measured.py`, then `python -m src.run_ebm_loop`.
