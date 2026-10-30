import numpy as np
from scipy.optimize import minimize

from src.ode_model import DEFAULT_PARAMS, dh_curve
from src.calibrate_ode import load_batches, unpack, pack

N_SCALE_RESTARTS = 10
SEED = 0


def loss_scaled(x, batches):
    globals_p = unpack(x[:4])
    scale = np.exp(x[4:])
    tot, n = 0.0, 0
    for b, s in zip(batches, scale):
        dh = dh_curve(b["S0"], b["E0"] * s, b["T"], b["pH"], b["t"], globals_p)
        tot += float(np.sum((dh - b["dh_obs"]) ** 2))
        n += len(b["t"])
    return tot / n


def main():
    batches = load_batches()
    rng = np.random.default_rng(SEED)
    best = None
    for i in range(N_SCALE_RESTARTS):
        x0 = np.concatenate([pack(DEFAULT_PARAMS), np.zeros(len(batches))])
        if i > 0:
            x0[:4] = rng.uniform(-6, 3, 4)
            x0[4:] = rng.uniform(-3, 3, len(batches))
        bounds = [(-8, 6), (-7, 6), (-7, 6), (-14, 0)] + [(-6, 6)] * len(batches)
        res = minimize(loss_scaled, x0, method="L-BFGS-B", bounds=bounds, args=(batches,))
        if best is None or res.fun < best.fun:
            best = res
    gp = unpack(best.x[:4])
    scale = np.exp(best.x[4:])
    print(f"scaled-loss: {best.fun:.3f}  (unscaled was 21.99 DH%^2)")
    print(f"{'batch':<10}{'E0':>8}{'rel_activity':>13}{'eff_E0':>9}")
    for b, s in zip(batches, scale):
        print(f"{b['id']:<10}{b['E0']:>8.3f}{s:>13.3f}{b['E0']*s:>9.3f}")
    print("global params:")
    for k in ["kcat_ref", "Km", "Ki", "kd_ref"]:
        print(f"  {k} = {gp[k]:.5g}")


if __name__ == "__main__":
    main()