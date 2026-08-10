# CAMPAIGN_012 — Alcalase (process_lhc)

## Purpose
process space; material gap herring_byproduct

## Setpoints
| pH | Temp (°C) | Duration (min) | Substrate (g/L) | E/S |
|---|---|:---:|:---:|:---:|
| 7.47 | 51.6 | 297 | 50.2 | 0.02 (fixed 0.02, record actual charge) |

## Weigh-out (per litre of slurry)
**Weigh-out table (per litre of slurry, scale to your batch volume):**

- Substrate (dry-basis input): **50.2 g/L**
- Material moisture, measured on the day: ____ %  (wet mass = 50.2 / (1 − moisture) = ____ g of wet substrate)
- Deionised water: add to make 1.00 L total slurry
- **Enzyme charge = E/S × substrate dry = 0.02 × 50.2 = 1.00 g**
- E/S = 0.02 is fixed — weigh the enzyme anyway and record the actual charge
- Scale factor: × ____  for batch volume ____ L

## pH set-up
- Target pH **7.47**; adjust with NaOH/HCl at ~40 °C while stirring, before enzyme addition.
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
|   297    |  ____ % |

- The **final row (t = 297 min) is the official FinalDH** measurement. Earlier rows are the optional time course that feeds ODE recalibration — take them if you can, they are the highest-value lab work.

## Assay checklist
- [ ] **FinalDH (%)** at t = 297 min — record as a NUMBER (e.g. 19.5). Never “4:48” / “0:00” style entries.
- [ ] Moisture, crude protein, crude lipid, ash — **wet basis only**, per material lot (see 00_OVERVIEW.md — shared with 0 other run(s)).
- [ ] Hydroxyproline / collagen — per material lot.
- [ ] ORAC (optional).

## Record into `data/campaign/measured_runs.csv`
`CAMPAIGN_012`, `herring_byproduct`, `Alcalase`, E/S=0.02 (actual weighed: ____), sub=50.2 g/L, T=51.6°C, pH=7.47, dur=297 min, FinalDH=____ %

Run `python src\validate_measured.py` after filling, then `python -m src.run_ebm_loop`.
