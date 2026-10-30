"""validate_measured.py - guard the bench -> training handoff.

Row states:
  PENDING  - every assay field blank: the run has not been measured yet (allowed)
  COMPLETE - FinalDH present: the run counts; composition may be blank because the
             loop imputes it from the material median (warning, not error)
  PARTIAL  - some assay fields filled but FinalDH missing: a half-recorded run,
             which is exactly how corrupted data enters (error)

Exit codes:
  0  validation OK, at least one measured run
  1  problems found
  2  structurally valid but nothing measured yet (use --allow-empty for pre-flight)
"""
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

CAMPAIGN_DIR = Path(__file__).resolve().parents[1] / 'data' / 'campaign'
MEASURED = CAMPAIGN_DIR / 'measured_runs.csv'
DESIGN = CAMPAIGN_DIR / 'campaign_design.csv'

REQUIRED = ["BatchID", "RawMaterial", "Enzyme", "EnzymeToSubstrateRatio",
            "SubstrateConc_gL", "Temp_C", "pH", "Duration_min",
            "Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
            "Hydroxyproline_pct", "Collagen_pct", "FinalDH_pct"]

COMPOSITION = ["Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
               "Hydroxyproline_pct", "Collagen_pct"]
ASSAY_COLS = COMPOSITION + ["FinalDH_pct"]

ALLOWED_ES = {0.01, 0.02, 0.04, 0.06}

TOL = {"pH": 0.5, "Temp_C": 2.0, "Duration_min": 0.15, "SubstrateConc_gL": 0.20}


@dataclass
class Report:
    problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    n_rows: int = 0
    n_complete: int = 0
    n_pending: int = 0

    @property
    def ok(self):
        return not self.problems


def _num(problems, bid, label, raw, lo=None, hi=None):
    try:
        val = float(raw)
    except (TypeError, ValueError):
        problems.append(f"{bid}: {label} not numeric: {raw!r}")
        return None
    if lo is not None and not (lo <= val <= hi):
        problems.append(f"{bid}: {label}={val} outside {lo}-{hi}")
        return None
    return val


def check(path=MEASURED, design_path=DESIGN):
    rep = Report()
    path = Path(path)
    design_path = Path(design_path)
    if not path.exists():
        rep.problems.append(f"missing file: {path}")
        return rep
    if not design_path.exists():
        rep.problems.append(f"missing design file: {design_path}")
        return rep

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = df.apply(lambda s: s.str.strip() if s.dtype == object else s)
    rep.n_rows = len(df)

    for col in REQUIRED:
        if col not in df.columns:
            rep.problems.append(f"missing column: {col}")
    if rep.problems:
        return rep

    dupes = df["BatchID"][df["BatchID"].duplicated()].tolist()
    if dupes:
        rep.problems.append(f"duplicate BatchID: {dupes}")

    design = pd.read_csv(design_path, dtype=str, keep_default_na=False)
    known = set(design["BatchID"])
    unknown = [b for b in df["BatchID"] if b not in known]
    if unknown:
        rep.problems.append(f"BatchID not in campaign design: {unknown}")
    missing = [b for b in known if b not in set(df["BatchID"])]
    if missing:
        rep.problems.append(f"design BatchID missing from measured file: {missing}")

    for _, row in df.iterrows():
        bid = row["BatchID"]
        dh_raw = row["FinalDH_pct"]
        filled_assay = [c for c in COMPOSITION if row[c]]

        if not dh_raw:
            if filled_assay:
                rep.problems.append(
                    f"{bid}: PARTIAL row - FinalDH_pct missing while "
                    f"{', '.join(filled_assay)} filled")
            else:
                rep.n_pending += 1
            continue

        rep.n_complete += 1
        if ":" in dh_raw or ";" in dh_raw:
            rep.problems.append(f"{bid}: FinalDH seems time-formatted: {dh_raw!r}")
        else:
            _num(rep.problems, bid, "FinalDH", dh_raw, 0.0, 100.0)

        for col in COMPOSITION:
            raw = row[col]
            if raw:
                _num(rep.problems, bid, col, raw, 0.0, 100.0)
            else:
                rep.warnings.append(
                    f"{bid}: {col} blank - loop will impute the material median")

        es_str = row["EnzymeToSubstrateRatio"]
        if es_str:
            es = _num(rep.problems, bid, "E/S", es_str)
            if es is not None and es not in ALLOWED_ES:
                rep.problems.append(
                    f"{bid}: E/S={es} outside allowed {{0.01,0.02,0.04,0.06}}")
        else:
            rep.problems.append(f"{bid}: E/S blank on a completed run")

        d_row = design[design["BatchID"] == bid]
        if d_row.empty:
            continue
        for col in ["pH", "Temp_C", "Duration_min", "SubstrateConc_gL"]:
            val = row[col]
            if not val:
                rep.problems.append(f"{bid}: {col} blank on a completed run")
                continue
            try:
                fv = float(val)
            except ValueError:
                rep.problems.append(f"{bid}: {col} not numeric: {val!r}")
                continue
            target = float(d_row[col].iloc[0])
            dev = abs(fv - target) if col in ("pH", "Temp_C") else abs(fv - target) / target
            if dev > TOL[col]:
                rep.problems.append(f"{bid}: {col}={fv} deviates {dev:.3f} from design {target}")
    return rep


def main():
    ap = argparse.ArgumentParser(description="Validate measured campaign runs.")
    ap.add_argument("path", nargs="?", default=str(MEASURED),
                    help="measured runs CSV (default: data/campaign/measured_runs.csv)")
    ap.add_argument("--design", default=str(DESIGN), help="campaign design CSV")
    ap.add_argument("--allow-empty", action="store_true",
                    help="exit 0 even when no run has been measured yet")
    args = ap.parse_args()

    rep = check(args.path, args.design)
    print(f"rows={rep.n_rows} complete={rep.n_complete} pending={rep.n_pending}")
    for w in rep.warnings:
        print("  !", w)
    if rep.problems:
        print("VALIDATION FAILED:")
        for p in rep.problems:
            print("  -", p)
        return 1
    if rep.n_complete == 0 and not args.allow_empty:
        print("VALIDATION INCOMPLETE: 0 measured runs - nothing to validate.")
        print("Fill at least one FinalDH_pct, or pass --allow-empty for a pre-flight check.")
        return 2
    print(f"validation OK: {rep.n_complete} measured run(s) consistent with campaign design")
    return 0


if __name__ == '__main__':
    sys.exit(main())
