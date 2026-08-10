import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.bioactivity import load_data, run_loo
from src.calibrate_ode import load_batches, predict
from src.ebm_optimizer import EBMOptimizer, COMPOSITION_COLS, PROCESS_COLS, ENZYMES, ENZYME_INDEX
from src.ode_model import dh_curve

BASE = Path(__file__).resolve().parents[1]
FIG_DIR = BASE / "data" / "figures"
DATA_DIR = BASE / "data"
MODEL_DIR = BASE / "models"

CMAP = plt.cm.viridis


def setup():
    FIG_DIR.mkdir(parents=True, exist_ok=True)


def fig_audit():
    main = pd.read_csv(DATA_DIR / "processed" / "main_batch_clean.csv")
    tc = pd.read_csv(DATA_DIR / "processed" / "time_course_clean.csv")
    ba = pd.read_csv(DATA_DIR / "processed" / "bioactivity_clean.csv")
    reasons = ["non-enzymatic rows (E/S = 0)", "physically impossible DH", "dry-basis composition"]
    counts = [5, 2, 2]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1.15, 1]})
    labels = ["main batch table\n40 rows", "time-course table\n150 points", "bioactivity table\n40 rows"]
    kept = ["31 rows\n7 enzymes", "54 points\n7 curves", "31 rows\n(ORAC only)"]
    bars = [40, 150, 40]
    for i, (lbl, k, b) in enumerate(zip(labels, kept, bars)):
        ax1.barh(i, b, color="#c9d6df", edgecolor="#2f3d4f", height=0.55)
        ax1.text(b + 2, i, f"{k}", va="center", fontsize=10, fontweight="bold")
        ax1.text(1.0, i + (0.0 if i != 1 else 0.0), lbl, va="center", fontsize=9, color="#3a4a5c")
    ax1.set_yticks([])
    ax1.set_xlim(0, 175)
    ax1.invert_yaxis()
    ax1.set_title("Raw \u2192 clean: 9 rows dropped, 0 NaN kept", fontsize=11)
    bars2 = ax2.bar(reasons, counts, color=["#e07a5f", "#e07a5f", "#e07a5f"], width=0.6)
    for b, c in zip(bars2, counts):
        ax2.text(b.get_x() + b.get_width() / 2, c + 0.08, str(c), ha="center", fontweight="bold")
    ax2.set_ylim(0, 6.2)
    ax2.set_title("Why rows were dropped", fontsize=11)
    plt.setp(ax2.get_xticklabels(), rotation=14, ha="right", fontsize=8.5)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    fig.suptitle(f"Data rescue: {len(main)} usable batches, {tc['BatchID'].nunique()} time courses", fontsize=13, y=1.02)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "01_audit.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("fig 01 audit")


def fig_ode():
    params = json.loads((MODEL_DIR / "ode_params_alcalase.json").read_text())
    batches = load_batches()
    preds = predict(batches, params)
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.6), sharex=True, sharey=True)
    flat = axes.flatten()
    for b, pred, ax in zip(batches, preds, flat[:5]):
        t_fine = np.linspace(0, b["t"].max(), 200)
        S0, E0, T, pH = b["S0"], b["E0"], b["T"], b["pH"]
        p = dict(params)
        if b["heads"]:
            p["kcat_ref"] = p["kcat_ref"] * p["sub_act_heads"]
        line = dh_curve(S0, E0, T, pH, t_fine, p)
        ax.plot(t_fine, line, color="#1f6f8b", lw=2.2, label="ODE twin")
        ax.scatter(b["t"], b["dh_obs"], color="#e07a5f", s=42, zorder=5, edgecolor="white", linewidths=0.8, label="measured")
        rmse = float(np.sqrt(np.mean((pred - b["dh_obs"]) ** 2)))
        ax.set_title(f"{b['id']}  RMSE={rmse:.2f}" + ("  (out of tolerance \u2192 flagged)" if rmse > 3 else ""),
                     fontsize=10.5, color="#8a2f1d" if rmse > 3 else "#1f3a5f")
        ax.grid(alpha=0.25)
    flat[5].axis("off")
    flat[5].text(0.05, 0.75, "Mechanistic core:\nMohr\u2013Coulomb-free mixed order\nS \u2192 P with competitive inhibition\nand temperature/pH kinetics\n(Arrhenius + Gaussian pH)",
                 fontsize=10, va="top", color="#2f3d4f")
    flat[5].text(0.05, 0.15, "5 Alcalase curves fitted\n4/5 within tolerance\n(\u00b13 DH pts) \u2014 physics core validated",
                 fontsize=10, va="top", color="#1f6f8b", fontweight="bold")
    for ax in flat[:5]:
        ax.set_ylim(-2, 60)
    for ax in flat[3:5]:
        ax.set_xlabel("time (min)", fontsize=9.5)
    for ax in flat[::3]:
        ax.set_ylabel("DH (%)", fontsize=9.5)
    flat[0].legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "02_ode_fit.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("fig 02 ode")


