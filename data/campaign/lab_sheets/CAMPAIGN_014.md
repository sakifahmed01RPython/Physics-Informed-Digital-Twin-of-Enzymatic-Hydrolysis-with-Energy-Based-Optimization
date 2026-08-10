# CAMPAIGN_014 — Alcalase (dose_sweep)

## Purpose
weighed enzyme charge E/S=0.04; restores dose identifiability

## Setpoints
| pH | Temp (°C) | Duration (min) | Substrate (g/L) | E/S |
|---|---|:---:|:---:|:---:|
| 8.29 | 55.5 | 120 | 50.0 | 0.04 (MANDATORY weigh-out (dose-sweep arm)) |

## Weigh-out (per litre of slurry)
**Weigh-out table (per litre of slurry, scale to your batch volume):**

- Substrate (dry-basis input): **50.0 g/L**
- Material moisture, measured on the day: ____ %  (wet mass = 50.0 / (1 − moisture) = ____ g of wet substrate)
- Deionised water: add to make 1.00 L total slurry
- **Enzyme charge = E/S × substrate dry = 0.04 × 50.0 = 2.00 g**
- 🚨 **DOSE-SWEEP RUN — enzyme charge is the design variable: MANDATORY weigh-out**
- Scale factor: × ____  for batch volume ____ L

## pH set-up
- Target pH **8.29**; adjust with NaOH/HCl at ~40 °C while stirring, before enzyme addition.
- Record base/acid volume added and any pH drift during the run.

## Sampling plan
| t (min) | DH (%) |
|---|--:|
|    0     |  ____ % |
|    30    |  ____ % |
|    60    |  ____ % |
|    90    |  ____ % |
|   120    |  ____ % |

- The **final row (t = 120 min) is the official FinalDH** measurement. Earlier rows are the optional time course that feeds ODE recalibration — take them if you can, they are the highest-value lab work.

## Assay checklist
- [ ] **FinalDH (%)** at t = 120 min — record as a NUMBER (e.g. 19.5). Never “4:48” / “0:00” style entries.
- [ ] Moisture, crude protein, crude lipid, ash — **wet basis only**, per material lot (see 00_OVERVIEW.md — shared with 6 other run(s)).
- [ ] Hydroxyproline / collagen — per material lot.
- [ ] ORAC (optional).

## Record into `data/campaign/measured_runs.csv`
`CAMPAIGN_014`, `salmon_frames`, `Alcalase`, E/S=0.04 (actual weighed: ____), sub=50.0 g/L, T=55.5°C, pH=8.29, dur=120 min, FinalDH=____ %

Run `python src\validate_measured.py` after filling, then `python -m src.run_ebm_loop`.
