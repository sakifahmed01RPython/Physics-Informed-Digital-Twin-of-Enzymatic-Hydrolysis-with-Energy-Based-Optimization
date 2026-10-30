"""ingest_campaign.py - append validated campaign measurements to the training set.

Uses the same raw-string loader and composition imputation as run_ebm_loop so a
half-filled template can never inject NaN into the golden dataset.
"""
import argparse
from pathlib import Path

import pandas as pd

from src.run_ebm_loop import load_measured_campaign_runs, prepare_measured
from src.validate_measured import check

BASE = Path(__file__).resolve().parents[1]
DATA_DIR = BASE / "data"

REQUIRED = ["BatchID", "RawMaterial", "Enzyme", "EnzymeToSubstrateRatio",
            "SubstrateConc_gL", "Temp_C", "pH", "Duration_min",
            "Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
            "Hydroxyproline_pct", "Collagen_pct", "FinalDH_pct"]


def main():
    ap = argparse.ArgumentParser(description="Append validated campaign measurements to the training set.")
    ap.add_argument("--input", default=str(DATA_DIR / "campaign" / "measured_runs.csv"),
                    help="measurement file (default: measured_runs.csv)")
    ap.add_argument("--output", default=str(DATA_DIR / "processed" / "main_batch_clean.csv"),
                    help="golden training file to extend (default: main_batch_clean.csv)")
    args = ap.parse_args()

    src = Path(args.input)
    dst = Path(args.output)

    rep = check(src)
    if rep.problems:
        for p in rep.problems:
            print("  -", p)
        raise SystemExit(f"ingest aborted: {len(rep.problems)} validation problem(s) in {src.name}")

    golden = DATA_DIR / "processed" / "main_batch_clean.csv"
    df = pd.read_csv(golden) if dst == golden or not dst.exists() else pd.read_csv(dst)
    measured = load_measured_campaign_runs(src)
    if measured.empty:
        print(f"ingest: no completed runs in {src.name} - nothing to ingest")
        return

    prepared, notes = prepare_measured(measured, df)
    for note in notes:
        print("  note:", note)

    already = set(df["BatchID"])
    fresh = prepared[~prepared["BatchID"].isin(already)]
    if fresh.empty:
        print(f"ingest: no new rows (all {len(measured)} completed BatchIDs already present)")
        return
    merged = pd.concat([df, fresh[REQUIRED]], ignore_index=True)
    if merged[REQUIRED].isna().any().any():
        raise SystemExit("ingest aborted: merged frame still has missing values")
    merged["S0_gL"] = merged["SubstrateConc_gL"] * merged["CrudeProtein_pct"] / 100.0
    merged["E0_gL"] = merged["EnzymeToSubstrateRatio"] * merged["S0_gL"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(dst, index=False)
    print(f"ingest: {len(df)} -> {len(merged)} rows ({len(fresh)} campaign rows) -> {dst}")


if __name__ == "__main__":
    main()
