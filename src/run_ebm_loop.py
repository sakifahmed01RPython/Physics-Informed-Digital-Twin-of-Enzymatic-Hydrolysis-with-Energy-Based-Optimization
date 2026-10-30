"""run_ebm_loop.py - one acquisition round of the closed loop.

Hardening (step 1):
  * measured runs are read as RAW STRINGS and only COMPLETED rows (FinalDH present)
    enter the training frame - pending template rows are ignored, never NaN-poisoned;
  * missing composition is imputed from the material median and logged, because the
    documented bench workflow only requires FinalDH to be filled;
  * the training frame, the training loss and every proposal are checked finite
    before anything is logged or written.

Benchmark status (2026-10-30): the held-out synthetic benchmark shows this loop
beats random/LHC/grid but loses to OFAT, and EI ranking is weak.  Production
keeps MIN_CLASS_ROWS=3; the frozen benchmark policy used min 1 only as a
cold-start ablation.  See data/synthetic/benchmark_final_report.md.
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from src.csv_io import read_raw_csv
from src.ebm_optimizer import (COMPOSITION_COLS, DOSE_COL, MODEL_NUM_COLS,
                               PROCESS_COLS, EBMOptimizer, feasible_y_best)

DATA_DIR = Path("data/processed")
CAMPAIGN_DIR = Path("data/campaign")
MODEL_DIR = Path("models")
ROUND_LOG = CAMPAIGN_DIR / "active_loop_history.csv"
N_ACQUIRE = 3

REQUIRED = ["BatchID", "RawMaterial", "Enzyme", "EnzymeToSubstrateRatio",
            "SubstrateConc_gL", "Temp_C", "pH", "Duration_min",
            "Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
            "Hydroxyproline_pct", "Collagen_pct", "FinalDH_pct"]
NUMERIC = ["EnzymeToSubstrateRatio", "SubstrateConc_gL", "Temp_C", "pH",
           "Duration_min"] + COMPOSITION_COLS + ["FinalDH_pct"]
MODEL_COLS = MODEL_NUM_COLS + ["FinalDH_pct"]
PROPOSAL_KEYS = ["EI", "expected_DH", "pH", "Temp_C", "Duration_min",
                 "SubstrateConc_gL", DOSE_COL]


def load_current_data(path=DATA_DIR / "main_batch_clean.csv"):
    return pd.read_csv(path)


def load_measured_campaign_runs(path=CAMPAIGN_DIR / "measured_runs.csv"):
    """Return ONLY completed campaign rows, with numeric columns converted.

    Reads raw strings first (the pandas coercion lesson): a cell like "4:48" must
    fail loudly, not become NaN and be mistaken for "not measured yet".
    """
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=REQUIRED)
    raw = read_raw_csv(path)

    missing = [c for c in REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f"{path.name} missing column(s): {missing}")

    done = raw[raw["FinalDH_pct"].notna()].copy()
    if done.empty:
        return done

    for col in NUMERIC:
        original = done[col]
        coerced = pd.to_numeric(original, errors="coerce")
        bad = done.loc[coerced.isna() & original.notna(), "BatchID"].astype(str).tolist()
        if bad:
            raise ValueError(
                f"{path.name}: non-numeric {col} in completed run(s) {bad} - "
                f"fix the raw cell(s) before running the loop")
        done[col] = coerced

    blank = done[["RawMaterial", "Enzyme", *PROCESS_COLS,
                  "EnzymeToSubstrateRatio"]].isna().any(axis=1)
    if blank.any():
        raise ValueError(
            "completed run(s) missing setpoints: "
            + ", ".join(done.loc[blank, "BatchID"].astype(str)))
    return done.reset_index(drop=True)


def prepare_measured(measured, main):
    """Impute missing composition from the material median (documented fallback)."""
    if measured.empty:
        return measured.copy(), []
    df = measured.copy()
    notes = []
    for col in COMPOSITION_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    missing = df[COMPOSITION_COLS].isna().any(axis=1)
    if missing.any():
        mat_med = main.groupby("RawMaterial")[COMPOSITION_COLS].median()
        global_med = main[COMPOSITION_COLS].median()
        for idx in df.index[missing]:
            mat = df.at[idx, "RawMaterial"]
            known = mat in mat_med.index
            fill = mat_med.loc[mat] if known else global_med
            for col in COMPOSITION_COLS:
                if pd.isna(df.at[idx, col]):
                    df.at[idx, col] = float(fill[col])
            notes.append(
                f"{df.at[idx, 'BatchID']}: composition imputed from "
                f"{'material ' + str(mat) if known else 'global'} median")
    return df, notes


def append_measured(df_main, measured):
    """Append completed campaign rows to the training frame, NaN-free."""
    if measured.empty:
        return df_main
    already = set(df_main["BatchID"])
    fresh = measured[~measured["BatchID"].isin(already)]
    if fresh.empty:
        return df_main

    prepared, notes = prepare_measured(fresh, df_main)
    for note in notes:
        print(f"  note: {note}")

    if float(prepared["EnzymeToSubstrateRatio"].nunique()) == 1 and \
            float(prepared["EnzymeToSubstrateRatio"].iloc[0]) == 0.02:
        print("warning: no weighed E/S variation found in measured runs")

    merged = pd.concat([df_main, prepared[REQUIRED]], ignore_index=True)
    merged["S0_gL"] = merged["SubstrateConc_gL"] * merged["CrudeProtein_pct"] / 100.0
    merged["E0_gL"] = merged["EnzymeToSubstrateRatio"] * merged["S0_gL"]

    bad = merged[MODEL_COLS].isna().any(axis=1)
    if bad.any():
        raise ValueError(
            "training frame has missing model inputs for: "
            + ", ".join(merged.loc[bad, "BatchID"].astype(str)))
    X = merged[MODEL_NUM_COLS].to_numpy(float)
    y = merged["FinalDH_pct"].to_numpy(float)
    if not (np.isfinite(X).all() and np.isfinite(y).all()):
        raise ValueError("training frame contains non-finite values")
    return merged


def train_ebm(df, seed=42):
    if df[MODEL_COLS].isna().any().any():
        raise ValueError("refusing to train: training frame has missing values")
    X = df[MODEL_NUM_COLS].to_numpy(float)
    if not np.isfinite(X).all():
        raise ValueError("refusing to train: non-finite features")
    opt = EBMOptimizer()
    opt.meta = df.copy()
    opt.fit_x_stats(opt.make_x(df))
    loss = opt.train(df, seed=seed, epochs=800)
    if not np.isfinite(loss):
        raise RuntimeError(f"EBM training diverged (loss={loss}); refusing to propose")
    return opt


def check_proposals(proposals):
    for p in proposals:
        vals = np.asarray([p[k] for k in PROPOSAL_KEYS], dtype=float)
        if not np.isfinite(vals).all():
            raise RuntimeError(f"non-finite proposal: {p}")
    return proposals


def log_round(round_no, proposals, df, hist_path=ROUND_LOG):
    best = float(df["FinalDH_pct"].max())
    best_feasible = feasible_y_best(df)
    rows = []
    for i, p in enumerate(proposals):
        rows.append({
            "round": round_no, "rank": i + 1, "EI": round(p["EI"], 4),
            "expected_DH": p["expected_DH"], "Enzyme": p["Enzyme"],
            "pH": p["pH"], "Temp_C": p["Temp_C"], "Duration_min": p["Duration_min"],
            "SubstrateConc_gL": p["SubstrateConc_gL"],
            DOSE_COL: p[DOSE_COL], "best_observed": best,
            "y_best_feasible": best_feasible,
        })
    new = pd.DataFrame(rows)
    if not np.isfinite(new[PROPOSAL_KEYS].to_numpy(float)).all():
        raise RuntimeError("refusing to log non-finite acquisition row")
    hist_path = Path(hist_path)
    if hist_path.exists():
        old = pd.read_csv(hist_path)
        pd.concat([old, new], ignore_index=True).to_csv(hist_path, index=False)
    else:
        new.to_csv(hist_path, index=False)


def main():
    ap = argparse.ArgumentParser(description="Run one acquisition round of the EBM loop.")
    ap.add_argument("--data", default=str(DATA_DIR / "main_batch_clean.csv"),
                    help="training set (default: main_batch_clean.csv)")
    ap.add_argument("--measured", default=str(CAMPAIGN_DIR / "measured_runs.csv"),
                    help="measured campaign file (default: measured_runs.csv)")
    ap.add_argument("--hist", default=str(ROUND_LOG),
                    help="round history file (default: active_loop_history.csv)")
    args = ap.parse_args()
    data_path = Path(args.data)
    hist_path = Path(args.hist)
    df = load_current_data(data_path)
    measured = load_measured_campaign_runs(args.measured)
    print(f"Completed campaign rows available: {len(measured)}")
    df = append_measured(df, measured)
    print(f"EBM training data: {len(df)} rows, best observed FinalDH={df['FinalDH_pct'].max():.1f}%")
    print(f"Acquisition anchor: y_best feasible={feasible_y_best(df):.1f}% "
          f"(all-data best={df['FinalDH_pct'].max():.1f}%)")
    print(f"Enzyme rows: {df['Enzyme'].value_counts().to_dict()}")
    round_no = 1
    if hist_path.exists():
        hist = pd.read_csv(hist_path)
        if len(hist):
            round_no = int(hist["round"].max()) + 1
    opt = train_ebm(df)
    proposals = check_proposals(opt.acquire(df, n_new=N_ACQUIRE, seed=round_no * 100))
    print(f"Round {round_no} acquisitions:")
    for p in proposals:
        print(f"  EI={p['EI']:.3f} expDH={p['expected_DH']:.1f} | {p['Enzyme']:<22} pH={p['pH']:.2f} "
              f"T={p['Temp_C']:.1f}C dur={p['Duration_min']:.0f}min sub={p['SubstrateConc_gL']:.1f} g/L "
              f"E/S={p[DOSE_COL]:.2f}")
    log_round(round_no, proposals, df, hist_path)
    print(f"Logged: {hist_path}")


if __name__ == "__main__":
    main()
