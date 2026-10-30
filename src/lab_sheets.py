import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DESIGN = BASE / 'data' / 'campaign' / 'campaign_design.csv'
OUT = BASE / 'data' / 'campaign' / 'lab_sheets'

TIME_COURSE_ENZYMES = {'Alcalase'}


def sample_times(duration):
    ladder = [0, 30, 60, 90, 120, 150, 180]
    times = [t for t in ladder if t < duration]
    if times[-1] != duration:
        times.append(duration)
    return times


def weigh_out_block(row):
    dry = row['SubstrateConc_gL']
    es = row['EnzymeToSubstrateRatio']
    charge = es * dry
    lines = [
        '**Weigh-out table (per litre of slurry, scale to your batch volume):**',
        '',
        f'- Substrate (dry-basis input): **{dry:.1f} g/L**',
        f'- Material moisture, measured on the day: ____ %  (wet mass = {dry:.1f} / (1 \u2212 moisture) = ____ g of wet substrate)',
        '- Deionised water: add to make 1.00 L total slurry',
        f'- **Enzyme charge = E/S \u00d7 substrate dry = {es:.2f} \u00d7 {dry:.1f} = {charge:.2f} g**',
    ]
    if row['arm'] == 'dose_sweep':
        lines.append('- \U0001f6a8 **DOSE-SWEEP RUN \u2014 enzyme charge is the design variable: MANDATORY weigh-out**')
    else:
        lines.append('- E/S = 0.02 is fixed \u2014 weigh the enzyme anyway and record the actual charge')
    lines.append('- Scale factor: \u00d7 ____  for batch volume ____ L')
    return '\n'.join(lines)


def sampling_block(row):
    if row['Enzyme'] in TIME_COURSE_ENZYMES:
        times = sample_times(row['Duration_min'])
        rows = '\n'.join(
            f'| {t:^8} |  ____ % |' for t in times
        )
        return (
            '| t (min) | DH (%) |\n|---|--:|\n' + rows
            + '\n\n' + f'- The **final row (t = {times[-1]} min) is the official FinalDH** measurement.'
            + ' Earlier rows are the optional time course that feeds ODE recalibration \u2014 take them if you can, they are the highest-value lab work.'
        )
    dur = row['Duration_min']
    return (f'- Final sample only at **t = {dur} min** \u2014 this IS the FinalDH measurement.\n'
            '- No time course required on this gap-fill run.')


def run_sheet(row, design):
    shares = material_runs(row['RawMaterial'], design)
    shared_by = len(shares) - 1
    duty = 'MANDATORY weigh-out (dose-sweep arm)' if row['arm'] == 'dose_sweep' else 'fixed 0.02, record actual charge'
    return f"""# {row['BatchID']} \u2014 {row['Enzyme']} ({row['arm']})

## Purpose
{row['note']}

## Setpoints
| pH | Temp (\u00b0C) | Duration (min) | Substrate (g/L) | E/S |
|---|---|:---:|:---:|:---:|
| {row['pH']:.2f} | {row['Temp_C']:.1f} | {row['Duration_min']} | {row['SubstrateConc_gL']:.1f} | {row['EnzymeToSubstrateRatio']:.2f} ({duty}) |

## Weigh-out (per litre of slurry)
{weigh_out_block(row)}

## pH set-up
- Target pH **{row['pH']:.2f}**; adjust with NaOH/HCl at ~40 \u00b0C while stirring, before enzyme addition.
- Record base/acid volume added and any pH drift during the run.

## Sampling plan
{sampling_block(row)}

## Assay checklist
- [ ] **FinalDH (%)** at t = {row['Duration_min']} min \u2014 record as a NUMBER (e.g. 19.5). Never \u201c4:48\u201d / \u201c0:00\u201d style entries.
- [ ] Moisture, crude protein, crude lipid, ash \u2014 **wet basis only**, per material lot (see 00_OVERVIEW.md \u2014 shared with {shared_by} other run(s)).
- [ ] Hydroxyproline / collagen \u2014 per material lot.
- [ ] ORAC (optional).

## Record into `data/campaign/measured_runs.csv`
`{row['BatchID']}`, `{row['RawMaterial']}`, `{row['Enzyme']}`, E/S={row['EnzymeToSubstrateRatio']:.2f} (actual weighed: ____), sub={row['SubstrateConc_gL']:.1f} g/L, T={row['Temp_C']:.1f}\u00b0C, pH={row['pH']:.2f}, dur={row['Duration_min']} min, FinalDH=____ %

Run `python src\\validate_measured.py` after filling, then `python -m src.run_ebm_loop`.
"""


