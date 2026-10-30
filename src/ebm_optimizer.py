import numpy as np
import pandas as pd
import torch
import torch.nn as nn

DATA_DIR = "data/processed"
MODEL_DIR = "models"

PROCESS_COLS = ["pH", "Temp_C", "Duration_min", "SubstrateConc_gL"]
DOSE_COL = "EnzymeToSubstrateRatio"
COMPOSITION_COLS = ["Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
                    "Hydroxyproline_pct", "Collagen_pct"]
# The EBM's numeric block.  E/S used to be excluded and every proposal was
# forced to 0.02, even though the real campaign has a three-arm dose sweep
# (0.01/0.04/0.06).  The benchmark showed that this made the loop unable to
# exploit the campaign's own dose factor.
MODEL_NUM_COLS = PROCESS_COLS + [DOSE_COL] + COMPOSITION_COLS
ENZYMES = ["Alcalase", "Alcalase+Flavourzyme", "Alcalase+Kojizyme", "Alcalase+Neutrase",
           "Flavourzyme", "Neutrase", "Pepsin"]
ENZYME_INDEX = {e: i for i, e in enumerate(ENZYMES)}

Y_MIN, Y_MAX = 0.0, 55.0
N_CHAINS = 4
N_LANGEVIN_STEPS = 120
N_EI_CANDIDATES = 500
EI_CHUNK = 64
MIN_CLASS_ROWS = 3
EPSILON = 0.05
SEED = 42

# Candidate-generation policy (step 5).  The original generator jittered every
# factor around a uniformly random training row, which is too diffuse when the
# EBM's EI ranking is weak.  The benchmark showed OFAT dominating that pool.
# The defaults below are a trust-region mixture: most candidates are local
# moves around the best measured runs, the rest explore all eligible rows.
BASE_TOP_K = 5
TOP_MIX = 0.6
LOCAL_JITTER = 0.025
GLOBAL_JITTER = 0.05
COORD_PROB = 0.7
DOSE_JITTER = 0.01

BOUNDS = {"pH": (2.0, 10.0), "Temp_C": (30.0, 60.0), "Duration_min": (15.0, 300.0),
          "SubstrateConc_gL": (30.0, 70.0)}
DOSE_BOUNDS = (0.01, 0.06)
DOSE_LEVELS = (0.01, 0.02, 0.04, 0.06)


def snap_dose(value):
    """Snap E/S to the four weighed dose levels used by the campaign design."""
    v = float(value)
    return float(min(DOSE_LEVELS, key=lambda x: abs(x - v)))


def feasible_mask(df):
    """Rows inside the acquisition box (the only conditions the EBM may propose)."""
    mask = np.ones(len(df), dtype=bool)
    for col, (lo, hi) in BOUNDS.items():
        vals = df[col].to_numpy(float)
        mask &= (vals >= lo) & (vals <= hi)
    if DOSE_COL in df.columns:
        vals = df[DOSE_COL].to_numpy(float)
        mask &= (vals >= DOSE_BOUNDS[0]) & (vals <= DOSE_BOUNDS[1])
    return mask


def feasible_y_best(df):
    """Best observed DH inside the acquisition box.

    The all-data best (50.0% at 720 min) is unreachable under the 15-300 min
    duration bound, so anchoring EI to it makes every improvement imaginary.
    """
    mask = feasible_mask(df)
    if not mask.any():
        return float(df["FinalDH_pct"].max())
    return float(df.loc[mask, "FinalDH_pct"].max())


class EnergyNet(nn.Module):
    def __init__(self, d_in):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(d_in, 32), nn.SiLU(),
            nn.Linear(32, 32), nn.SiLU(),
            nn.Linear(32, 1),
        )

    def forward(self, x, y):
        return self.net(torch.cat([x, y], dim=-1)).squeeze(-1)


