# CAMPAIGN_003 — Alcalase+Kojizyme (gap_fill)

## Purpose
raise Alcalase+Kojizyme rows to n>=3

## Setpoints
| pH | Temp (°C) | Duration (min) | Substrate (g/L) | E/S |
|---|---|:---:|:---:|:---:|
| 7.07 | 57.9 | 246 | 50.0 | 0.02 (fixed 0.02, record actual charge) |

## Weigh-out (per litre of slurry)
**Weigh-out table (per litre of slurry, scale to your batch volume):**

- Substrate (dry-basis input): **50.0 g/L**
- Material moisture, measured on the day: ____ %  (wet mass = 50.0 / (1 − moisture) = ____ g of wet substrate)
- Deionised water: add to make 1.00 L total slurry
- **Enzyme charge = E/S × substrate dry = 0.02 × 50.0 = 1.00 g**
- E/S = 0.02 is fixed — weigh the enzyme anyway and record the actual charge
- Scale factor: × ____  for batch volume ____ L

## pH set-up
- Target pH **7.07**; adjust with NaOH/HCl at ~40 °C while stirring, before enzyme addition.
- Record base/acid volume added and any pH drift during the run.

## Sampling plan
- Final sample only at **t = 246 min** — this IS the FinalDH measurement.
- No time course required on this gap-fill run.

## Assay checklist
- [ ] **FinalDH (%)** at t = 246 min — record as a NUMBER (e.g. 19.5). Never “4:48” / “0:00” style entries.
- [ ] Moisture, crude protein, crude lipid, ash — **wet basis only**, per material lot (see 00_OVERVIEW.md — shared with 3 other run(s)).
- [ ] Hydroxyproline / collagen — per material lot.
- [ ] ORAC (optional).

## Record into `data/campaign/measured_runs.csv`
`CAMPAIGN_003`, `cod_frames`, `Alcalase+Kojizyme`, E/S=0.02 (actual weighed: ____), sub=50.0 g/L, T=57.9°C, pH=7.07, dur=246 min, FinalDH=____ %

Run `python src\validate_measured.py` after filling, then `python -m src.run_ebm_loop`.