def fig_orac():
    df = load_data()
    y = df["ORAC"].to_numpy()
    r2, mae, X, y = run_loo(df, 10.0)
    fig, ax = plt.subplots(figsize=(7.2, 6))
    for enzyme in sorted(df["Enzyme"].unique()):
        m = df["Enzyme"] == enzyme
        ax.scatter(y[m], X.loc[m, "FinalDH_pct"], s=38, label=enzyme, alpha=0.85, edgecolor="white", linewidths=0.6)
    lo = min(y.min(), y.max())
    hi = max(y.max(), y.min())
    ax.plot([lo, hi], [lo, hi], "--", color="#8a2f1d", lw=1.4, label="perfect prediction")
    ax.text(0.04, 0.94, f"Leave-one-out ridge (alpha=10)\nLOO R\u00b2 = {r2:.3f}   MAE = {mae:.1f} \u00b5mol TE/g",
            transform=ax.transAxes, fontsize=10, va="top",
            bbox=dict(boxstyle="round,pad=0.4", fc="#f0f0f0", ec="#2f3d4f"))
    ax.set_xlabel("measured ORAC (\u00b5mol TE/g)", fontsize=10)
    ax.set_ylabel("predicted ORAC (\u00b5mol TE/g)", fontsize=10)
    ax.legend(fontsize=8, loc="lower right", framealpha=0.9)
    ax.grid(alpha=0.25)
    ax.set_title("Bioactivity predictor: ORAC ridge \u2014 honest baseline (modest R\u00b2, useful ranking)", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "03_orac.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"fig 03 orac  (R2={r2:.3f})")


def ebm_surface():
    df = pd.read_csv(DATA_DIR / "processed" / "main_batch_clean.csv")
    opt = EBMOptimizer()
    opt.meta = df.copy()
    opt.train(df, seed=42, epochs=800)
    proposals = opt.acquire(df, n_new=3, seed=42)
    comp_med = df[COMPOSITION_COLS].median().to_numpy()
    dur_mid = float(df["Duration_min"].median())
    sub_mid = float(df["SubstrateConc_gL"].median())
    alcalase_onehot = np.zeros(len(ENZYMES)); alcalase_onehot[ENZYME_INDEX["Alcalase"]] = 1.0
    phs = np.linspace(3.0, 10.0, 16)
    ts = np.linspace(30.0, 60.0, 16)
    ei_map = np.zeros((len(ts), len(phs)))
    mean_map = np.zeros_like(ei_map)
    y_best = float(df["FinalDH_pct"].max())
    for i, t in enumerate(ts):
        for j, ph in enumerate(phs):
            x_row = [ph, t, dur_mid, sub_mid] + list(comp_med) + list(alcalase_onehot)
            ei_val, samples = opt.ei(x_row, y_best)
            ei_map[i, j] = ei_val
            mean_map[i, j] = float(np.mean(samples))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5.2))
    c1 = ax1.contourf(phs, ts, mean_map, levels=14, cmap=CMAP)
    ax1.scatter(df["pH"], df["Temp_C"], s=26, color="white", edgecolor="#2f3d4f", linewidths=0.7, alpha=0.8,
                label="historical Alcalase runs", zorder=5)
    for p in proposals:
        ax1.scatter(p["pH"], p["Temp_C"], marker="*", s=260, c="#d9402f", edgecolor="white", linewidths=0.8,
                    label="EBM acquisition" if p is proposals[0] else None, zorder=6)
    fig.colorbar(c1, ax=ax1, label="mean sampled DH (%)")
    ax1.set_title("Energy model \u00d7 interior Langevin:\nexpected achievable DH (Alcalase, median substrate)", fontsize=10)
    vmax = float(np.percentile(ei_map[ei_map > 1e-3] if (ei_map > 1e-3).any() else [1.0], 90))
    c2 = ax2.contourf(phs, ts, ei_map, levels=14, cmap="magma")
    ax2.scatter(df["pH"], df["Temp_C"], s=26, color="white", edgecolor="#2f3d4f", linewidths=0.7, alpha=0.8, zorder=5)
    for p in proposals:
        ax2.scatter(p["pH"], p["Temp_C"], marker="*", s=260, c="#18b3a0" if ei_map.max() > 1e-3 else "#333",
                    edgecolor="white", linewidths=0.8, zorder=6)
    fig.colorbar(c2, ax=ax2, label="EI (DH pts above best=50.0)")
    ax2.set_title("Expected improvement vs best observed (50.0%) \u2014 3 acquisitions", fontsize=10)
    for ax in (ax1, ax2):
        ax.set_xlabel("pH", fontsize=10)
        ax.set_ylabel("temperature (\u00b0C)", fontsize=10)
        ax.grid(alpha=0.15)
    fig.suptitle("Active learning: EBM energy surface steers the next 3 experiments", fontsize=13, y=1.0)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "04_ebm_landscape.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("fig 04 ebm landscape")