class EBMOptimizer:
    def __init__(self, seed=SEED, chains=N_CHAINS,
                 langevin_steps=N_LANGEVIN_STEPS, ei_chunk=EI_CHUNK):
        self.rng = np.random.default_rng(seed)
        torch.manual_seed(seed)
        self.x_stats = None
        self.model = None
        # Acquisition cost is dominated by the sequential Langevin loop.  The
        # defaults preserve the production behaviour; the benchmark passes
        # smaller values and batches every candidate in a chunk.
        self.chains = int(chains)
        self.langevin_steps = int(langevin_steps)
        self.ei_chunk = int(ei_chunk)

    def load_data(self):
        main = pd.read_csv(f"{DATA_DIR}/main_batch_clean.csv")
        self.meta = main.copy()

    def make_x(self, df):
        num = df[MODEL_NUM_COLS].astype(float).to_numpy()
        onehot = np.zeros((len(df), len(ENZYMES)))
        for i, e in enumerate(df["Enzyme"]):
            onehot[i, ENZYME_INDEX[e]] = 1.0
        return np.concatenate([num, onehot], axis=1)

    def fit_x_stats(self, X):
        mean = X.mean(axis=0, keepdims=True)
        std = X.std(axis=0, keepdims=True)
        # A constant column (all historical E/S values are 0.02) has zero
        # standard deviation.  Dividing by 1e-9 turns a 0.06 proposal into a
        # 4e7 feature and destroys the model.  Use unit scale for constants;
        # the column is centred at zero and the model simply has no evidence
        # about it until the campaign provides dose variation.
        std = np.where(std < 1e-6, 1.0, std)
        self.x_stats = (mean, std)

    def normalize_x(self, X):
        return (X - self.x_stats[0]) / self.x_stats[1]

    def train(self, df, epochs=800, lr=1e-3, seed=None, n_grid=21, n_aug=10, aug_noise=0.12):
        if seed is not None:
            torch.manual_seed(seed)
        X = self.make_x(df)
        self.fit_x_stats(X)
        rng = np.random.default_rng(seed if seed is not None else 0)
        x_scale = X.std(axis=0, keepdims=True) + 1e-9
        X_aug = [X]
        y_base = df["FinalDH_pct"].to_numpy(float).reshape(-1, 1)
        y_aug = [y_base]
        for _ in range(n_aug):
            xj = X + rng.normal(0, aug_noise * 0.5, size=X.shape) * x_scale
            yj = y_base * (1.0 + rng.normal(0, aug_noise, size=y_base.shape))
            X_aug.append(xj)
            y_aug.append(np.clip(yj, Y_MIN * 0.5, Y_MAX))
        X = np.concatenate(X_aug, axis=0).astype(np.float32)
        y = ((np.concatenate(y_aug, axis=0) - Y_MIN) / (Y_MAX - Y_MIN)).astype(np.float32)
        Xn = self.normalize_x(X).astype(np.float32)
        d = Xn.shape[1] + 1
        self.model = EnergyNet(d)
        opt = torch.optim.Adam(self.model.parameters(), lr=lr, weight_decay=1e-3)
        y_grid = torch.linspace(0.0, 1.0, n_grid).reshape(1, n_grid, 1).expand(len(y), -1, -1)
        yt = torch.tensor(y).reshape(-1, 1, 1)
        grid = torch.cat([yt, y_grid], dim=1).reshape(len(y), n_grid + 1, 1)
        Xt = torch.tensor(np.repeat(Xn, n_grid + 1, axis=0))
        target = torch.zeros(len(y), dtype=torch.long)
        for epoch in range(epochs):
            opt.zero_grad()
            energies = self.model(Xt, grid.reshape(-1, 1)).view(len(y), n_grid + 1)
            loss = torch.nn.functional.cross_entropy(-energies, target)
            loss.backward()
            opt.step()
        return float(loss.detach())

    def energy(self, Xn, y_scaled):
        with torch.no_grad():
            return self.model(torch.tensor(Xn, dtype=torch.float32),
                              torch.tensor(y_scaled, dtype=torch.float32)).numpy()

    def _langevin_batch(self, X_norm, y0, noise, eps=EPSILON):
        """Run ``noise.shape[0]`` Langevin steps for a batch of chains.

        ``X_norm`` is (B, d), ``y0`` is (B, 1), and ``noise`` is
        (steps, B, 1).  Every chain is advanced in the same forward/backward
        pass.  The graph is detached at each step so memory stays flat.
        """
        if self.model is None:
            raise RuntimeError("train() must be called before sampling")
        e = float(np.sqrt(eps))
        xt = torch.tensor(np.asarray(X_norm, dtype=np.float32))
        yt = torch.tensor(np.asarray(y0, dtype=np.float32))
        noise_t = torch.from_numpy(np.asarray(noise, dtype=np.float32))
        for t in range(noise_t.shape[0]):
            yt = yt.detach().requires_grad_(True)
            energy = self.model(xt, yt)
            grad = torch.autograd.grad(energy.sum(), yt)[0]
            yt = (yt - (eps / 2.0) * grad + e * noise_t[t]).clamp(0.0, 1.0)
        return yt.detach().numpy()

    def langevin_samples(self, x_row_norm, k=N_CHAINS, steps=N_LANGEVIN_STEPS, eps=EPSILON):
        x = np.asarray(x_row_norm, dtype=float).reshape(1, -1)
        X = np.repeat(x, k, axis=0)
        y0 = self.rng.uniform(0.0, 1.0, (k, 1)).astype(np.float32)
        noise = self.rng.standard_normal((steps, k, 1)).astype(np.float32)
        draws = self._langevin_batch(X, y0, noise, eps).reshape(k, 1)
        return draws * (Y_MAX - Y_MIN)

    def ei(self, x_row_unnorm, y_best):
        xnn = self.normalize_x(np.asarray(x_row_unnorm, dtype=float).reshape(1, -1))
        samples = self.langevin_samples(xnn).flatten()
        interior = samples[(samples > 2.0) & (samples < 53.0)]
        if interior.size == 0:
            ei_val = 0.0
        else:
            ei_val = float(np.mean(np.maximum(interior - y_best, 0.0)))
        return ei_val, samples

    @staticmethod
    def _base_from_row(row):
        return ([row.pH, row.Temp_C, row.Duration_min, row.SubstrateConc_gL],
                float(row.EnzymeToSubstrateRatio),
                [getattr(row, c) for c in COMPOSITION_COLS],
                row.Enzyme, row.RawMaterial)

    def acquire(self, df_train, n_new=3, n_cand=N_EI_CANDIDATES, seed=None,
                min_class_rows=None, chains=None, langevin_steps=None,
                ei_chunk=None, base_top_k=None, top_mix=None,
                local_jitter=None, global_jitter=None, coord_prob=None,
                rank_mode="ei"):
        """Propose n_new experiments.

        ``min_class_rows`` is an experimental hook: the production default is
        MIN_CLASS_ROWS=3, but a benchmark ablation may set it to 1 to separate
        the eligibility guard from the candidate-generation policy.

        ``chains``, ``langevin_steps`` and ``ei_chunk`` override the instance
        defaults.  Candidates are sampled in chunks; all chains in a chunk are
        advanced in one autograd pass, which removes the per-candidate Python
        loop that made acquisition ~7 s per 150 candidates.

        Candidate generation is a trust-region mixture.  ``top_mix`` of the
        candidates are local moves around the ``base_top_k`` best measured rows
        (one coordinate at a time with probability ``coord_prob``); the rest
        jitter around all eligible rows.  ``rank_mode="random"`` is a
        development-only ablation: it uses the same candidate pool but picks
        proposals at random instead of by EI, so the benchmark can test whether
        the energy model's ranking adds anything.
        """
        if self.model is None:
            raise RuntimeError("train() must be called before acquire()")
        if len(df_train) == 0:
            raise ValueError("cannot acquire from an empty training frame")
        if rank_mode not in ("ei", "random"):
            raise ValueError("rank_mode must be 'ei' or 'random'")
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        min_rows = MIN_CLASS_ROWS if min_class_rows is None else int(min_class_rows)
        k = self.chains if chains is None else int(chains)
        steps = self.langevin_steps if langevin_steps is None else int(langevin_steps)
        chunk = self.ei_chunk if ei_chunk is None else int(ei_chunk)
        if k < 1 or steps < 1 or chunk < 1:
            raise ValueError("chains, langevin_steps and ei_chunk must be >= 1")
        top_k = BASE_TOP_K if base_top_k is None else int(base_top_k)
        mix = TOP_MIX if top_mix is None else float(top_mix)
        local = LOCAL_JITTER if local_jitter is None else float(local_jitter)
        broad = GLOBAL_JITTER if global_jitter is None else float(global_jitter)
        coord = COORD_PROB if coord_prob is None else float(coord_prob)
        if top_k < 1 or not (0.0 <= mix <= 1.0) or not (0.0 <= coord <= 1.0):
            raise ValueError("base_top_k must be >= 1; top_mix/coord_prob in [0, 1]")

        y_best = feasible_y_best(df_train)
        class_counts = df_train["Enzyme"].value_counts().to_dict()
        rng = self.rng
        eligible = [row for row in df_train.itertuples()
                    if class_counts.get(row.Enzyme, 0) >= min_rows]
        if not eligible:
            # The eligibility guard can exclude every enzyme when a class has
            # too few rows.  Falling back to all rows is safer than an empty
            # base list (which previously crashed with randint(0, 0)).
            eligible = list(df_train.itertuples())
        if not eligible:
            raise ValueError("no usable base rows for candidate generation")
        # Keep the measured DH alongside each base so the trust region can be
        # anchored on the best observed runs (including noisy gross errors,
        # which is what the lab would actually see).
        bases = sorted(((self._base_from_row(row), float(row.FinalDH_pct))
                        for row in eligible), key=lambda t: -t[1])
        top_bases = bases[:min(top_k, len(bases))]

        cand = []
        for _ in range(int(n_cand)):
            use_top = bool(rng.random() < mix)
            pool = top_bases if use_top else bases
            b, _y = pool[int(rng.integers(0, len(pool)))]
            scale = local if use_top else broad
            if use_top and rng.random() < coord:
                xn = list(b[0])
                idx = int(rng.integers(0, len(PROCESS_COLS)))
                col = PROCESS_COLS[idx]
                xn[idx] = float(np.clip(
                    xn[idx] + rng.normal(0, scale) * (BOUNDS[col][1] - BOUNDS[col][0]),
                    *BOUNDS[col]))
            else:
                xn = [float(np.clip(
                    b[0][i] + rng.normal(0, scale) * (BOUNDS[c][1] - BOUNDS[c][0]),
                    *BOUNDS[c]))
                    for i, c in enumerate(PROCESS_COLS)]
            es = snap_dose(np.clip(b[1] + rng.normal(0, DOSE_JITTER), *DOSE_BOUNDS))
            xc = [b[2][i] * (1.0 + rng.normal(0, 0.02))
                  for i in range(len(COMPOSITION_COLS))]
            cand.append((xn, es, xc, b[3], b[4]))
        if not cand:
            return []

        if rank_mode == "random":
            # Same candidate pool, random selection.  Use a separate RNG so
            # the pool is bit-identical to the EI run with the same seed.
            pick_rng = np.random.default_rng((seed if seed is not None else 0) + 777)
            picks = pick_rng.choice(len(cand), size=min(int(n_new), len(cand)),
                                    replace=False)
            return [{"EI": 0.0, "expected_DH": float("nan"),
                     "pH": cand[i][0][0], "Temp_C": cand[i][0][1],
                     "Duration_min": cand[i][0][2],
                     "SubstrateConc_gL": cand[i][0][3],
                     DOSE_COL: cand[i][1],
                     **{c: cand[i][2][j] for j, c in enumerate(COMPOSITION_COLS)},
                     "Enzyme": cand[i][3], "RawMaterial": cand[i][4]}
                    for i in picks]

        rows = []
        for xn, es, xc, enzyme, _material in cand:
            onehot = [1.0 if ENZYME_INDEX[enzyme] == i else 0.0
                      for i in range(len(ENZYMES))]
            rows.append(xn + [es] + xc + onehot)
        X_cand = self.normalize_x(np.asarray(rows, dtype=float)).astype(np.float32)

        # Draw all initial values and all Langevin noise up front.  This makes
        # the result independent of the chunk size, so --ei-chunk is purely a
        # memory/speed knob and cannot change the proposal ranking.
        y0 = rng.uniform(0.0, 1.0, (len(cand), k, 1)).astype(np.float32)
        noise = rng.standard_normal((steps, len(cand), k, 1)).astype(np.float32)
        ei_vals = np.zeros(len(cand), dtype=float)
        exp_vals = np.zeros(len(cand), dtype=float)
        scale = Y_MAX - Y_MIN
        for start in range(0, len(cand), chunk):
            stop = min(start + chunk, len(cand))
            c = stop - start
            Xb = np.repeat(X_cand[start:stop], k, axis=0)
            yb = y0[start:stop].reshape(c * k, 1)
            nb = noise[:, start:stop].reshape(steps, c * k, 1)
            draws = self._langevin_batch(Xb, yb, nb).reshape(c, k) * scale
            interior = (draws > 2.0) & (draws < 53.0)
            clipped = np.where(interior, np.maximum(draws - y_best, 0.0), 0.0)
            counts = interior.sum(axis=1)
            ei_vals[start:stop] = np.where(
                counts > 0, clipped.sum(axis=1) / np.maximum(counts, 1), 0.0)
            exp_vals[start:stop] = draws.mean(axis=1)
        if not (np.isfinite(ei_vals).all() and np.isfinite(exp_vals).all()):
            raise RuntimeError("non-finite EI/expected DH from the energy model")

        evals = [(float(ei_vals[i]), float(exp_vals[i]), *cand[i])
                 for i in range(len(cand))]
        evals.sort(key=lambda t: (-t[0], -t[1]))
        return [{"EI": t[0], "expected_DH": round(t[1], 1),
                 "pH": t[2][0], "Temp_C": t[2][1], "Duration_min": t[2][2],
                 "SubstrateConc_gL": t[2][3],
                 DOSE_COL: t[3],
                 **{c: t[4][i] for i, c in enumerate(COMPOSITION_COLS)},
                 "Enzyme": t[5], "RawMaterial": t[6]}
                for t in evals[:n_new]]


