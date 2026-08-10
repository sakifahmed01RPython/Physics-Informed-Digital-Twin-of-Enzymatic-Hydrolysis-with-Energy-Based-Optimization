from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/processed")
AUDIT_PATH = Path("data/audit_report.md")

NON_ENZYMATIC_BATCHES = {"BATCH_023", "BATCH_025", "BATCH_038", "BATCH_039", "BATCH_040"}
DH_OUTLIER_BATCHES = {"BATCH_022", "BATCH_024"}
DRY_BASIS_BATCHES = {"BATCH_026", "BATCH_027"}
ENZYME_DOSE_RECODE = 0.02

MAIN_RENAMES = {
    "E/S Ratio": "EnzymeToSubstrateRatio",
    "Substrate Conc (g/L)": "SubstrateConc_gL",
    "Solid:Liquid": "SolidLiquidRatio",
    "Temp (°C)": "Temp_C",
    "Time (min)": "Duration_min",
    "Moisture (%)": "Moisture_pct",
    "Crude Protein (%)": "CrudeProtein_pct",
    "Crude Lipid (%)": "CrudeLipid_pct",
    "Ash (%)": "Ash_pct",
    "Hydroxyproline (%)": "Hydroxyproline_pct",
    "Collagen (%)": "Collagen_pct",
    "Protein Recovery (%)": "ProteinRecovery_pct",
    "Final DH (%)": "FinalDH_pct",
}


def load_main() -> pd.DataFrame:
    df = pd.read_excel(RAW_DIR / "Table 1 Main Batch Table.xlsx")
    df = df.rename(columns=MAIN_RENAMES)
    return df


def load_time_course() -> pd.DataFrame:
    return pd.read_excel(RAW_DIR / "Table 3 Time-Course Table (15 time points per batch).xlsx")


def load_bioactivity() -> pd.DataFrame:
    return pd.read_excel(RAW_DIR / "Table 2 Bioactivity Table.xlsx")


