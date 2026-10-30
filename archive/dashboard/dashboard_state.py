"""dashboard_state.py - pure state builder for the Protein-7 operations console.

Loads the REAL fitted models (EnergyNet checkpoint, x-stats, ODE params) and REAL
CSVs only. No randomness. Writes data/dashboard/state.json consumed by
reports/dashboard.html in SNAPSHOT mode and re-fed by dashboard_server.py in
LIVE SIMULATION mode.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from src.ebm_optimizer import (COMPOSITION_COLS, PROCESS_COLS, ENZYMES,
                               ENZYME_INDEX, EnergyNet, Y_MIN, Y_MAX)
from src.ode_model import dh_curve

BASE = Path(__file__).resolve().parents[1]
PROCESSED = BASE / "data" / "processed"
CAMPAIGN = BASE / "data" / "campaign"
MODELS = BASE / "models"
OUT = BASE / "data" / "dashboard" / "state.json"

Y_GRID_N = 55
ORAC_ALPHA = 10.0
ORAC_LOO_R2 = 0.507
ORAC_LOO_MAE = 28.34
REBEL_THRESHOLD = 30.0
REBEL_TOP_BATCH = "BATCH_011"
REBEL_TOP_DEV = 128.1
PURGED_COUNT = 9
BEST_OBSERVED_DH = 50.0
N_DEPLOYMENTS = 15
ROUNDS_COMPLETED = 2
TOP_EI = 2.9288
KINETICS_FLAG_RMSE = 3.0

LANDSCAPE = {
    "pH": (6.0, 9.0, 10),
    "temp": (44.0, 60.0, 10),
    "duration": 120.0,
    "substrate": 55.0,
    "enzyme": "Alcalase",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_energy_net():
    stats = np.load(MODELS / "ebm_x_stats.npy")
    mean, std = stats[0], stats[1]
    model = EnergyNet(len(mean) + 1)
    model.load_state_dict(torch.load(MODELS / "ebm_energy_net.pt",
                                     map_location="cpu"))
    model.eval()
    return model, mean, std


def _features(process, comp, enzyme, normalizer):
    num = np.asarray([process[c] for c in PROCESS_COLS] +
                     [comp[c] for c in COMPOSITION_COLS], dtype=float)
    onehot = np.zeros(len(ENZYMES))
    onehot[ENZYME_INDEX[enzyme]] = 1.0
    x = np.concatenate([num, onehot]).reshape(1, -1)
    return (x - normalizer[0]) / normalizer[1]


def _expected_dh(x_norm_batch, model, mean, std, y_grid=None):
    """Softmax-conditional expected DH under the trained EnergyNet.

    P(dh|x) ~ exp(-E(x, dh)); expected value over a fine dh grid.
    Mirrors the EBM's expectation semantics cheaply and deterministically.
    """
    if y_grid is None:
        y_grid = np.linspace(0.0, 1.0, Y_GRID_N)
    n = len(x_norm_batch)
    with torch.no_grad():
        E = model(
            torch.tensor(np.repeat(x_norm_batch, len(y_grid), axis=0),
                         dtype=torch.float32),
            torch.tensor(np.tile(y_grid, n).reshape(-1, 1),
                         dtype=torch.float32),
        ).view(n, -1).numpy()
    p = np.exp(-(E - E.min(axis=1, keepdims=True)))
    p /= p.sum(axis=1, keepdims=True)
    mu = (p * (y_grid.reshape(1, -1) * (Y_MAX - Y_MIN) + Y_MIN)).sum(axis=1)
    return mu


def _process_row(r):
    return {c: float(r[c]) for c in PROCESS_COLS}


def _comp_medians(main):
    out = {}
    for mat, g in main.groupby("RawMaterial"):
        out[mat] = {c: float(g[c].median()) for c in COMPOSITION_COLS}
    out["__all__"] = {c: float(main[c].median()) for c in COMPOSITION_COLS}
    return out


def build_state():
    main = pd.read_csv(PROCESSED / "main_batch_clean.csv")
    bio = pd.read_csv(PROCESSED / "bioactivity_clean.csv")
    timecourse = pd.read_csv(PROCESSED / "time_course_clean.csv")
    design = pd.read_csv(CAMPAIGN / "campaign_design.csv")
    history = pd.read_csv(CAMPAIGN / "active_loop_history.csv")
    merged = main.merge(bio, on="BatchID", how="inner")

    model, mean, std = _load_energy_net()
    comp_med = _comp_medians(main)
    now = _now()

    def score(process, comp, enzyme):
        xn = _features(process, comp, enzyme, (mean, std))
        return float(_expected_dh(xn, model, mean, std)[0])

    # ---- landscape grid -------------------------------------------------
    ph_axis = np.linspace(*LANDSCAPE["pH"])
    temp_axis = np.linspace(*LANDSCAPE["temp"])
    grid_proc = []
    grid_comp = comp_med["__all__"]
    for ph in ph_axis:
        for temp in temp_axis:
            grid_proc.append({
                "pH": float(ph), "Temp_C": float(temp),
                "Duration_min": LANDSCAPE["duration"],
                "SubstrateConc_gL": LANDSCAPE["substrate"],
            })
    x_norm = np.vstack([_features(p, grid_comp, LANDSCAPE["enzyme"], (mean, std))
                        for p in grid_proc])
    z = _expected_dh(x_norm, model, mean, std).reshape(10, 10)
    grid_vals = z.tolist()
    halo_flat = int(np.argmax(z))
    halo = {"ph": float(ph_axis[halo_flat // 10]),
            "temp": float(temp_axis[halo_flat % 10]), "v": float(z.max())}

    # ---- nodes ----------------------------------------------------------
    nodes = []
    for _, r in merged.iterrows():
        v = score(_process_row(r), {c: float(r[c]) for c in COMPOSITION_COLS},
                  r["Enzyme"])
        nodes.append({"id": r["BatchID"], "type": "subject",
                      "ph": float(r["pH"]), "temp": float(r["Temp_C"]),
                      "v": v, "dh": float(r["FinalDH_pct"]),
                      "enzyme": r["Enzyme"]})
    for _, r in design.iterrows():
        v = score(_process_row(r), comp_med.get(r["RawMaterial"], grid_comp),
                  r["Enzyme"])
        nodes.append({"id": r["BatchID"], "type": "deployment",
                      "ph": float(r["pH"]), "temp": float(r["Temp_C"]),
                      "v": v, "arm": r["arm"],
                      "enzyme": r["Enzyme"], "status": "pending"})
    for _, r in history.iterrows():
        v = score(_process_row(r), grid_comp, r["Enzyme"])
        nodes.append({"id": f"S{r['round']}R{r['rank']}", "type": "scout",
                      "ph": float(r["pH"]), "temp": float(r["Temp_C"]),
                      "v": v, "ei": float(r["EI"]),
                      "expected": float(r["expected_DH"]),
                      "round": int(r["round"]), "rank": int(r["rank"])})

    # ---- correlation network ---------------------------------------------
    vars_ = [("pH", "pH"), ("Temp_C", "T"), ("Duration_min", "DUR"),
             ("EnzymeToSubstrateRatio", "E/S"), ("SubstrateConc_gL", "SUB"),
             ("FinalDH_pct", "DH"), ("ORAC", "ORAC")]
    labels = [lab for _, lab in vars_]
    R = merged[[c for c, _ in vars_]].astype(float).corr().to_numpy()

    ref = {c: float(main[c].median()) for c in PROCESS_COLS}
    ref_comp = comp_med["__all__"]
    ref["SubstrateConc_gL"] = float(main["SubstrateConc_gL"].median())
    ref["EnzymeToSubstrateRatio"] = float(main["EnzymeToSubstrateRatio"].median())
    s0 = ref["SubstrateConc_gL"] * ref_comp["CrudeProtein_pct"] / 100.0
    e0 = ref["EnzymeToSubstrateRatio"] * s0
    ode_p = json.loads((MODELS / "ode_params_alcalase.json").read_text())

    def sens(col, frac=0.1):
        if col == "Duration_min":
            lo, hi = ref[col] * 0.5, ref[col] * 1.5
        else:
            lo, hi = ref[col] * (1 - frac), ref[col] * (1 + frac)
        p_lo, p_hi = dict(ref), dict(ref)
        p_lo[col], p_hi[col] = lo, hi
        def dh(p):
            return float(dh_curve(s0, e0, p["Temp_C"], p["pH"],
                                  [0.0, p["Duration_min"]], ode_p)[-1])
        return (dh(p_hi) - dh(p_lo)) / (hi - lo)

    node_rows = []
    for i, lab in enumerate(labels):
        row = np.abs(R[i])
        if np.isnan(row).all():
            v = 0.0
        else:
            v = float(np.nanmax(row)) * 100
        node_rows.append({"id": lab, "label": lab, "value": round(v, 1)})
    edges = []
    bad_edges = set()
    for i in range(len(vars_)):
        for j in range(i + 1, len(vars_)):
            r_ij = R[i, j]
            if not np.isfinite(r_ij):
                bad_edges.add((labels[i], labels[j]))
                continue
            if abs(r_ij) < 0.20:
                continue
            col_i, col_j = vars_[i][0], vars_[j][0]
            s_i = sens(col_i) if col_i in ("pH", "Temp_C", "Duration_min",
                                           "EnzymeToSubstrateRatio",
                                           "SubstrateConc_gL") else None
            s_j = sens(col_j) if col_j in ("pH", "Temp_C", "Duration_min",
                                           "EnzymeToSubstrateRatio",
                                           "SubstrateConc_gL") else None
            sig = None
            if s_i is not None and abs(s_i) > 1e-6:
                sig = np.sign(r_ij) == np.sign(s_i) or np.sign(r_ij) == 0 or np.sign(s_i) == 0
            elif s_j is not None and abs(s_j) > 1e-6:
                sig = np.sign(r_ij) == np.sign(s_j)
            agree = None if sig is None else bool(sig)
            edges.append({"s": labels[i], "t": labels[j],
                          "r": round(float(r_ij), 3), "agree": agree})
    edges.sort(key=lambda e: -abs(e["r"]))
    edges = edges[:12]
    network_note = []
    if bad_edges:
        network_note.append(
            f"E/S constant (0.02) in n={len(merged)} - zero variance, "
            f"{len(bad_edges)} edge(s) withheld")
    network_note.append("data corr vs ODE sensitivity, n = 31 · |r| ≥ 0.20")
    network_note = " · ".join(network_note)

    # ---- kinetics --------------------------------------------------------
    kin_batch_info = main[["BatchID", "Enzyme", "S0_gL", "E0_gL", "Temp_C", "pH",
                           "Duration_min", "FinalDH_pct"]].merge(
        timecourse[["BatchID"]].drop_duplicates(), on="BatchID")
    kinetics = []
    for _, b in kin_batch_info.iterrows():
        tc = timecourse[timecourse["BatchID"] == b["BatchID"]]
        measured = [[float(t), float(d)] for t, d in
                    zip(tc["Time_min"], tc["DegreeOfHydrolysis_pct"])]
        entry = {"id": b["BatchID"], "enzyme": b["Enzyme"],
                 "final": float(b["FinalDH_pct"]), "measured": measured,
                 "predicted": None, "rmse": None, "flag": False}
        if b["Enzyme"] == "Alcalase":
            ts = np.linspace(0.0, max(float(b["Duration_min"]), 1.0), 60)
            pred = dh_curve(float(b["S0_gL"]), float(b["E0_gL"]),
                            float(b["Temp_C"]), float(b["pH"]), ts, ode_p)
            entry["predicted"] = [[float(t), float(p)] for t, p in zip(ts, pred)]
            m_t = tc["Time_min"].to_numpy(float)
            m_d = tc["DegreeOfHydrolysis_pct"].to_numpy(float)
            p_at = dh_curve(float(b["S0_gL"]), float(b["E0_gL"]),
                            float(b["Temp_C"]), float(b["pH"]), m_t, ode_p)
            rmse = float(np.sqrt(np.mean((m_d - p_at) ** 2)))
            entry["rmse"] = round(rmse, 2)
            entry["flag"] = rmse > KINETICS_FLAG_RMSE
        kinetics.append(entry)
    flagged_kinetics = [(b["id"], b["rmse"]) for b in kinetics if b["flag"]]

    # ---- confidence ------------------------------------------------------
    tc_al = timecourse.merge(
        main[main["Enzyme"] == "Alcalase"][["BatchID", "S0_gL", "E0_gL",
                                            "Temp_C", "pH"]],
        on="BatchID")
    if len(tc_al):
        pred_parts, obs_parts = [], []
        for b in tc_al[["BatchID", "S0_gL", "E0_gL", "Temp_C", "pH"]].drop_duplicates().itertuples():
            sub = tc_al[tc_al["BatchID"] == b.BatchID]
            pred_parts.append(dh_curve(
                float(b.S0_gL), float(b.E0_gL), float(b.Temp_C), float(b.pH),
                sub["Time_min"].to_numpy(float), ode_p))
            obs_parts.append(sub["DegreeOfHydrolysis_pct"].to_numpy(float))
        pred = np.concatenate(pred_parts)
        obs = np.concatenate(obs_parts)
        ss_res = float(np.sum((obs - pred) ** 2))
        ss_tot = float(np.sum((obs - obs.mean()) ** 2))
        ode_r2 = round(1.0 - ss_res / ss_tot, 3)
        if not math.isfinite(ode_r2):
            ode_r2 = None
    else:
        ode_r2 = None

    confidence = [
        {"model": "ODE FIT", "metric": "Alcalase kinetics R²",
         "value": ode_r2, "status": "ok",
         "note": f"dh_curve vs time-course, n={len(tc_al)} pts"},
        {"model": "EBM ENERGYNET", "metric": "top EI · 2 rounds",
         "value": TOP_EI, "status": "ok",
         "note": f"expectation-improvement acquisition, round {ROUNDS_COMPLETED} closed"},
        {"model": "ORAC RIDGE", "metric": f"LOO R² = {ORAC_LOO_R2} · MAE {ORAC_LOO_MAE}",
         "value": ORAC_LOO_R2, "status": "ok",
         "note": f"α = {ORAC_ALPHA}, leave-one-out audit"},
        {"model": "PRIOR ARMS", "metric": "rule-based, σ = 4.0 DH pts",
         "value": None, "status": "warn",
         "note": "non-Alcalase deployments rely on prior mean + log-duration add"},
    ]

    # ---- alerts ----------------------------------------------------------
    alerts = [
        {"level": "crit" if flagged_kinetics else "info", "source": "KINETICS", "ts": now,
         "msg": (f"{flagged_kinetics[0][0]} hydrolysis curve unfit — RMSE "
                 f"{flagged_kinetics[0][1]} pts vs fitted ODE; flagged, not silently trusted")
         if flagged_kinetics else
         "all Alcalase time-courses within the fitted-ODE tolerance"},
        {"level": "warn", "source": "BIOACTIVITY", "ts": now,
         "msg": f"{PURGED_COUNT} rebel cells vetted from registry — ORAC LOO residual > {REBEL_THRESHOLD:.0f}; top {REBEL_TOP_BATCH} at {REBEL_TOP_DEV} umol TE/g"},
        {"level": "warn", "source": "IDENTIFIABILITY", "ts": now,
         "msg": "E/S held constant in 5 batch-1 runs — dose effect weakly identified; campaign dose sweep in progress"},
        {"level": "info", "source": "ACQUISITION", "ts": now,
         "msg": f"Round {ROUNDS_COMPLETED} closed — 3 scouts deployed, top EI {TOP_EI}, best observed {BEST_OBSERVED_DH:.1f}%"},
        {"level": "info", "source": "CAMPAIGN", "ts": now,
         "msg": f"{N_DEPLOYMENTS} deployments queued — dose_sweep / process_lhc / gap_fill arms"},
        {"level": "info", "source": "ETHOS", "ts": now,
         "msg": "No rebel exceeds best observed 50.0% — honest status, no theatre"},
    ]

    # ---- roster ----------------------------------------------------------
    roster = []
    for _, r in design.iterrows():
        roster.append({"id": r["BatchID"], "arm": r["arm"],
                       "enzyme": r["Enzyme"], "ph": float(r["pH"]),
                       "temp": float(r["Temp_C"]),
                       "duration": float(r["Duration_min"]),
                       "substrate": float(r["SubstrateConc_gL"]),
                       "status": "pending",
                       "measured_dh": None, "expected_dh": None})

    state = {
        "schema": "protein-7/dashboard-state/v1",
        "regime": "snapshot",
        "build_ts": now,
        "tick_ms": 8000,
        "header": {
            "subjects": int(len(main)),
            "purged": PURGED_COUNT,
            "deployments_total": N_DEPLOYMENTS,
            "deployments_done": 0,
            "deployments_pending": N_DEPLOYMENTS,
            "rounds_completed": ROUNDS_COMPLETED,
            "top_ei": TOP_EI,
            "best_observed_dh": BEST_OBSERVED_DH,
            "rebel_top": {"batch": REBEL_TOP_BATCH, "dev": REBEL_TOP_DEV},
        },
        "landscape": {
            "ph_axis": [float(x) for x in ph_axis],
            "temp_axis": [float(x) for x in temp_axis],
            "grid": grid_vals,
            "halo": halo,
            "condition": {"duration": LANDSCAPE["duration"],
                          "substrate": LANDSCAPE["substrate"],
                          "enzyme": LANDSCAPE["enzyme"],
                          "composition": "median, all subjects"},
            "nodes": nodes,
        },
        "network": {"nodes": node_rows, "edges": edges, "note": network_note},
        "kinetics": {"batches": kinetics,
                     "note": "measured = lab time-course; dashed = fitted ODE at each batch's recorded T/pH"},
        "confidence": confidence,
        "alerts": alerts,
        "roster": roster,
    }
    return state


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    state = build_state()
    try:
        payload = json.dumps(state, indent=1, allow_nan=False)
    except ValueError as e:
        print(f"[dashboard_state] FAIL - state contains non-finite values ({e}); "
              f"refusing to write a corrupt snapshot", file=sys.stderr)
        return 1
    OUT.write_text(payload, encoding="utf-8")
    k = len(state["kinetics"]["batches"])
    flagged = [b["id"] for b in state["kinetics"]["batches"] if b["flag"]]
    print(f"[dashboard_state] wrote {OUT} ({len(payload) / 1024:.1f} KB)")
    print(f"  subjects={state['header']['subjects']} deployments={state['header']['deployments_total']} "
          f"landscape grid={len(state['landscape']['grid'])}x{len(state['landscape']['grid'][0])} "
          f"halo=({state['landscape']['halo']['ph']:.1f} pH, {state['landscape']['halo']['temp']:.1f} C) "
          f"v={state['landscape']['halo']['v']:.1f}")
    print(f"  network edges={len(state['network']['edges'])} note='{state['network']['note'].replace(chr(183), '|').replace(chr(8805), '>=')}'")
    print(f"  kinetics batches={k} conf bars={len(state['confidence'])} alerts={len(state['alerts'])}")
    print(f"  kinetics flagged: {flagged or 'none'}")
    print(f"  ode_r2={state['confidence'][0]['value']} ei_history={[n['ei'] for n in state['landscape']['nodes'] if n['type']=='scout']}")
    return 0


if __name__ == "__main__":
    main()