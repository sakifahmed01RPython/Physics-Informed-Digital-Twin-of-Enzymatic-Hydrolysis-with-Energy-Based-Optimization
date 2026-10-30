from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import qmc

DATA_DIR = Path("data/processed")
OUT_DIR = Path("data/campaign")
FIXED_E_S = 0.02
SUBSTRATE_DEFAULT = 50.0
SEED = 7
N_PROCESS_ARH = 5
N_DOSE_ARM = 3
DOSE_VALUES = [0.01, 0.04, 0.06]

N_X_MINOR = 3

ENZYME_WINDOWS = {
    "Pepsin": ("pH", 2.0, 3.5, "Temp_C", 35, 40),
    "Flavourzyme": ("pH", 6.0, 8.0, "Temp_C", 45, 55),
    "Alcalase+Kojizyme": ("pH", 7.0, 8.5, "Temp_C", 50, 60),
    "Alcalase+Neutrase": ("pH", 7.0, 8.0, "Temp_C", 48, 55),
    "Alcalase+Flavourzyme": ("pH", 7.0, 8.0, "Temp_C", 50, 58),
}

MATERIAL_POOL = ["cod_frames", "salmon_trimmings", "cod_frames", "salmon_frames"]


def lhc_points(n, lo, hi, seed):
    sampler = qmc.LatinHypercube(d=2, seed=seed)
    u = sampler.random(n)
    ph = lo[0] + u[:, 0] * (hi[0] - lo[0])
    t = lo[1] + u[:, 1] * (hi[1] - lo[1])
    return ph, t


def main():
    OUT_DIR.mkdir(exist_ok=True)
    main_df = pd.read_csv(DATA_DIR / "main_batch_clean.csv")
    counts = main_df["Enzyme"].value_counts().to_dict()
    rng = np.random.default_rng(SEED)
    rows = []
    idx = 1

    def add(enzyme, ph, t, dur, sub, e_s, material, arm, note):
        nonlocal idx
        rows.append({
            "BatchID": f"CAMPAIGN_{idx:03d}",
            "Enzyme": enzyme,
            "pH": round(float(ph), 2),
            "Temp_C": round(float(t), 1),
            "Duration_min": int(dur),
            "SubstrateConc_gL": float(sub),
            "EnzymeToSubstrateRatio": e_s,
            "RawMaterial": material,
            "arm": arm,
            "note": note,
        })
        idx += 1

    gap_slots = {e: max(0, N_X_MINOR - counts.get(e, 0)) for e in ENZYME_WINDOWS}
    for enzyme, need in gap_slots.items():
        lo_pH, hi_pH, lo_T, hi_T = ENZYME_WINDOWS[enzyme][1], ENZYME_WINDOWS[enzyme][2], \
                                   ENZYME_WINDOWS[enzyme][4], ENZYME_WINDOWS[enzyme][5]
        phs, ts = lhc_points(need, (lo_pH, lo_T), (hi_pH, hi_T), SEED + idx)
        for k in range(need):
            mat = MATERIAL_POOL[int(rng.integers(0, len(MATERIAL_POOL)))]
            dur = int(rng.integers(60, 300))
            add(enzyme, phs[k], ts[k], dur, SUBSTRATE_DEFAULT, FIXED_E_S, mat,
                "gap_fill", f"raise {enzyme} rows to n>={N_X_MINOR}")

    phs, ts = lhc_points(N_PROCESS_ARH, (7.0, 50.0), (9.0, 60.0), SEED + 500)
    mats = ["salmon_frames", "cod_frames", "salmon_trimmings", "cod_heads", "herring_byproduct"]
    for k in range(N_PROCESS_ARH):
        dur = int(rng.integers(60, 300))
        sub = float(rng.uniform(30, 70))
        add("Alcalase", phs[k], ts[k], dur, sub, FIXED_E_S, mats[k],
            "process_lhc", f"process space; material gap {mats[k]}")

    for k, e_s in enumerate(DOSE_VALUES):
        add("Alcalase", float(rng.uniform(7.5, 8.5)), float(rng.uniform(53, 57)),
            120, SUBSTRATE_DEFAULT, e_s, "salmon_frames", "dose_sweep",
            f"weighed enzyme charge E/S={e_s}; restores dose identifiability")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_DIR / "campaign_design.csv", index=False)

    new_counts = counts.copy()
    for e in df["Enzyme"]:
        new_counts[e] = new_counts.get(e, 0) + 1
    print(f"Runs: {len(df)}")
    print("Projected enzyme rows (existing + campaign):")
    for e, n in sorted(new_counts.items()):
        flag = "" if n >= N_X_MINOR else "  <-- still below threshold"
        print(f"  {e:<24} {n}{flag}")
    print("\nArms:")
    print(df["arm"].value_counts().to_string())
    print("\nSample:")
    print(df.head(6).to_string(index=False))
    print(f"\nSaved: {OUT_DIR / 'campaign_design.csv'}")


if __name__ == "__main__":
    main()