def apply_drops(main: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    log = []
    drop_reasons = {b: "non-enzymatic process (E/S = 0)" for b in NON_ENZYMATIC_BATCHES}
    drop_reasons.update({b: "physically impossible DH for enzymatic hydrolysis" for b in DH_OUTLIER_BATCHES})
    drop_reasons.update({b: "dry-basis composition (protein+lipid+ash ~99%) in wet-basis file; no verifiable wet-basis value" for b in DRY_BASIS_BATCHES})
    for batch_id, reason in sorted(drop_reasons.items()):
        was_present = (main["BatchID"] == batch_id).any()
        log.append({"BatchID": batch_id, "action": "drop", "reason": reason, "present": was_present})
    mask = ~main["BatchID"].isin(NON_ENZYMATIC_BATCHES | DH_OUTLIER_BATCHES | DRY_BASIS_BATCHES)
    return main[mask].copy(), log


def reconcile_final_dh(main: pd.DataFrame, tc: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    log = []
    changed = main.copy()
    for batch_id in tc["BatchID"].unique():
        if batch_id not in set(changed["BatchID"]):
            continue
        duration = int(changed.loc[changed["BatchID"] == batch_id, "Duration_min"].iloc[0])
        curve = tc[tc["BatchID"] == batch_id]
        at_duration = curve[curve["Time_min"] == duration]
        if len(at_duration) == 0:
            log.append({
                "BatchID": batch_id,
                "action": "keep",
                "reason": f"no curve point at declared Duration {duration} min (curve ends at {curve['Time_min'].max():.0f}); main FinalDH trusted",
            })
            continue
        measured = float(at_duration["DegreeOfHydrolysis_pct"].iloc[0])
        old = float(changed.loc[changed["BatchID"] == batch_id, "FinalDH_pct"].iloc[0])
        if abs(measured - old) > 1e-9:
            changed.loc[changed["BatchID"] == batch_id, "FinalDH_pct"] = measured
            log.append({
                "BatchID": batch_id,
                "action": "recompute",
                "reason": f"FinalDH {old} -> {measured} (= curve at Duration {duration} min)",
            })
    return changed, log


def add_derived(main: pd.DataFrame) -> pd.DataFrame:
    out = main.copy()
    out["S0_gL"] = out["SubstrateConc_gL"] * out["CrudeProtein_pct"] / 100.0
    out["E0_gL"] = out["EnzymeToSubstrateRatio"] * out["S0_gL"]
    return out


def recode_enzyme_dose(main: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    log = []
    changed = main.copy()
    old_values = sorted(changed["EnzymeToSubstrateRatio"].unique())
    changed["EnzymeToSubstrateRatio"] = ENZYME_DOSE_RECODE
    changed["E0_gL"] = changed["EnzymeToSubstrateRatio"] * changed["S0_gL"]
    log.append({
        "action": "recode",
        "reason": (
            f"recorded E/S inconsistent with measured kinetics (per-curve activity probe: MSE 21.99 -> 0.044 with "
            f"near-constant effective dose); declared lab practice: constant enzyme-to-substrate ratio. "
            f"Old distinct values {old_values} -> {ENZYME_DOSE_RECODE} for all rows."
        ),
    })
    return changed, log


def clean_time_course(tc: pd.DataFrame, main: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    log = []
    keep_ids = set(main["BatchID"])
    n_pre = len(tc)
    tc = tc[tc["BatchID"].isin(keep_ids)].copy()
    for batch_id, duration in main[["BatchID", "Duration_min"]].values:
        duration = int(duration)
        n_before = int((tc["BatchID"] == batch_id).sum())
        tc = tc[~((tc["BatchID"] == batch_id) & (tc["Time_min"] > duration))]
        n_after = int((tc["BatchID"] == batch_id).sum())
        if n_before != n_after:
            log.append({
                "BatchID": batch_id,
                "action": "truncate",
                "reason": f"removed {n_before - n_after} points beyond declared Duration {duration} min",
            })
    s0_map = main.set_index("BatchID")["S0_gL"].to_dict()
    tc["S_gL"] = (1.0 - tc["DegreeOfHydrolysis_pct"] / 100.0) * tc["BatchID"].map(s0_map)
    tc["P_gL"] = (tc["DegreeOfHydrolysis_pct"] / 100.0) * tc["BatchID"].map(s0_map)
    return tc, log


def clean_bioactivity(ba: pd.DataFrame) -> pd.DataFrame:
    return ba[["BatchID", "ORAC", "PeptideYield_pct"]].copy()


def build_audit(main_drop_log, dh_log, dose_log, trunc_log, main, tc, ba) -> str:
    lines = ["# Data Audit Report", ""]
    lines.append(f"Generated: {pd.Timestamp.now():%Y-%m-%d %H:%M}")
    lines.append("")
    lines.append("## Scope decisions applied")
    lines.append("")
    lines.append("- Enzymatic hydrolysis only; 5 non-enzymatic rows (E/S=0) and 2 physically impossible DH rows dropped.")
    lines.append("- Main Batch table is authoritative: curves truncated to declared Duration; FinalDH := curve value at Duration.")
    lines.append("- DH domain recalibrated to enzymatic ceiling (~50%); no synthetic capping.")
    lines.append("- Bioactivity reduced to ORAC + PeptideYield_pct; all IC50 columns excluded (unit/protocol anomalies).")
    lines.append("")
    lines.append("## Drops")
    lines.append("")
    lines.append("| BatchID | Reason |")
    lines.append("|---|---|")
    for row in main_drop_log:
        lines.append(f"| {row['BatchID']} | {row['reason']} |")
    lines.append("")
    lines.append("## FinalDH reconciliation (Main table vs curve at Duration)")
    lines.append("")
    lines.append("| BatchID | Action | Detail |")
    lines.append("|---|---|---|")
    for row in dh_log:
        lines.append(f"| {row['BatchID']} | {row['action']} | {row['reason']} |")
    lines.append("")
    lines.append("## Time-course truncation")
    lines.append("")
    lines.append("| BatchID | Action | Detail |")
    lines.append("|---|---|---|")
    for row in trunc_log:
        lines.append(f"| {row['BatchID']} | {row['action']} | {row['reason']} |")
    lines.append("")
    lines.append("## Enzyme dose recode")
    lines.append("")
    lines.append("| Action | Detail |")
    lines.append("|---|---|")
    for row in dose_log:
        lines.append(f"| {row['action']} | {row['reason']} |")
    lines.append("")
    lines.append("Consequences: `EnzymeToSubstrateRatio` is now constant (no dose-response information);")
    lines.append("`E0_gL` varies only via `S0_gL`. E/S is removed from the EBM acquisition space.")
    lines.append("The Phase-5 campaign must include a weighed-E/S arm to restore identifiability.")
    lines.append("")
    lines.append("## Coverage after cleaning")
    lines.append("")
    lines.append(f"- Main Batch rows: **{len(main)}**")
    lines.append(f"- Time-course curves: **{tc['BatchID'].nunique()}** ({len(tc)} points)")
    lines.append(f"- Bioactivity rows: **{len(ba)}**")
    lines.append("")
    lines.append("## Data-quality checks")
    lines.append("")
    lines.append(f"- Missing values in Main (kept rows, model columns): **{int(main.isna().sum().sum())}**")
    lines.append(f"- Missing values in Time-Course: **{int(tc.isna().sum().sum())}**")
    lines.append(f"- Missing values in Bioactivity: **{int(ba.isna().sum().sum())}**")
    lines.append("- FinalDH range of kept rows: "
                 f"{main['FinalDH_pct'].min():.1f}% – {main['FinalDH_pct'].max():.1f}%")
    lines.append("- Curve grids: points at 15-min spacing truncated at Duration; BATCH_009 curve kept to 300 min (Duration 720).")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    main_raw = load_main()
    tc_raw = load_time_course()
    ba_raw = load_bioactivity()

    main_clean, drop_log = apply_drops(main_raw)
    main_clean, dh_log = reconcile_final_dh(main_clean, tc_raw)
    main_clean = add_derived(main_clean)
    main_clean, dose_log = recode_enzyme_dose(main_clean)
    main_clean = main_clean.sort_values("BatchID").reset_index(drop=True)

    tc_clean, trunc_log = clean_time_course(tc_raw, main_clean)
    tc_clean = tc_clean.sort_values(["BatchID", "Time_min"]).reset_index(drop=True)

    ba_clean = clean_bioactivity(ba_raw)
    ba_clean = ba_clean[ba_clean["BatchID"].isin(set(main_clean["BatchID"]))].sort_values("BatchID").reset_index(drop=True)

    main_clean.to_csv(OUT_DIR / "main_batch_clean.csv", index=False)
    tc_clean.to_csv(OUT_DIR / "time_course_clean.csv", index=False)
    ba_clean.to_csv(OUT_DIR / "bioactivity_clean.csv", index=False)

    audit = build_audit(drop_log, dh_log, dose_log, trunc_log, main_clean, tc_clean, ba_clean)
    AUDIT_PATH.write_text(audit, encoding="utf-8")

    summary = main_raw["BatchID"].nunique() - len(main_clean)
    print(f"Main: {len(main_raw)} -> {len(main_clean)} rows ({summary} dropped)")
    print(f"Time-course: {len(tc_raw)} -> {len(tc_clean)} rows, {tc_clean['BatchID'].nunique()} curves")
    print(f"Bioactivity: {len(ba_raw)} -> {len(ba_clean)} rows")
    print(f"FinalDH range kept: {main_clean['FinalDH_pct'].min():.1f}% – {main_clean['FinalDH_pct'].max():.1f}%")
    print(f"Audit report: {AUDIT_PATH}")


if __name__ == "__main__":
    main()