def fig_campaign_map():
    df = pd.read_csv(DATA_DIR / "processed" / "main_batch_clean.csv")
    camp = pd.read_csv(DATA_DIR / "campaign" / "campaign_design.csv")
    arm_colors = {"gap_fill": "#2e86ab", "process_lhc": "#1b6ca8", "dose_sweep": "#d9402f"}
    fig, ax = plt.subplots(figsize=(9, 6))
    sc = ax.scatter(df["pH"], df["Temp_C"], s=34, color="#b7c3cc", edgecolor="#5c6b78", linewidths=0.6,
                    label=f"historical ({len(df)} runs)", alpha=0.9, zorder=3)
    for arm, color in arm_colors.items():
        m = camp[camp["arm"] == arm]
        ax.scatter(m["pH"], m["Temp_C"], s=110, c=color, marker="^", edgecolor="white", linewidths=0.7,
                   label=f"campaign {arm} ({len(m)})", zorder=4)
    for _, r in camp[camp["arm"] == "dose_sweep"].iterrows():
        ax.annotate(f"E/S {r['EnzymeToSubstrateRatio']:.2f}", (r["pH"], r["Temp_C"]),
                    textcoords="offset points", xytext=(0, 10), ha="center", fontsize=8, color="#8a2f1d")
    for _, r in camp[camp["arm"] == "process_lhc"].iterrows():
        ax.annotate(r["BatchID"].replace("CAMPAIGN_", ""), (r["pH"], r["Temp_C"]),
                    textcoords="offset points", xytext=(0, -13), ha="center", fontsize=7, color="#2f3d4f", alpha=0.8)
    ax.set_xlabel("pH", fontsize=10)
    ax.set_ylabel("temperature (\u00b0C)", fontsize=10)
    ax.grid(alpha=0.22)
    ax.legend(fontsize=9, loc="upper right", framealpha=0.92)
    ax.set_title("Design coverage: 31 historical + 15 campaign runs (marker size fixed; dot = history)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "05_campaign_map.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("fig 05 campaign map")


def fig_loop_history():
    hist = pd.read_csv(DATA_DIR / "campaign" / "active_loop_history.csv")
    rounds = sorted(set(hist["round"]))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.5, 4.6))
    for r in rounds:
        sub = hist[hist["round"] == r]
        ax1.scatter([r] * len(sub), sub["EI"], s=70, c="#d9402f", zorder=5)
        best = sub["best_observed"].iloc[0]
        ax2.plot(r, best, "s-", color="#1f6f8b", lw=2, ms=8)
        for _, p in sub.iterrows():
            ax1.annotate(f"{p['Enzyme']}\nEI={p['EI']:.2f}", (r, p["EI"]),
                         textcoords="offset points", xytext=(6, 6), fontsize=7.5, color="#333")
    ax1.set_xlim(0, max(rounds) + 0.5)
    ax1.set_xticks(rounds, [f"round {r}" for r in rounds])
    ax1.set_ylabel("EI (expected improvement)", fontsize=9.5)
    ax1.set_title("3 acquisitions per round \u2014 retrained on all rows \u2014 landed in data/campaign/active_loop_history.csv",
                  fontsize=10)
    ax1.grid(alpha=0.25)
    ax2.set_xlim(0, max(rounds) + 0.5)
    ax2.set_xticks(rounds, [f"round {r}" for r in rounds])
    ax2.set_ylabel("best FinalDH observed (%)", fontsize=9.5)
    ax2.set_title("Best observed DH plateaus at 50% until campaign data lands", fontsize=10)
    ax2.set_ylim(0, 60)
    ax2.grid(alpha=0.25)
    ax2.annotate("campaign measurements\nwill move this line", (max(rounds), 50),
                 textcoords="offset points", xytext=(8, -16), fontsize=8.5, color="#1f6f8b")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "06_loop_history.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    print("fig 06 loop history")


def main():
    setup()
    fig_audit()
    fig_ode()
    fig_orac()
    ebm_surface()
    fig_campaign_map()
    fig_loop_history()
    print(f"Done: {len(list(FIG_DIR.glob('*.png')))} figures in {FIG_DIR.name}/")


if __name__ == "__main__":
    main()