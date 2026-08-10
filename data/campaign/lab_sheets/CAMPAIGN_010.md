# CAMPAIGN_010 — Alcalase (process_lhc)

## Purpose
process space; material gap salmon_trimmings

## Setpoints
| pH | Temp (°C) | Duration (min) | Substrate (g/L) | E/S |
|---|---|:---:|:---:|:---:|
| 9.00 | 59.8 | 255 | 41.1 | 0.02 (fixed 0.02, record actual charge) |

## Weigh-out (per litre of slurry)
**Weigh-out table (per litre of slurry, scale to your batch volume):**

- Substrate (dry-basis input): **41.1 g/L**
- Material moisture, measured on the day: ____ %  (wet mass = 41.1 / (1 − moisture) = ____ g of wet substrate)
- Deionised water: add to make 1.00 L total slurry
- **Enzyme charge = E/S × substrate dry = 0.02 × 41.1 = 0.82 g**
- E/S = 0.02 is fixed — weigh the enzyme anyway and record the actual charge
- Scale factor: × ____  for batch volume ____ L

## pH set-up
- Target pH **9.00**; adjust with NaOH/HCl at ~40 °C while stirring, before enzyme addition.
- Record base/acid volume added and any pH drift during the run.

## Sampling plan
| t (min) | DH (%) |
|---|--:|
|    0     |  ____ % |
|    30    |  ____ % |
|    60    |  ____ % |
|    90    |  ____ % |
|   120    |  ____ % |
|   150    |  ____ % |
|   180    |  ____ % |
|   255    |  ____ % |

- The **final row (t = 255 min) is the official FinalDH** measurement. Earlier rows are the optional time course that feeds ODE recalibration — take them if you can, they are the highest-value lab work.

## Assay checklist
- [ ] **FinalDH (%)** at t = 255 min — record as a NUMBER (e.g. 19.5). Never “4:48” / “0:00” style entries.
- [ ] Moisture, crude protein, crude lipid, ash — **wet basis only**, per material lot (see 00_OVERVIEW.md — shared with 1 other run(s)).
- [ ] Hydroxyproline / collagen — per material lot.
- [ ] ORAC (optional).

## Record into `data/campaign/measured_runs.csv`
`CAMPAIGN_010`, `salmon_trimmings`, `Alcalase`, E/S=0.02 (actual weighed: ____), sub=41.1 g/L, T=59.8°C, pH=9.00, dur=255 min, FinalDH=____ %

Run `python src\validate_measured.py` after filling, then `python -m src.run_ebm_loop`.
