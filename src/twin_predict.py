import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.csv_io import read_raw_csv
from src.ode_model import dh_curve

DATA_DIR = Path("data/processed")
CAMPAIGN_DIR = Path("data/campaign")
MODEL_DIR = Path("models")
CONFIRM_REPORT = CAMPAIGN_DIR / "twin_confirmation.md"

FITTED_ENZYMES = {"Alcalase"}
# Bands derived in the internal noise-floor notes from the REAL replicate groups:
#   repeatability ~1.07 DH, pooled within-condition SD ~5.93 DH
TOL_FIT = 3.0          # interpolation on the 5 calibrated curves (~2.8x repeatability)
TOL_PREDICTIVE = 11.9  # new-run band = 2 x pooled SD
TOL_PRIOR = 12.0       # non-Alcalase: predictive floor + model-form error
DEFAULT_PROTEIN_RECOVERY = None
ORAC_FEATURE_ORDER = ["Temp_C", "pH", "Duration_min", "SubstrateConc_gL",
                      "Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
                      "Hydroxyproline_pct", "Collagen_pct", "FinalDH_pct", "ProteinRecovery_pct"]
COMPOSITION_COLS = ["Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
                    "Hydroxyproline_pct", "Collagen_pct"]


def load_ode_params():
    with open(MODEL_DIR / "ode_params_alcalase.json") as f:
        return json.load(f)


def load_orac_model():
    bundle = joblib.load(MODEL_DIR / "orac_ridge.joblib")
    return bundle["pipeline"], bundle["onehot"]


def material_composition(material):
    main = pd.read_csv(DATA_DIR / "main_batch_clean.csv")
    sub = main[main["RawMaterial"] == material]
    if len(sub):
        return {c: float(sub[c].median()) for c in COMPOSITION_COLS}
    fallback = main
    return {c: float(fallback[c].median()) for c in COMPOSITION_COLS}


def predict_run(enzyme, material, temp_c, ph, duration_min, substrate_conc_gL,
                e_s_ratio, comp=None, protein_recovery=None, n_pts=16):
    ode_params = load_ode_params()
    fitted = enzyme in FITTED_ENZYMES
    comp = comp if comp is not None else material_composition(material)
    s0 = substrate_conc_gL * float(comp["CrudeProtein_pct"]) / 100.0
    e0 = e_s_ratio * s0
    t_eval = np.linspace(0.0, float(duration_min), n_pts)
    p = dict(ode_params)
    if material == "cod_heads":
        p["kcat_ref"] = p["kcat_ref"] * p["sub_act_heads"]
    S, P, E, dh = None, None, None, None
    from src.ode_model import simulate
    try:
        S, P, E, dh = simulate(s0, e0, float(temp_c), float(ph), t_eval, params=p)
    except Exception as exc:
        return {"error": str(exc)}
    final_dh = float(dh[-1])
    orac_pred = None
    orac_note = ""
    if protein_recovery is None:
        protein_recovery = get_default_protein_recovery()
        orac_note = " (ProteinRecovery defaulted)"
    orac_row = [temp_c, ph, duration_min, substrate_conc_gL,
                comp["Moisture_pct"], comp["CrudeProtein_pct"], comp["CrudeLipid_pct"],
                comp["Ash_pct"], comp["Hydroxyproline_pct"], comp["Collagen_pct"],
                final_dh, protein_recovery]
    pipeline, encoder = load_orac_model()
    cats = encoder.categories_[0]
    row = np.zeros(len(ORAC_FEATURE_ORDER) + len(cats))
    row[:len(ORAC_FEATURE_ORDER)] = orac_row
    row[len(ORAC_FEATURE_ORDER) + list(cats).index(enzyme)] = 1.0
    orac_pred = float(pipeline.predict(pd.DataFrame([row], columns=ORAC_FEATURE_ORDER + [f"Enzyme_{c}" for c in cats]))[0])
    return {
        "enzyme": enzyme,
        "material": material,
        "calibration_status": "fitted" if fitted else "prior",
        "tolerance_DH_pts": TOL_PREDICTIVE if fitted else TOL_PRIOR,
        "fit_tolerance_DH_pts": TOL_FIT if fitted else None,
        "final_DH_pred": round(final_dh, 2),
        "dh_curve": np.round(dh, 3),
        "t_eval": t_eval,
        "ORAC_pred": round(float(orac_pred), 1),
        "orac_note": orac_note,
    }


def get_default_protein_recovery():
    global DEFAULT_PROTEIN_RECOVERY
    if DEFAULT_PROTEIN_RECOVERY is None:
        main = pd.read_csv(DATA_DIR / "main_batch_clean.csv")
        DEFAULT_PROTEIN_RECOVERY = float(main["ProteinRecovery_pct"].median())
    return DEFAULT_PROTEIN_RECOVERY


