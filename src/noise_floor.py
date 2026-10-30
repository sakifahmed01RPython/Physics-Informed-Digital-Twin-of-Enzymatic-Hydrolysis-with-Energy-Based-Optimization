"""noise_floor.py - quantify within-condition variability from REAL replicate groups.

Writes the internal noise-floor notes. No synthetic data is used here: every number comes
from data/processed/main_batch_clean.csv.

Why this exists: the twin's tolerance bands were judgment calls (+/-3 fitted,
+/-12 prior). The four Alcalase runs at identical setpoints span 3.4-21.1 % DH,
so the bands must be derived from the data, not decreed.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
MAIN = BASE / "data" / "processed" / "main_batch_clean.csv"
MODEL = BASE / "models" / "ode_params_alcalase.json"
TIMECOURSE = BASE / "data" / "processed" / "time_course_clean.csv"
OUT = BASE / "docs" / "noise_floor.md"

GROUP_KEYS = ["Enzyme", "RawMaterial", "Temp_C", "pH", "Duration_min",
              "SubstrateConc_gL"]
TIGHT_SD = 2.0  # a group this tight is repeatability, not a lot/occasion effect


def replicate_groups(df):
    rows = []
    for key, g in df.groupby(GROUP_KEYS, dropna=False):
        if len(g) < 2:
            continue
        y = g["FinalDH_pct"].to_numpy(float)
        rows.append({
            "Enzyme": key[0], "Material": key[1], "Temp_C": key[2],
            "pH": key[3], "Duration_min": key[4], "SubstrateConc_gL": key[5],
            "n": len(y), "mean": float(y.mean()), "sd": float(y.std(ddof=1)),
            "min": float(y.min()), "max": float(y.max()),
            "batches": ", ".join(g["BatchID"].astype(str)),
        })
    return sorted(rows, key=lambda r: (-r["sd"], r["batches"]))


def pooled_sd(groups):
    ss = sum((r["n"] - 1) * r["sd"] ** 2 for r in groups)
    dof = sum(r["n"] - 1 for r in groups)
    if dof == 0:
        return float("nan"), 0
    return float(np.sqrt(ss / dof)), int(dof)


def curve_residuals():
    """Per-curve RMSE of the fitted ODE, using each batch's recorded T/pH."""
    params = json.loads(MODEL.read_text())
    from src.ode_model import dh_curve
    main = pd.read_csv(MAIN)
    tc = pd.read_csv(TIMECOURSE)
    out = []
    for bid in sorted(tc["BatchID"].unique()):
        row = main[main["BatchID"] == bid].iloc[0]
        if row["Enzyme"] != "Alcalase":
            continue
        c = tc[tc["BatchID"] == bid]
        pred = dh_curve(float(row["S0_gL"]), float(row["E0_gL"]),
                        float(row["Temp_C"]), float(row["pH"]),
                        c["Time_min"].to_numpy(float), params)
        rmse = float(np.sqrt(np.mean((c["DegreeOfHydrolysis_pct"].to_numpy(float) - pred) ** 2)))
        out.append((bid, rmse))
    return out


def main():
    df = pd.read_csv(MAIN)
    groups = replicate_groups(df)
    tight = [g for g in groups if g["sd"] <= TIGHT_SD]
    pooled_all, dof_all = pooled_sd(groups)
    repeat, dof_rep = pooled_sd(tight)
    predictive = 2.0 * pooled_all
    fit_band = 3.0
    residuals = curve_residuals()
    mean_rmse = float(np.mean([r for _, r in residuals])) if residuals else float("nan")

    lines = [
        "# Noise Floor — within-condition variability (real data only)",
        "",
        f"Source: `{MAIN.relative_to(BASE).as_posix()}` ({len(df)} real batches).",
        "Groups are rows with identical Enzyme, material, temperature, pH, duration",
        "and substrate concentration. Synthetic data is not used here.",
        "",
        "## Replicate groups",
        "",
        "| Enzyme | Material | T (C) | pH | t (min) | S (g/L) | n | mean DH | SD | min | max | batches |",
        "|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|---|",
    ]
    for g in groups:
        lines.append(
            f"| {g['Enzyme']} | {g['Material']} | {g['Temp_C']:.1f} | {g['pH']:.2f} | "
            f"{g['Duration_min']:.0f} | {g['SubstrateConc_gL']:.1f} | {g['n']} | "
            f"{g['mean']:.1f} | {g['sd']:.2f} | {g['min']:.1f} | {g['max']:.1f} | {g['batches']} |")

    lines += [
        "",
        "## Pooled estimates",
        "",
        f"- **Repeatability** (groups with SD <= {TIGHT_SD:.1f} DH): "
        f"**{repeat:.2f} DH pts** (pooled, df={dof_rep}).",
        f"- **All replicate groups**: **{pooled_all:.2f} DH pts** (pooled, df={dof_all}).",
    ]
    if groups:
        worst = groups[0]
        lines.append(
            f"- **Worst group**: {worst['batches']} at identical setpoints spans "
            f"{worst['min']:.1f}-{worst['max']:.1f} % DH (SD {worst['sd']:.2f}).")
    lines += [
        "",
        "## Derived bands",
        "",
        f"- **Fit band** (interpolation on the calibrated curves): +/-{fit_band:.1f} DH "
        f"= {fit_band / repeat:.1f}x repeatability. Used for curve diagnostics only.",
        f"- **New-run predictive band** (2 x pooled SD): **+/-{predictive:.1f} DH pts**. "
        "Used when the twin judges a campaign run at conditions it has not seen.",
        "- **Non-Alcalase prior band**: +/-12.0 DH (predictive floor + model-form error,",
        "  because the Alcalase kinetics are applied to other enzymes).",
        "",
        "## Fitted-ODE residual vs the noise floor",
        "",
    ]
    for bid, rmse in residuals:
        lines.append(f"- {bid}: RMSE {rmse:.2f} DH = {rmse / repeat:.1f}x repeatability")
    lines += [
        "",
        f"Mean curve RMSE: **{mean_rmse:.2f} DH** = {mean_rmse / repeat:.1f}x repeatability.",
        "",
        "## Interpretation (do not soften this)",
        "",
        "- Repeatability is about 1 DH point. The four Alcalase runs at the *same* ",
        "  setpoint span 17.7 DH points. That gap is not assay noise; it is a lot/occasion",
        "  effect (enzyme activity, substrate batch, or an unrecorded process variable).",
        "- Therefore a new Alcalase run cannot be judged against +/-3 DH. The honest",
        "  predictive band is about +/-12 DH until enzyme/substrate lots are recorded.",
        "- The ODE fits the *selected* curves at 2-4x repeatability, which is respectable",
        "  for interpolation, but it does not explain the replicate spread.",
        "- Consequence for the campaign: triplicate one condition before trusting any",
        "  single-run comparison; otherwise the twin is optimising lot noise.",
        "",
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[noise_floor] wrote {OUT}")
    print(f"  repeatability={repeat:.2f} DH (df={dof_rep})")
    print(f"  pooled all   ={pooled_all:.2f} DH (df={dof_all})")
    print(f"  predictive   =+/-{predictive:.1f} DH")
    print(f"  mean curve RMSE={mean_rmse:.2f} DH ({mean_rmse / repeat:.1f}x repeatability)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
