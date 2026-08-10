import numpy as np
import pandas as pd
import torch
import torch.nn as nn

DATA_DIR = "data/processed"
MODEL_DIR = "models"

PROCESS_COLS = ["pH", "Temp_C", "Duration_min", "SubstrateConc_gL"]
COMPOSITION_COLS = ["Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct", "Ash_pct",
                    "Hydroxyproline_pct", "Collagen_pct"]
ENZYMES = ["Alcalase", "Alcalase+Flavourzyme", "Alcalase+Kojizyme", "Alcalase+Neutrase",
           "Flavourzyme", "Neutrase", "Pepsin"]
ENZYME_INDEX = {e: i for i, e in enumerate(ENZYMES)}

Y_MIN, Y_MAX = 0.0, 55.0
N_CHAINS = 4
N_LANGEVIN_STEPS = 120
N_EI_CANDIDATES = 500
MIN_CLASS_ROWS = 3
EPSILON = 0.05
SEED = 42

BOUNDS = {"pH": (2.0, 10.0), "Temp_C": (30.0, 60.0), "Duration_min": (15.0, 300.0),
          "SubstrateConc_gL": (30.0, 70.0)}


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
    def __init__(self, seed=SEED):
        self.rng = np.random.default_rng(seed)
        torch.manual_seed(seed)
        self.x_stats = None
        self.model = None

    def load_data(self):
        main = pd.read_csv(f"{DATA_DIR}/main_batch_clean.csv")
        self.meta = main.copy()

    def make_x(self, df):
        num = df[PROCESS_COLS + COMPOSITION_COLS].astype(float).to_numpy()
        onehot = np.zeros((len(df), len(ENZYMES)))
        for i, e in enumerate(df["Enzyme"]):
            onehot[i, ENZYME_INDEX[e]] = 1.0
        return np.concatenate([num, onehot], axis=1)

    def fit_x_stats(self, X):
        self.x_stats = (X.mean(axis=0, keepdims=True), X.std(axis=0, keepdims=True) + 1e-9)

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

    def langevin_samples(self, x_row_norm, k=N_CHAINS, steps=N_LANGEVIN_STEPS, eps=EPSILON):
        e = float(np.sqrt(eps))
        scale = Y_MAX - Y_MIN
        y0 = self.rng.uniform(0.0, 1.0, (k, 1)).astype(np.float32)
        xt = np.tile(x_row_norm, (k, 1)).astype(np.float32)
        yt = torch.tensor(y0, requires_grad=True)
        for _ in range(steps):
            yt = yt.detach().requires_grad_(True)
            E = self.model(torch.tensor(xt), yt)
            grad = torch.autograd.grad(E.sum(), yt)[0]
            noise = torch.randn_like(yt)
            yt = yt - (eps / 2.0) * grad + e * noise
            yt = torch.clamp(yt, 0.0, 1.0)
        draws = yt.detach().numpy() * scale
        return draws

    def ei(self, x_row_unnorm, y_best):
        xnn = self.normalize_x(np.asarray(x_row_unnorm, dtype=float).reshape(1, -1))
        samples = self.langevin_samples(xnn).flatten()
        interior = samples[(samples > 2.0) & (samples < 53.0)]
        if interior.size == 0:
            ei_val = 0.0
        else:
            ei_val = float(np.mean(np.maximum(interior - y_best, 0.0)))
        return ei_val, samples

    def acquire(self, df_train, n_new=3, n_cand=N_EI_CANDIDATES, seed=None):
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        y_best = float(df_train["FinalDH_pct"].max())
        class_counts = df_train["Enzyme"].value_counts().to_dict()
        eligible_enzymes = [e for e in ENZYMES if class_counts.get(e, 0) >= MIN_CLASS_ROWS]
        if not eligible_enzymes:
            eligible_enzymes = ENZYMES
        rng = self.rng
        bases = []
        for row in df_train.itertuples():
            if class_counts.get(row.Enzyme, 0) < MIN_CLASS_ROWS:
                continue
            x_num = [row.pH, row.Temp_C, row.Duration_min, row.SubstrateConc_gL]
            x_comp = [getattr(row, c) for c in COMPOSITION_COLS]
            bases.append((x_num, x_comp, row.Enzyme))
        cand = []
        for _ in range(n_cand):
            b = bases[int(rng.integers(0, len(bases)))]
            xn = [np.clip(b[0][i] + rng.normal(0, 0.05) * (BOUNDS[c][1] - BOUNDS[c][0]), *BOUNDS[c])
                  for i, c in enumerate(PROCESS_COLS)]
            xc = [b[1][i] * (1.0 + rng.normal(0, 0.02)) for i in range(len(COMPOSITION_COLS))]
            enzyme = b[2]
            cand.append((xn, xc, enzyme))
        evals = []
        for xn, xc, enzyme in cand:
            row = xn + xc + [1.0 if ENZYME_INDEX[enzyme] == i else 0.0 for i in range(len(ENZYMES))]
            ei_val, samples = self.ei(row, y_best)
            evals.append((ei_val, float(np.mean(samples)), xn, xc, enzyme))
        evals.sort(key=lambda t: (-t[0], -t[1]))
        return [{"EI": t[0], "expected_DH": round(t[1], 1),
                 "pH": t[2][0], "Temp_C": t[2][1], "Duration_min": t[2][2],
                 "SubstrateConc_gL": t[2][3],
                 **{c: t[3][i] for i, c in enumerate(COMPOSITION_COLS)}, "Enzyme": t[4]}
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
            prop_comp = df_prop[COMPOSITION_COLS].to_numpy(float)
            prop_enz = np.zeros((len(df_prop), len(ENZYMES)))
            for i, e in enumerate(df_prop["Enzyme"]):
                prop_enz[i, ENZYME_INDEX[e]] = 1.0
            Xp = opt.normalize_x(np.concatenate([prop_num, prop_comp, prop_enz], axis=1))
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
    print("Proposed next experiments (trained on all 31 rows):")
    for p in prop:
        print(f"  EI={p['EI']:.2f}  expDH={p['expected_DH']:.1f}  pH={p['pH']:.1f} T={p['Temp_C']:.0f}C dur={p['Duration_min']:.0f}min "
              f"sub={p['SubstrateConc_gL']:.0f} g/L {p['Enzyme']}")
    offline_validation()


if __name__ == "__main__":
    main()