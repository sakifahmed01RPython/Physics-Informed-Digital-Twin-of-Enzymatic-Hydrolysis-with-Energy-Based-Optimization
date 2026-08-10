import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.ode_model import dh_curve, DEFAULT_PARAMS

DATA_DIR = Path("data/processed")
MODEL_DIR = Path("models")
ENZYME = "Alcalase"

FIT_KEYS = ["kcat_ref", "Km", "Ki", "kd_ref", "sub_act_heads"]
BOUNDS_LOG = {
    "kcat_ref": (-8.0, 6.0),
    "Km": (-7.0, 6.0),
    "Ki": (-7.0, 6.0),
    "kd_ref": (-14.0, 0.0),
    "sub_act_heads": (-2.5, 2.5),
}
N_RESTARTS = 8
SEED = 42


def load_batches():
    main = pd.read_csv(DATA_DIR / "main_batch_clean.csv")
    tc = pd.read_csv(DATA_DIR / "time_course_clean.csv")
    sel = main[main["Enzyme"] == ENZYME]
    batches = []
    for row in sel.itertuples():
        curve = tc[tc["BatchID"] == row.BatchID].sort_values("Time_min")
        if len(curve) == 0:
            continue
        batches.append({
            "id": row.BatchID,
            "S0": float(row.S0_gL),
            "E0": float(row.E0_gL),
            "T": float(row.Temp_C),
            "pH": float(row.pH),
            "heads": str(row.RawMaterial) == "cod_heads",
            "t": curve["Time_min"].to_numpy(),
            "dh_obs": curve["DegreeOfHydrolysis_pct"].to_numpy(),
        })
    return batches


def predict(batches, params):
    out = []
    for b in batches:
        p = dict(params)
        if b["heads"]:
            p["kcat_ref"] = p["kcat_ref"] * p["sub_act_heads"]
        out.append(dh_curve(b["S0"], b["E0"], b["T"], b["pH"], b["t"], p))
    return out


def mse_loss(batches, params):
    total, n = 0.0, 0
    for b, dh in zip(batches, predict(batches, params)):
        total += float(np.sum((dh - b["dh_obs"]) ** 2))
        n += len(b["t"])
    return total / n


def unpack(x):
    p = dict(DEFAULT_PARAMS)
    for key, val in zip(FIT_KEYS, x):
        p[key] = np.exp(val)
    return p


def pack(params):
    return np.array([np.log(params[k]) for k in FIT_KEYS])


def fit(batches):
    rng = np.random.default_rng(SEED)
    best = None
    for i in range(N_RESTARTS):
        if i == 0:
            x0 = pack(DEFAULT_PARAMS)
        else:
            x0 = np.array([
                rng.uniform(*BOUNDS_LOG[k]) for k in FIT_KEYS
            ])
        res = minimize(
            lambda x: mse_loss(batches, unpack(x)),
            x0,
            method="L-BFGS-B",
            bounds=[BOUNDS_LOG[k] for k in FIT_KEYS],
            options={"maxiter": 400},
        )
        if best is None or res.fun < best.fun:
            best = res
    return unpack(best.x), best.fun


def report(batches, params):
    print(f"{'Batch':<10}{'pts':>4}{'RMSE':>8}{'maxAE':>8}")
    for b in batches:
        dh = dh_curve(b["S0"], b["E0"], b["T"], b["pH"], b["t"], params)
        rmse = float(np.sqrt(np.mean((dh - b["dh_obs"]) ** 2)))
        maxae = float(np.max(np.abs(dh - b["dh_obs"])))
        print(f"{b['id']:<10}{len(b['t']):>4}{rmse:>8.2f}{maxae:>8.2f}")
    return None


def main():
    MODEL_DIR.mkdir(exist_ok=True)
    batches = load_batches()
    params, loss = fit(batches)
    report(batches, params)
    print(f"\nMSE loss: {loss:.3f} (DH %^2)")
    print("Fitted params:")
    for k in FIT_KEYS:
        print(f"  {k} = {params[k]:.5g}")
    print(f"  sub_act_heads = {params['sub_act_heads']:.3f} (kcat multiplier for cod_heads)")
    with open(MODEL_DIR / "ode_params_alcalase.json", "w") as f:
        json.dump(params, f, indent=2, default=float)
    print(f"Saved: {MODEL_DIR / 'ode_params_alcalase.json'}")


if __name__ == "__main__":
    main()