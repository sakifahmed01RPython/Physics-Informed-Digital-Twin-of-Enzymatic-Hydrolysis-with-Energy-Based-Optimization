import sys
from pathlib import Path

import pandas as pd

CAMPAIGN_DIR = Path(__file__).resolve().parents[1] / 'data' / 'campaign'
MEASURED = CAMPAIGN_DIR / 'measured_runs.csv'
DESIGN = CAMPAIGN_DIR / 'campaign_design.csv'

REQUIRED = ["BatchID", "RawMaterial", "Enzyme", "EnzymeToSubstrateRatio",
            "SubstrateConc_gL", "Temp_C", "pH", "Duration_min",
            "Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
            "Hydroxyproline_pct", "Collagen_pct", "FinalDH_pct"]

ALLOWED_ES = {0.01, 0.02, 0.04, 0.06}

TOL = {"pH": 0.5, "Temp_C": 2.0, "Duration_min": 0.15, "SubstrateConc_gL": 0.20}


def check(path=MEASURED):
    problems = []
    if not path.exists():
        problems.append(f"missing file: {path}")
        return problems
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in REQUIRED:
        if col not in df.columns:
            problems.append(f"missing column: {col}")
    if problems:
        return problems
    dupes = df["BatchID"][df["BatchID"].duplicated()].tolist()
    if dupes:
        problems.append(f"duplicate BatchID: {dupes}")
    design = pd.read_csv(DESIGN, dtype=str, keep_default_na=False)
    known = set(design["BatchID"])
    unknown = [b for b in df["BatchID"] if b not in known]
    if unknown:
        problems.append(f"BatchID not in campaign design: {unknown}")
    missing = [b for b in known if b not in set(df["BatchID"])]
    if missing:
        problems.append(f"design BatchID missing from measured file: {missing}")
    for _, row in df.iterrows():
        bid = row["BatchID"]
        es_str = row["EnzymeToSubstrateRatio"].strip()
        if es_str:
            try:
                es = float(es_str)
                if es not in ALLOWED_ES:
                    problems.append(f"{bid}: E/S={es} outside allowed {{0.01,0.02,0.04,0.06}}")
            except ValueError:
                problems.append(f"{bid}: E/S not numeric: {es_str!r}")
        dh = row["FinalDH_pct"].strip()
        if dh:
            if ":" in dh or ";" in dh:
                problems.append(f"{bid}: FinalDH seems time-formatted: {dh!r}")
            else:
                try:
                    dhf = float(dh)
                    if not (0.0 <= dhf <= 100.0):
                        problems.append(f"{bid}: FinalDH={dhf} outside 0-100")
                except ValueError:
                    problems.append(f"{bid}: FinalDH not numeric: {dh!r}")
        d_row = design[design["BatchID"] == bid]
        if d_row.empty:
            continue
        for col in ["pH", "Temp_C", "Duration_min", "SubstrateConc_gL"]:
            val = row[col].strip()
            if not val:
                continue
            try:
                fv = float(val)
            except ValueError:
                problems.append(f"{bid}: {col} not numeric: {val!r}")
                continue
            target = float(d_row[col].iloc[0])
            if col in ("pH", "Temp_C"):
                dev = abs(fv - target)
            else:
                dev = abs(fv - target) / target
            if dev > TOL[col]:
                problems.append(f"{bid}: {col}={fv} deviates {dev:.3f} from design {target}")
    return problems


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else MEASURED
    problems = check(path)
    if problems:
        print("VALIDATION FAILED:")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("validation OK: measured_runs.csv consistent with campaign design")


if __name__ == '__main__':
    main()