def run_confirmation(measured_path=None, out_path=None):
    """Judge ONLY completed runs; pending template rows are counted, never scored."""
    measured_path = Path(measured_path) if measured_path else CAMPAIGN_DIR / "measured_runs.csv"
    out_path = Path(out_path) if out_path else CONFIRM_REPORT
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# Twin Confirmation Report", ""]
    lines.append(f"Generated: {pd.Timestamp.now():%Y-%m-%d %H:%M}")
    lines.append("")
    if not measured_path.exists():
        lines.append(f"Measured file missing: `{measured_path}`.")
        lines.append("Rows: BatchID, RawMaterial, Enzyme, EnzymeToSubstrateRatio, SubstrateConc_gL,")
        lines.append("Temp_C, pH, Duration_min, Moisture_pct, CrudeProtein_pct, CrudeLipid_pct,")
        lines.append("Ash_pct, Hydroxyproline_pct, Collagen_pct, FinalDH_pct [, ORAC]")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Confirmation report: {out_path} (measured file missing)")
        return

    raw = read_raw_csv(measured_path)
    if "FinalDH_pct" not in raw.columns:
        raise ValueError(f"{measured_path} has no FinalDH_pct column")
    done = raw[raw["FinalDH_pct"].notna()].copy()
    n_pending = len(raw) - len(done)

    if done.empty:
        lines.append(f"No measured runs yet - 0 of {len(raw)} campaign runs returned.")
        lines.append("")
        lines.append("A run enters this report only once its `FinalDH_pct` is filled;")
        lines.append("pending template rows are never scored as failures.")
        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Confirmation report: {out_path} (0 measured, {n_pending} pending)")
        return

    lines.append(f"Bands: new-run predictive +/-{TOL_PREDICTIVE} DH "
                 f"(2 x pooled within-condition SD, the internal noise-floor notes);")
    lines.append(f"curve interpolation +/-{TOL_FIT} DH. A pass means 'inside the predictive band',")
    lines.append("not 'validated'.")
    lines.append("")
    lines.append("| BatchID | Enzyme | status | twin DH | measured DH | diff | tol | verdict | ORAC twin | ORAC measured |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    n_pass = n_bad = 0
    for row in done.itertuples():
        try:
            fdh = float(row.FinalDH_pct)
        except (TypeError, ValueError):
            lines.append(
                f"| {row.BatchID} | {row.Enzyme} | invalid | n/a | {row.FinalDH_pct!r} | "
                f"n/a | n/a | INVALID FinalDH | n/a | n/a |")
            n_bad += 1
            continue
        pred = predict_run(row.Enzyme, row.RawMaterial, float(row.Temp_C), float(row.pH),
                           float(row.Duration_min), float(row.SubstrateConc_gL),
                           float(row.EnzymeToSubstrateRatio))
        if "error" in pred:
            lines.append(
                f"| {row.BatchID} | {row.Enzyme} | error | n/a | {fdh:.1f} | n/a | n/a | "
                f"twin error: {pred['error']} | n/a | n/a |")
            n_bad += 1
            continue
        diff = abs(pred["final_DH_pred"] - fdh)
        verdict = "pass" if diff <= pred["tolerance_DH_pts"] else "FLAG (re-check)"
        if diff <= pred["tolerance_DH_pts"]:
            n_pass += 1

        orac_m = None
        if "ORAC" in done.columns:
            v = getattr(row, "ORAC", None)
            if isinstance(v, str) and v:
                try:
                    orac_m = float(v)
                except ValueError:
                    orac_m = None
        orac_m_s = f"{orac_m:.1f}" if orac_m is not None else "n/a"
        lines.append(
            f"| {row.BatchID} | {row.Enzyme} | {pred['calibration_status']} | "
            f"{pred['final_DH_pred']:.1f} | {fdh:.1f} | {diff:.1f} | "
            f"{pred['tolerance_DH_pts']:.0f} | {verdict} | {pred['ORAC_pred']:.0f} | {orac_m_s} |")
    lines.append("")
    lines.append(f"Pass: {n_pass}/{len(done)} measured "
                 f"({n_pending} pending, {n_bad} invalid)")
    lines.append("")
    lines.append("Verification plan: once the best conditions from the active loop are known,")
    lines.append("run a confirmatory triplicate; mean replicate DH vs twin prediction must fall")
    lines.append("inside the tolerance for a pass verdict.")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Confirmation report: {out_path} "
          f"(pass {n_pass}/{len(done)} measured, {n_pending} pending, {n_bad} invalid)")


def main():
    demo = pd.read_csv(CAMPAIGN_DIR / "campaign_design.csv")
    for batch in ["CAMPAIGN_001", "CAMPAIGN_008", "CAMPAIGN_013"]:
        r = demo[demo["BatchID"] == batch].iloc[0]
        pred = predict_run(r["Enzyme"], r["RawMaterial"], r["Temp_C"], r["pH"],
                           r["Duration_min"], r["SubstrateConc_gL"],
                           r["EnzymeToSubstrateRatio"])
        print(f"{batch} {r['Enzyme']:<22} [{pred['calibration_status']}]  "
              f"predDH={pred['final_DH_pred']:.1f}% ORAC={pred['ORAC_pred']:.0f}{pred['orac_note']}")
    run_confirmation()


if __name__ == "__main__":
    main()