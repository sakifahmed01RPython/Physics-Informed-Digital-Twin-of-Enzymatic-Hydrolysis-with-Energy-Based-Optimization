import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from src.ebm_optimizer import EBMOptimizer

DATA_DIR = Path("data/processed")
CAMPAIGN_DIR = Path("data/campaign")
MODEL_DIR = Path("models")
ROUND_LOG = CAMPAIGN_DIR / "active_loop_history.csv"
N_ACQUIRE = 3


def load_current_data(path=DATA_DIR / "main_batch_clean.csv"):
    return pd.read_csv(path)


def load_measured_campaign_runs():
    path = CAMPAIGN_DIR / "measured_runs.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def train_ebm(df, seed=42):
    opt = EBMOptimizer()
    opt.meta = df.copy()
    opt.fit_x_stats(opt.make_x(df))
    opt.train(df, seed=seed, epochs=800)
    return opt


def append_measured(df_main, measured):
    if measured.empty:
        return df_main
    already = set(df_main["BatchID"])
    fresh = measured[~measured["BatchID"].isin(already)]
    if fresh.empty:
        return df_main
    required = ["BatchID", "RawMaterial", "Enzyme", "EnzymeToSubstrateRatio",
                "SubstrateConc_gL", "Temp_C", "pH", "Duration_min",
                "Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
                "Hydroxyproline_pct", "Collagen_pct", "FinalDH_pct"]
    for col in required:
        if col not in fresh.columns:
            raise ValueError(f"measured_runs missing column: {col}")
    if float(fresh["EnzymeToSubstrateRatio"].nunique()) == 1 and \
            float(fresh["EnzymeToSubstrateRatio"].iloc[0]) == 0.02:
        print("warning: no weighed E/S variation found in measured runs")
    merged = pd.concat([df_main, fresh[required]], ignore_index=True)
    merged["S0_gL"] = merged["SubstrateConc_gL"] * merged["CrudeProtein_pct"] / 100.0
    merged["E0_gL"] = merged["EnzymeToSubstrateRatio"] * merged["S0_gL"]
    return merged


def log_round(round_no, proposals, df, hist_path=ROUND_LOG):
    best = float(df["FinalDH_pct"].max())
    rows = []
    for i, p in enumerate(proposals):
        rows.append({
            "round": round_no, "rank": i + 1, "EI": round(p["EI"], 4),
            "expected_DH": p["expected_DH"], "Enzyme": p["Enzyme"],
            "pH": p["pH"], "Temp_C": p["Temp_C"], "Duration_min": p["Duration_min"],
            "SubstrateConc_gL": p["SubstrateConc_gL"], "best_observed": best,
        })
    new = pd.DataFrame(rows)
    if hist_path.exists():
        old = pd.read_csv(hist_path)
        pd.concat([old, new], ignore_index=True).to_csv(hist_path, index=False)
    else:
        new.to_csv(hist_path, index=False)


def main():
    ap = argparse.ArgumentParser(description="Run one acquisition round of the EBM loop.")
    ap.add_argument("--data", default=str(DATA_DIR / "main_batch_clean.csv"),
                    help="training set (default: main_batch_clean.csv)")
    ap.add_argument("--hist", default=str(ROUND_LOG),
                    help="round history file (default: active_loop_history.csv)")
    args = ap.parse_args()
    data_path = Path(args.data)
    hist_path = Path(args.hist)
    df = load_current_data(data_path)
    measured = load_measured_campaign_runs()
    df = append_measured(df, measured)
    print(f"EBM training data: {len(df)} rows, best observed FinalDH={df['FinalDH_pct'].max():.1f}%")
    print(f"Enzyme rows: {df['Enzyme'].value_counts().to_dict()}")
    round_no = 1
    if hist_path.exists():
        hist = pd.read_csv(hist_path)
        if len(hist):
            round_no = int(hist["round"].max()) + 1
    opt = train_ebm(df)
    proposals = opt.acquire(df, n_new=N_ACQUIRE, seed=round_no * 100)
    print(f"Round {round_no} acquisitions:")
    for p in proposals:
        print(f"  EI={p['EI']:.3f} expDH={p['expected_DH']:.1f} | {p['Enzyme']:<22} pH={p['pH']:.2f} "
              f"T={p['Temp_C']:.1f}C dur={p['Duration_min']:.0f}min sub={p['SubstrateConc_gL']:.1f} g/L")
    log_round(round_no, proposals, df, hist_path)
    print(f"Logged: {hist_path}")


if __name__ == "__main__":
    main()