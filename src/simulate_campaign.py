import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.ode_model import dh_curve

BASE = Path(__file__).resolve().parents[1]
DATA_DIR = BASE / "data"
PROCESSED_DIR = DATA_DIR / "processed"
CAMPAIGN_DIR = DATA_DIR / "campaign"
MODEL_DIR = BASE / "models"

COMP_COLS = ["Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
             "Hydroxyproline_pct", "Collagen_pct"]
OUTPUT_COLS = ["BatchID", "RawMaterial", "Enzyme", "EnzymeToSubstrateRatio",
               "SubstrateConc_gL", "Temp_C", "pH", "Duration_min"] + COMP_COLS + ["FinalDH_pct"]

ALCALASE_SIGMA = 1.75
PRIOR_SIGMA_FLOOR = 4.0


def simulate():
    rng = np.random.default_rng(7)
    main = pd.read_csv(PROCESSED_DIR / "main_batch_clean.csv")
    camp = pd.read_csv(CAMPAIGN_DIR / "campaign_design.csv")
    params = json.loads((MODEL_DIR / "ode_params_alcalase.json").read_text())

    comp_stats = {}
    for mat in main["RawMaterial"].unique():
        sub = main[main["RawMaterial"] == mat]
        comp_stats[mat] = {
            "base": sub[COMP_COLS].astype(float),
            "min": sub[COMP_COLS].astype(float).min(),
            "max": sub[COMP_COLS].astype(float).max(),
            "n": int(len(sub)),
        }

    rows = []
    report = []
    for _, r in camp.iterrows():
        mat = r["RawMaterial"]
        cs = comp_stats[mat]
        base = cs["base"].iloc[rng.integers(0, cs["n"])]
        jitter = 1.0 + rng.normal(0.0, 0.03, size=len(COMP_COLS))
        comp = np.clip(base.to_numpy(float) * jitter,
                       cs["min"].to_numpy(float) * 0.9,
                       cs["max"].to_numpy(float) * 1.1)
        comp = dict(zip(COMP_COLS, comp))

        sub_g = float(r["SubstrateConc_gL"])
        s0 = sub_g * comp["CrudeProtein_pct"] / 100.0
        e0 = float(r["EnzymeToSubstrateRatio"]) * s0
        dur = float(r["Duration_min"])

        if r["Enzyme"] == "Alcalase":
            p = dict(params)
            dh = float(dh_curve(s0, e0, float(r["Temp_C"]), float(r["pH"]), [0.0, dur], p)[-1])
            dh += rng.normal(0.0, ALCALASE_SIGMA)
            basis = "physics"
            sigma = ALCALASE_SIGMA
            conf = "fitted ODE integration (Alcalase kinetics)"
        else:
            rows_e = main[main["Enzyme"] == r["Enzyme"]]
            mean_dh = float(rows_e["FinalDH_pct"].mean())
            max_dh = float(rows_e["FinalDH_pct"].max())
            sigma = float(rows_e["FinalDH_pct"].std()) if len(rows_e) > 1 else PRIOR_SIGMA_FLOOR
            sigma = max(sigma, PRIOR_SIGMA_FLOOR)
            dh = mean_dh + 8.0 * np.log(dur / 120.0)
            cap = min(80.0, max_dh + 10.0)
            dh = float(np.clip(dh + rng.normal(0.0, sigma), 0.1, cap))
            basis = "prior_low_conf"
            conf = (f"enzyme mean {mean_dh:.1f}% + log-duration add {8.0 * np.log(dur / 120.0):+.1f} "
                    f"(n={len(rows_e)}, cap {cap:.1f})")

        dh = float(np.clip(dh, 0.1, 95.0))
        rows.append({
            "BatchID": r["BatchID"], "RawMaterial": mat, "Enzyme": r["Enzyme"],
            "EnzymeToSubstrateRatio": float(r["EnzymeToSubstrateRatio"]),
            "SubstrateConc_gL": sub_g, "Temp_C": float(r["Temp_C"]),
            "pH": float(r["pH"]), "Duration_min": dur, **comp, "FinalDH_pct": round(dh, 1),
        })
        report.append({
            "BatchID": r["BatchID"], "basis": basis, "sigma": round(sigma, 2),
            "FinalDH_pct": round(dh, 1), "composition_source": f"{mat} (n={cs['n']})",
            "basis_detail": conf,
        })

    out = pd.DataFrame(rows, columns=OUTPUT_COLS)
    out.to_csv(CAMPAIGN_DIR / "measured_runs_simulated.csv", index=False)

    rep = pd.DataFrame(report)
    lines = [
        "# Simulation Report — synthetic campaign measurements",
        "",
        "Status: **DEMO ONLY** — throwaway data, never merged into the real pipeline.",
        "Any real campaign run must be re-measured and entered in `measured_runs.csv`.",
        "",
        f"Generated from: fitted Alcalase ODE (`models/ode_params_alcalase.json`) +",
        "per-material composition sampling from `main_batch_clean.csv` (jitter ±3%, clipped to material range).",
        "",
        "| BatchID | Basis | sigma (DH pts) | FinalDH (%) | Composition source | Detail |",
        "|---|---|---|--:|---|---|",
    ]
    for _, r in rep.iterrows():
        lines.append(f"| {r['BatchID']} | {r['basis']} | {r['sigma']} | {r['FinalDH_pct']} | "
                     f"{r['composition_source']} | {r['basis_detail']} |")
    lines += [
        "",
        "## Per-arm summary",
        "| arm | basis mix | mean FinalDH (%) |",
        "|---|---|--:|",
    ]
    merged = rep.merge(camp[["BatchID", "arm"]], on="BatchID")
    for arm in ["dose_sweep", "process_lhc", "gap_fill"]:
        sub = merged[merged["arm"] == arm]
        mix = ", ".join(sorted(sub["basis"].value_counts().index))
        lines.append(f"| {arm} | {mix} | {sub['FinalDH_pct'].mean():.1f} |")
    (CAMPAIGN_DIR / "simulation_report.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Simulated: {len(out)} rows -> data/campaign/measured_runs_simulated.csv")
    print(f"Report: data/campaign/simulation_report.md")
    print("FinalDH by arm:")
    for arm in ["dose_sweep", "process_lhc", "gap_fill"]:
        ids = camp[camp["arm"] == arm]["BatchID"]
        sub = out[out["BatchID"].isin(ids)]
        for _, x in sub.iterrows():
            print(f"  {x['BatchID']}  {x['Enzyme']:<22} DH={x['FinalDH_pct']:5.1f}")


if __name__ == "__main__":
    simulate()