def material_runs(material, design):
    return list(design[design['RawMaterial'] == material]['BatchID'])


def overview(design):
    material_lines = []
    for mat in sorted(design['RawMaterial'].unique()):
        runs = material_runs(mat, design)
        plural = '' if len(runs) == 1 else 's'
        material_lines.append(f'- **{mat}** \u2014 {len(runs)} run{plural}: {", ".join(runs)} \u2192 measure composition ONCE per lot, reuse across runs')
    dose = design[design['arm'] == 'dose_sweep']
    return f"""# Campaign Lab Overview \u2014 15 runs

Generated from `data/campaign/campaign_design.csv` (regenerate with `python src\\lab_sheets.py`).

## Recommended run order
1. **Dose-sweep first or grouped in one week**: {", ".join(dose['BatchID'])} \u2014 same enzyme lot, same material lot, minimises lot-to-lot variance on the dose response.
2. Remaining arms in any order; batch-level assays (not the reactions) are the throughput bottleneck.

## Material sharing \u2014 composition measured once per lot
{chr(10).join(material_lines)}

## What each arm feeds
| Arm | Runs | Purpose in the pipeline |
|---|---|---|
| gap_fill | 001\u2013007 | Bring rare enzymes to n\u22653 rows so the EBM can acquire over them |
| process_lhc | 008\u2013012 | Alcalase process-space coverage + new material lots; time courses extend the ODE kinetic bank |
| dose_sweep | 013\u2013015 | Real weighed E/S doses \u2014 the only way the model can learn a dose response |

## Key discipline reminders
- **FinalDH as a number (%)**, wet basis, never time-formatted cells.
- **Weigh EVERY enzyme charge**; only the dose arm treats E/S as a design variable, but recorded values are what the twin learns from.
- **Time-course samples are highest-value** on Alcalase runs (008\u2013015): each curve is an ODE recalibration row.

## Reagents / consumables (per batch)
- Substrate per material sharing map; NaOH & HCl for pH adjustment; deionised water.
- Enzyme (Alcalase 2.4L or equivalent; Pepsin; Flavourzyme; Kojizyme; Neutrase \u2014 blends per design).
- DH assay kit (OPA/TNBS or pH-stat), composition assay train (moisture, Kjeldahl, Soxhlet, ash), hydroxyproline assay.
- After each batch: append to `data/campaign/measured_runs.csv`, run `python src\\validate_measured.py`, then `python -m src.run_ebm_loop`.
"""


MEASURED_CSV_COLS = ["BatchID", "RawMaterial", "Enzyme", "EnzymeToSubstrateRatio",
                     "SubstrateConc_gL", "Temp_C", "pH", "Duration_min",
                     "Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
                     "Hydroxyproline_pct", "Collagen_pct", "FinalDH_pct"]


def measured_template(design):
    rows = []
    for _, r in design.iterrows():
        rows.append({
            "BatchID": r["BatchID"], "RawMaterial": r["RawMaterial"],
            "Enzyme": r["Enzyme"], "EnzymeToSubstrateRatio": r["EnzymeToSubstrateRatio"],
            "SubstrateConc_gL": r["SubstrateConc_gL"], "Temp_C": r["Temp_C"],
            "pH": r["pH"], "Duration_min": r["Duration_min"],
            "Moisture_pct": "", "CrudeProtein_pct": "", "CrudeLipid_pct": "",
            "Ash_pct": "", "Hydroxyproline_pct": "", "Collagen_pct": "",
            "FinalDH_pct": "",
        })
    return pd.DataFrame(rows, columns=MEASURED_CSV_COLS)


def main():
    design = pd.read_csv(DESIGN)
    OUT.mkdir(parents=True, exist_ok=True)
    for _, row in design.iterrows():
        (OUT / f"{row['BatchID']}.md").write_text(run_sheet(row, design), encoding='utf-8')
    (OUT / '00_OVERVIEW.md').write_text(overview(design), encoding='utf-8')
    measured_template(design).to_csv(BASE / 'data' / 'campaign' / 'measured_runs.csv', index=False)
    n = len(list(OUT.glob('*.md')))
    arms = design['arm'].value_counts().to_dict()
    print(f'Sheets: {n} files in data/campaign/lab_sheets/')
    print('Arms:', {k: int(v) for k, v in arms.items()})
    print('Template: data/campaign/measured_runs.csv (15 rows pre-filled from design)')


if __name__ == '__main__':
    main()