def offline_validation(n_folds=3, seeds=(0, 1, 2)):
    opt = EBMOptimizer()
    opt.load_data()
    df = opt.meta
    df = df.sort_values("BatchID").reset_index(drop=True)
    rng = np.random.default_rng(1)
    order = rng.permutation(len(df))
    folds = np.array_split(order, n_folds)
    results = []
    for seed in seeds:
        hits = 0
        for fi in range(n_folds):
            test_idx = folds[fi]
            train = df.iloc[np.setdiff1d(order, test_idx)].reset_index(drop=True)
            test = df.iloc[test_idx].reset_index(drop=True)
            opt.fit_x_stats(opt.make_x(train))
            opt.train(train, seed=seed, epochs=500)
            median_y = float(train["FinalDH_pct"].median())
            proposed = opt.acquire(train, n_new=3, seed=seed * 10 + fi)
            Xn_train = opt.normalize_x(opt.make_x(train))
            df_prop = pd.DataFrame(proposed)
            prop_num = df_prop[PROCESS_COLS].to_numpy(float)
            prop_es = df_prop[[DOSE_COL]].to_numpy(float)
            prop_comp = df_prop[COMPOSITION_COLS].to_numpy(float)
            prop_enz = np.zeros((len(df_prop), len(ENZYMES)))
            for i, e in enumerate(df_prop["Enzyme"]):
                prop_enz[i, ENZYME_INDEX[e]] = 1.0
            Xp = opt.normalize_x(np.concatenate(
                [prop_num, prop_es, prop_comp, prop_enz], axis=1))
            Xt = opt.normalize_x(opt.make_x(test))
            dist = np.linalg.norm(Xp[:, None, :] - Xt[None, :, :], axis=-1)
            nearest = np.argmin(dist, axis=1)
            for row in nearest:
                if float(test.iloc[row]["FinalDH_pct"]) > median_y:
                    hits += 1
        results.append((seed, hits, n_folds))
        print(f"seed={seed}: nearest-neighbour wins {hits}/{n_folds} (of 3 proposals per fold)")
    return results


def main():
    opt = EBMOptimizer()
    opt.load_data()
    df = opt.meta
    opt.train(df, seed=42)
    torch.save(opt.model.state_dict(), f"{MODEL_DIR}/ebm_energy_net.pt")
    np.save(f"{MODEL_DIR}/ebm_x_stats.npy", np.concatenate(opt.x_stats, axis=0))
    prop = opt.acquire(df, n_new=3, seed=42)
    print(f"Acquisition anchor: y_best feasible={feasible_y_best(df):.1f}% "
          f"(all-data best={df['FinalDH_pct'].max():.1f}%)")
    print("Proposed next experiments (trained on all 31 rows):")
    for p in prop:
        print(f"  EI={p['EI']:.2f}  expDH={p['expected_DH']:.1f}  pH={p['pH']:.1f} T={p['Temp_C']:.0f}C dur={p['Duration_min']:.0f}min "
              f"sub={p['SubstrateConc_gL']:.0f} g/L {p['Enzyme']}")
    offline_validation()


if __name__ == "__main__":
    main()