"""benchmark_policy.py - does the acquisition loop actually reduce trials?

This is the centrepiece evidence for the project.  It runs the real EBM loop
(not a toy surrogate) inside the independent synthetic world from
``src/synthetic_lab.py`` and compares it with design baselines:

  twin_current  the production-style loop: trust-region candidates around the
                best measured rows, MIN_CLASS_ROWS=3, E/S modelled
  twin_explore  same, but MIN_CLASS_ROWS=1 (isolates the eligibility guard)
  random        uniform random runs over the campaign box
  lhc           static Latin-hypercube design over the box
  ofat          greedy one-factor-at-a-time around the best measured run
  grid          coarse 4-level process grid, enzyme/material/E-S fixed at the
                best seed run (a full factorial over all factors is far larger)
  oracle        knows the latent truth; picks the true top runs (upper bound)

Primary metric: mean best *true* DH at the 30-run budget (including the 15-run
seed campaign).  Secondary: true regret, the true DH of the run the lab would
select (highest *measured* DH), ORAC at that run, and whether EI ranks
proposals by realised improvement.

The 200 worlds are split 0-99 (development) and 100-199 (held-out).  Step-5
tuning must use the development half only; the headline table is the held-out
half.  A synthetic win is not a real-world win: the generator is a plausible
world, not a validated model.

Run:
    python -m src.benchmark_policy --worlds 100 --world-start 100 --workers 2
    python -m src.benchmark_policy --quick
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

# Pin BLAS/OpenMP threads before numpy/torch are imported.  On Windows the
# spawned worker re-imports this module, so these values are inherited by every
# worker.  Without this, two workers each start 12 BLAS threads on a 12-thread
# CPU and spend their time context-switching.
for _thread_var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
                    "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_thread_var, "1")

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.ebm_optimizer import COMPOSITION_COLS, EBMOptimizer
from src.synthetic_lab import (ENZYMES, ES_VALUES, MATERIALS, PROCESS_BOUNDS,
                               SyntheticLab, _jsonable, _lhc)

BASE = Path(__file__).resolve().parents[1]
OUT_DIR = BASE / "data" / "synthetic"
RUNS_DIR = OUT_DIR / "runs"
MODEL_NAME = "two_pool_exposure_v1"
SCHEMA_VERSION = 1

DESIGN_COLS = ["BatchID", "Enzyme", "pH", "Temp_C", "Duration_min",
               "SubstrateConc_gL", "EnzymeToSubstrateRatio", "RawMaterial",
               *COMPOSITION_COLS]
HISTORY_COLS = ["world", "policy", "source", "round", "trial", "BatchID",
                "Enzyme", "RawMaterial", "pH", "Temp_C", "Duration_min",
                "SubstrateConc_gL", "EnzymeToSubstrateRatio",
                "true_DH_pct", "FinalDH_pct", "true_ORAC", "ORAC",
                "gross_error", "proposed_EI", "proposed_expected_DH"]

POLICY_ORDER = ["twin_current", "twin_explore", "twin_explore_random",
                "twin_random_rank", "random", "lhc", "ofat", "grid", "oracle"]

# Two times the real-replicate repeatability (1.07 DH, the internal noise-floor notes).
# A policy that gets within this band of the world's oracle is at the limit of
# what the real assay can distinguish; the 95%-of-oracle target is stricter.
NOISE_BAND_DH = 2.1
MAX_WORKERS = 3
POOL_CHUNK = 20


@dataclass
class BenchmarkConfig:
    n_worlds: int = 200
    world_start: int = 0
    budget: int = 30
    batch: int = 3
    seed: int = 20261029
    epochs: int = 250
    n_aug: int = 6
    n_cand: int = 150
    langevin_steps: int = 120
    chains: int = 4
    ei_chunk: int = 64
    oracle_candidates: int = 50000
    workers: int = 2
    policies: tuple[str, ...] = tuple(POLICY_ORDER)
    save_histories: bool = True
    quick: bool = False
    split_at: int = 100
    # Free pre-campaign history, mimicking the 31 real batches the production
    # loop trains on.  Zero reproduces the original cold-start benchmark.  The
    # rows are training data only: they do not consume campaign trials and are
    # not part of the campaign metrics.
    history_rows: int = 0


# --------------------------------------------------------------------- utils
def _snap_es(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.02
    return float(min(ES_VALUES, key=lambda x: abs(x - v)))


def _make_design(rows: list[dict[str, Any]], world, policy: str,
                 round_no: int, world_seed: int) -> pd.DataFrame:
    """Normalise policy output into a campaign row with a unique BatchID."""
    out = []
    for i, r in enumerate(rows, 1):
        material = str(r.get("RawMaterial", "salmon_frames"))
        if material not in MATERIALS:
            material = "salmon_frames"
        comp = world.material_comp[material]
        row = {
            "BatchID": f"{policy[:4].upper()}_{world_seed:03d}_{round_no:02d}_{i:02d}",
            "Enzyme": str(r["Enzyme"]),
            "pH": round(float(np.clip(r["pH"], *PROCESS_BOUNDS["pH"])), 2),
            "Temp_C": round(float(np.clip(r["Temp_C"], *PROCESS_BOUNDS["Temp_C"])), 1),
            "Duration_min": round(float(np.clip(r["Duration_min"],
                                                *PROCESS_BOUNDS["Duration_min"])), 1),
            "SubstrateConc_gL": round(float(np.clip(r["SubstrateConc_gL"],
                                                    *PROCESS_BOUNDS["SubstrateConc_gL"])), 2),
            "EnzymeToSubstrateRatio": _snap_es(r.get("EnzymeToSubstrateRatio", 0.02)),
            "RawMaterial": material,
            # Composition is a property of the material lot, not a dial the
            # experimenter can set.  Policies may use composition as a feature,
            # but the measured design row must carry the world's true material
            # composition; otherwise a policy could "propose" a better lot and
            # the synthetic truth would reward an impossible experiment.
            **{c: float(comp[c]) for c in COMPOSITION_COLS},
        }
        if "proposed_EI" in r and np.isfinite(float(r["proposed_EI"])):
            row["proposed_EI"] = float(r["proposed_EI"])
        if "proposed_expected_DH" in r and np.isfinite(float(r["proposed_expected_DH"])):
            row["proposed_expected_DH"] = float(r["proposed_expected_DH"])
        out.append(row)
    return pd.DataFrame(out)


def _history_row(world_seed: int, policy: str, source: str, round_no: int,
                 row: Any) -> dict[str, Any]:
    return {
        "world": int(world_seed), "policy": policy, "source": source,
        "round": int(round_no), "trial": int(row.trial),
        "BatchID": row.BatchID, "Enzyme": row.Enzyme,
        "RawMaterial": row.RawMaterial, "pH": float(row.pH),
        "Temp_C": float(row.Temp_C), "Duration_min": float(row.Duration_min),
        "SubstrateConc_gL": float(row.SubstrateConc_gL),
        "EnzymeToSubstrateRatio": float(row.EnzymeToSubstrateRatio),
        "true_DH_pct": float(row.true_DH_pct),
        "FinalDH_pct": float(row.FinalDH_pct),
        "true_ORAC": float(row.true_ORAC), "ORAC": float(row.ORAC),
        "gross_error": bool(row.gross_error),
        "proposed_EI": float(getattr(row, "proposed_EI", np.nan)),
        "proposed_expected_DH": float(getattr(row, "proposed_expected_DH", np.nan)),
    }


# -------------------------------------------------------------------- policies
class BasePolicy:
    name = "base"

    def __init__(self, world_seed: int, seed_data: pd.DataFrame,
                 cfg: BenchmarkConfig, lab: SyntheticLab):
        self.world_seed = world_seed
        self.cfg = cfg
        self.lab = lab
        self.seed_data = seed_data.copy()
        self.data = seed_data.copy()
        self.round = 0
        idx = POLICY_ORDER.index(self.name) if self.name in POLICY_ORDER else 0
        self.rng = np.random.default_rng(world_seed * 1000 + idx * 97 + 29)
        self.measure_rng = np.random.default_rng(world_seed * 1000 + idx * 97 + 13)

    def propose(self, n: int) -> pd.DataFrame:
        raise NotImplementedError

    def observe(self, measured: pd.DataFrame) -> None:
        self.data = pd.concat([self.data, measured], ignore_index=True)
        self.round += 1

    def _frame(self, rows: list[dict[str, Any]]) -> pd.DataFrame:
        return _make_design(rows, self.lab.world, self.name, self.round + 1,
                            self.world_seed)


class RandomPolicy(BasePolicy):
    name = "random"

    def propose(self, n: int) -> pd.DataFrame:
        cand = self.lab.candidate_space(n, rng=self.rng, balanced_enzymes=False)
        return self._frame(cand.to_dict("records"))


class LHCPolicy(BasePolicy):
    name = "lhc"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.points = self._make_points(self.cfg.budget)
        self.cursor = 0

    def _make_points(self, n: int) -> list[dict[str, Any]]:
        u = _lhc(n, 4, self.rng)
        enzymes = list(ENZYMES)
        self.rng.shuffle(enzymes)
        materials = list(MATERIALS)
        self.rng.shuffle(materials)
        es = list(ES_VALUES) * (n // len(ES_VALUES) + 1)
        self.rng.shuffle(es)
        rows = []
        for i in range(n):
            rows.append({
                "Enzyme": enzymes[i % len(enzymes)],
                "pH": 2.0 + 8.0 * u[i, 0],
                "Temp_C": 30.0 + 30.0 * u[i, 1],
                "Duration_min": 15.0 + 285.0 * u[i, 2],
                "SubstrateConc_gL": 30.0 + 40.0 * u[i, 3],
                "EnzymeToSubstrateRatio": es[i],
                "RawMaterial": materials[i % len(materials)],
            })
        return rows

    def propose(self, n: int) -> pd.DataFrame:
        rows = self.points[self.cursor:self.cursor + n]
        self.cursor += len(rows)
        return self._frame(rows)


class OFATPolicy(BasePolicy):
    name = "ofat"
    FACTORS = ["pH", "Temp_C", "Duration_min", "SubstrateConc_gL",
               "EnzymeToSubstrateRatio"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.center = self._best(self.seed_data)
        self.factor_idx = 0
        self.direction = 1
        self.seen: set[tuple] = set()

    @staticmethod
    def _best(data: pd.DataFrame) -> dict[str, Any]:
        return data.loc[data["FinalDH_pct"].idxmax()].to_dict()

    def _step(self, row: dict[str, Any], factor: str, direction: int) -> dict[str, Any]:
        r = dict(row)
        if factor == "pH":
            r["pH"] = float(np.clip(r["pH"] + direction * 0.75,
                                    *PROCESS_BOUNDS["pH"]))
        elif factor == "Temp_C":
            r["Temp_C"] = float(np.clip(r["Temp_C"] + direction * 4.0,
                                        *PROCESS_BOUNDS["Temp_C"]))
        elif factor == "Duration_min":
            r["Duration_min"] = float(np.clip(
                r["Duration_min"] * (1.5 if direction > 0 else 0.67),
                *PROCESS_BOUNDS["Duration_min"]))
        elif factor == "SubstrateConc_gL":
            r["SubstrateConc_gL"] = float(np.clip(
                r["SubstrateConc_gL"] + direction * 10.0,
                *PROCESS_BOUNDS["SubstrateConc_gL"]))
        elif factor == "EnzymeToSubstrateRatio":
            cur = _snap_es(r["EnzymeToSubstrateRatio"])
            i = list(ES_VALUES).index(cur)
            r["EnzymeToSubstrateRatio"] = ES_VALUES[(i + direction) % len(ES_VALUES)]
        return r

    def propose(self, n: int) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        attempts = 0
        while len(rows) < n and attempts < n * 30:
            attempts += 1
            factor = self.FACTORS[self.factor_idx % len(self.FACTORS)]
            self.factor_idx += 1
            direction = self.direction
            self.direction *= -1
            r = self._step(self.center, factor, direction)
            key = (round(float(r["pH"]), 3), round(float(r["Temp_C"]), 3),
                   round(float(r["Duration_min"]), 3),
                   round(float(r["SubstrateConc_gL"]), 3),
                   _snap_es(r["EnzymeToSubstrateRatio"]), r["Enzyme"],
                   r["RawMaterial"])
            if key in self.seen:
                continue
            self.seen.add(key)
            rows.append(r)
        while len(rows) < n:
            r = dict(self.center)
            r["pH"] = float(np.clip(r["pH"] + self.rng.normal(0, 0.5),
                                    *PROCESS_BOUNDS["pH"]))
            r["Temp_C"] = float(np.clip(r["Temp_C"] + self.rng.normal(0, 3.0),
                                        *PROCESS_BOUNDS["Temp_C"]))
            rows.append(r)
        return self._frame(rows)

    def observe(self, measured: pd.DataFrame) -> None:
        super().observe(measured)
        self.center = self._best(self.data)


class GridPolicy(BasePolicy):
    name = "grid"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        best = self.seed_data.loc[self.seed_data["FinalDH_pct"].idxmax()].to_dict()
        self.enzyme = best["Enzyme"]
        self.material = best["RawMaterial"]
        self.es = _snap_es(best["EnzymeToSubstrateRatio"])
        self.points = self._make_grid()
        self.cursor = 0

    def _make_grid(self) -> list[dict[str, Any]]:
        levels = [0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0]
        rows = []
        for a in levels:
            for b in levels:
                for c in levels:
                    for d in levels:
                        rows.append({
                            "Enzyme": self.enzyme,
                            "pH": 2.0 + 8.0 * a,
                            "Temp_C": 30.0 + 30.0 * b,
                            "Duration_min": 15.0 + 285.0 * c,
                            "SubstrateConc_gL": 30.0 + 40.0 * d,
                            "EnzymeToSubstrateRatio": self.es,
                            "RawMaterial": self.material,
                        })
        self.rng.shuffle(rows)
        return rows

    def propose(self, n: int) -> pd.DataFrame:
        rows = self.points[self.cursor:self.cursor + n]
        self.cursor += len(rows)
        return self._frame(rows)


class OraclePolicy(BasePolicy):
    name = "oracle"

    def __init__(self, world_seed: int, seed_data: pd.DataFrame,
                 cfg: BenchmarkConfig, lab: SyntheticLab,
                 oracle_table: dict[str, Any]):
        super().__init__(world_seed, seed_data, cfg, lab)
        self.table = oracle_table["top_dh"].copy()
        self.cursor = 0

    def propose(self, n: int) -> pd.DataFrame:
        rows = self.table.iloc[self.cursor:self.cursor + n].to_dict("records")
        self.cursor += len(rows)
        return self._frame(rows)


class TwinPolicy(BasePolicy):
    name = "twin_current"
    min_class_rows: int | None = None
    rank_mode = "ei"

    def propose(self, n: int) -> pd.DataFrame:
        seed = self.world_seed * 1000 + 900 + self.round
        opt = EBMOptimizer(seed=seed)
        opt.meta = self.data.copy()
        opt.fit_x_stats(opt.make_x(self.data))
        opt.train(self.data, seed=seed, epochs=self.cfg.epochs,
                  n_aug=self.cfg.n_aug)
        props = opt.acquire(self.data, n_new=n, n_cand=self.cfg.n_cand,
                            seed=seed + 1, min_class_rows=self.min_class_rows,
                            chains=self.cfg.chains,
                            langevin_steps=self.cfg.langevin_steps,
                            ei_chunk=self.cfg.ei_chunk,
                            rank_mode=self.rank_mode)
        rows = []
        for p in props:
            rows.append({
                "Enzyme": p["Enzyme"],
                "pH": p["pH"], "Temp_C": p["Temp_C"],
                "Duration_min": p["Duration_min"],
                "SubstrateConc_gL": p["SubstrateConc_gL"],
                # E/S is a modelled decision variable since step 5.  The
                # campaign has a dose sweep, so forcing 0.02 here would make
                # the benchmark test a policy that ignores its own design.
                "EnzymeToSubstrateRatio": p["EnzymeToSubstrateRatio"],
                "RawMaterial": p.get("RawMaterial", "salmon_frames"),
                **{c: p[c] for c in COMPOSITION_COLS},
                "proposed_EI": p["EI"],
                "proposed_expected_DH": p["expected_DH"],
            })
        return self._frame(rows)


class TwinExplorePolicy(TwinPolicy):
    name = "twin_explore"
    min_class_rows = 1


class TwinRandomRankPolicy(TwinPolicy):
    """Development-only ablation: same candidate pool, random ranking.

    If this matches ``twin_current``, the energy model's EI ranking is not
    adding value; the candidate distribution is doing the work.
    """
    name = "twin_random_rank"
    rank_mode = "random"


class TwinExploreRandomPolicy(TwinExplorePolicy):
    """Development-only ablation for the frozen policy (min rows = 1)."""
    name = "twin_explore_random"
    rank_mode = "random"


def make_policy(name: str, world_seed: int, seed_data: pd.DataFrame,
                cfg: BenchmarkConfig, lab: SyntheticLab,
                oracle_table: dict[str, Any]) -> BasePolicy:
    mapping = {
        "twin_current": TwinPolicy,
        "twin_explore": TwinExplorePolicy,
        "twin_random_rank": TwinRandomRankPolicy,
        "twin_explore_random": TwinExploreRandomPolicy,
        "random": RandomPolicy,
        "lhc": LHCPolicy,
        "ofat": OFATPolicy,
        "grid": GridPolicy,
    }
    if name == "oracle":
        return OraclePolicy(world_seed, seed_data, cfg, lab, oracle_table)
    if name not in mapping:
        raise ValueError(f"unknown policy: {name}")
    return mapping[name](world_seed, seed_data, cfg, lab)


# -------------------------------------------------------------------- metrics
def _spearman(a, b) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    if len(a) < 3 or np.allclose(a, a[0]) or np.allclose(b, b[0]):
        return float("nan")
    rho = spearmanr(a, b, nan_policy="omit").statistic
    return float(rho) if np.isfinite(rho) else float("nan")


def policy_metrics(history: pd.DataFrame, oracle_best_dh: float,
                   oracle_best_orac: float, cfg: BenchmarkConfig) -> dict[str, Any]:
    hist = history.sort_values("trial").reset_index(drop=True)
    true = hist["true_DH_pct"].to_numpy(float)
    meas = hist["FinalDH_pct"].to_numpy(float)
    best_true_cum = np.maximum.accumulate(true)

    # 95% is the pre-registered headline target.  80% and 90% are reported as
    # sensitivity: a single threshold can make every policy look censored even
    # when one is clearly better.
    reached_by_level: dict[int, tuple[bool, int]] = {}
    for level in (80, 90, 95):
        hit = np.where(best_true_cum >= (level / 100.0) * oracle_best_dh)[0]
        reached_l = bool(len(hit))
        trials_l = int(hist["trial"].iloc[hit[0]]) if reached_l else int(cfg.budget + 1)
        reached_by_level[level] = (reached_l, trials_l)
    reached, trials_to_95 = reached_by_level[95]

    noise_threshold = max(float(oracle_best_dh) - NOISE_BAND_DH, 0.0)
    noise_hit = np.where(best_true_cum >= noise_threshold)[0]
    reached_noise = bool(len(noise_hit))
    trials_to_noise = (int(hist["trial"].iloc[noise_hit[0]]) if reached_noise
                       else int(cfg.budget + 1))

    sel_idx = hist["FinalDH_pct"].idxmax()
    sel = hist.loc[sel_idx]
    best_true = float(true.max())
    best_meas = float(meas.max())
    selected_true = float(sel["true_DH_pct"])
    selected_meas = float(sel["FinalDH_pct"])
    best_orac_true = float(hist["true_ORAC"].max())
    best_orac_meas = float(hist["ORAC"].max())
    orac_at_selected = float(sel["true_ORAC"])

    adaptive = hist[hist["source"] == "adaptive"]
    rho_imp, rho_true, top_hit, top_improved = [], [], [], []
    if len(adaptive):
        for round_no in sorted(adaptive["round"].unique()):
            g = adaptive[adaptive["round"] == round_no]
            if len(g) < 2:
                continue
            before = hist[hist["trial"] < g["trial"].min()]
            y_before = float(before["FinalDH_pct"].max()) if len(before) else 0.0
            ei = g["proposed_EI"].to_numpy(float)
            gtrue = g["true_DH_pct"].to_numpy(float)
            gmeas = g["FinalDH_pct"].to_numpy(float)
            improvement = gmeas - y_before
            r = _spearman(ei, improvement)
            if np.isfinite(r):
                rho_imp.append(r)
            r = _spearman(ei, gtrue)
            if np.isfinite(r):
                rho_true.append(r)
            if np.isfinite(ei).any():
                top = int(np.nanargmax(ei))
                top_hit.append(1.0 if gtrue[top] == gtrue.max() else 0.0)
                top_improved.append(1.0 if gmeas[top] > y_before else 0.0)

    ei_vs_true = _spearman(adaptive["proposed_EI"], adaptive["true_DH_pct"]) \
        if len(adaptive) else float("nan")
    expected_vs_true = _spearman(adaptive["proposed_expected_DH"],
                                 adaptive["true_DH_pct"]) if len(adaptive) else float("nan")
    ei_vs_meas = _spearman(adaptive["proposed_EI"], adaptive["FinalDH_pct"]) \
        if len(adaptive) else float("nan")

    return {
        "n_rows": int(len(hist)),
        "n_adaptive": int(len(adaptive)),
        "n_gross": int(hist["gross_error"].sum()),
        "reached_80": reached_by_level[80][0],
        "trials_to_80": reached_by_level[80][1],
        "reached_90": reached_by_level[90][0],
        "trials_to_90": reached_by_level[90][1],
        "reached_95": reached,
        "trials_to_95": trials_to_95,
        "reached_noise": reached_noise,
        "trials_to_noise": trials_to_noise,
        "noise_band_dh": NOISE_BAND_DH,
        "best_true": best_true,
        "best_measured": best_meas,
        "selected_true": selected_true,
        "selected_measured": selected_meas,
        "selected_trial": int(sel["trial"]),
        "regret_true": float(oracle_best_dh - best_true),
        "regret_selected": float(oracle_best_dh - selected_true),
        "regret_measured": float(oracle_best_dh - best_meas),
        "best_orac_true": best_orac_true,
        "best_orac_measured": best_orac_meas,
        "orac_at_selected": orac_at_selected,
        "orac_regret": float(oracle_best_orac - best_orac_true),
        "ei_spearman_improvement_mean": float(np.mean(rho_imp)) if rho_imp else float("nan"),
        "ei_spearman_true_mean": float(np.mean(rho_true)) if rho_true else float("nan"),
        "ei_top_hit_rate": float(np.mean(top_hit)) if top_hit else float("nan"),
        "ei_top_improved_rate": float(np.mean(top_improved)) if top_improved else float("nan"),
        "ei_vs_true_pooled": ei_vs_true,
        "expected_vs_true_pooled": expected_vs_true,
        "ei_vs_measured_pooled": ei_vs_meas,
    }


# -------------------------------------------------------------------- one world
def _legacy_design(lab: SyntheticLab, n_rows: int,
                   rng: np.random.Generator) -> pd.DataFrame:
    """Synthetic pre-campaign history with the real 31-batch enzyme mix.

    The production loop trains on 31 historical batches before the 15-run
    campaign.  The original benchmark started cold, which made the
    ``MIN_CLASS_ROWS=3`` guard exclude almost every enzyme.  This helper gives
    every policy the same free history so the guard can be tested under
    realistic class counts.  History rows do not consume campaign trials.
    """
    if n_rows <= 0:
        return pd.DataFrame()
    # ENZYMES order: Alcalase, Alcalase+Flavourzyme, Alcalase+Kojizyme,
    # Alcalase+Neutrase, Flavourzyme, Neutrase, Pepsin.
    base = np.array([20, 1, 2, 1, 2, 3, 2], dtype=int)  # real 31-batch counts
    if n_rows == int(base.sum()):
        counts = base
    else:
        if n_rows < len(ENZYMES):
            raise ValueError("history_rows must be 0 or at least the number of enzymes")
        raw = base / base.sum() * n_rows
        counts = np.floor(raw).astype(int)
        remainder = n_rows - int(counts.sum())
        order = np.argsort(-(raw - counts))
        counts[order[:remainder]] += 1
    enzymes: list[str] = []
    for enzyme, count in zip(ENZYMES, counts):
        enzymes.extend([enzyme] * int(count))
    rng.shuffle(enzymes)

    design = lab.candidate_space(n_rows, rng=rng, balanced_enzymes=False)
    design["Enzyme"] = enzymes
    design["EnzymeToSubstrateRatio"] = 0.02  # every real historical row is 0.02
    design["BatchID"] = [f"HIST_{i:03d}" for i in range(1, n_rows + 1)]
    return design


def run_world_task(task: tuple[int, dict[str, Any]]) -> dict[str, Any]:
    world_seed, cfg_dict = task
    cfg = BenchmarkConfig(**cfg_dict)
    try:
        import torch
        torch.set_num_threads(1)
    except Exception:
        pass

    lab = SyntheticLab(world_seed)
    seed_design = lab.seed_design()
    seed_rng = np.random.default_rng(world_seed * 1000 + 7)
    seed_data = lab.measure(seed_design, rng=seed_rng, trial_start=1,
                            budget=cfg.budget)
    history_data = pd.DataFrame()
    if cfg.history_rows:
        history_design = _legacy_design(
            lab, cfg.history_rows, np.random.default_rng(world_seed * 1000 + 11))
        history_data = lab.measure(
            history_design, rng=np.random.default_rng(world_seed * 1000 + 12),
            trial_start=0, budget=cfg.budget)
    training_data = pd.concat([history_data, seed_data], ignore_index=True)
    oracle = lab.oracle_table(n=cfg.oracle_candidates, refine=True)

    policies: dict[str, Any] = {}
    histories: list[pd.DataFrame] = []
    for name in cfg.policies:
        policy = make_policy(name, world_seed, training_data, cfg, lab, oracle)
        hist_rows = [
            _history_row(world_seed, name, "seed", 0, row)
            for row in seed_data.itertuples()
        ]
        n_adaptive = cfg.budget - len(seed_data)
        n_rounds = int(np.ceil(max(n_adaptive, 0) / cfg.batch))
        for r in range(n_rounds):
            n_new = min(cfg.batch, cfg.budget - len(seed_data) - r * cfg.batch)
            if n_new <= 0:
                break
            props = policy.propose(n_new)
            trial_start = len(seed_data) + r * cfg.batch + 1
            measured = lab.measure(props, rng=policy.measure_rng,
                                   trial_start=trial_start, budget=cfg.budget)
            policy.observe(measured)
            hist_rows.extend(
                _history_row(world_seed, name, "adaptive", r + 1, row)
                for row in measured.itertuples()
            )
        hist = pd.DataFrame(hist_rows)
        histories.append(hist)
        policies[name] = policy_metrics(hist, oracle["best_dh"],
                                        oracle["best_orac"], cfg)

    return {
        "world": int(world_seed),
        "oracle": {"best_dh": float(oracle["best_dh"]),
                   "best_orac": float(oracle["best_orac"]),
                   "n_evaluated": int(oracle["n_evaluated"])},
        "policies": policies,
        "histories": histories,
    }


# -------------------------------------------------------------------- summary
def _bootstrap_ci(values, n_boot: int = 2000, seed: int = 7) -> list[float]:
    vals = np.asarray(values, dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(vals, len(vals), replace=True).mean()
                      for _ in range(n_boot)])
    lo, hi = np.percentile(means, [2.5, 97.5])
    return [float(lo), float(hi)]


def _policy_summary(g: pd.DataFrame) -> dict[str, Any]:
    reached = g.loc[g["reached_95"], "trials_to_95"]
    d: dict[str, Any] = {
        "n_worlds": int(len(g)),
        "reached_95_pct": float(100.0 * g["reached_95"].mean()),
        "trials_to_95_median_reached": float(reached.median()) if len(reached) else None,
        "trials_to_95_mean_censored": float(g["trials_to_95"].mean()),
        "reached_80_pct": float(100.0 * g["reached_80"].mean()),
        "trials_to_80_median_reached": (
            float(g.loc[g["reached_80"], "trials_to_80"].median())
            if g["reached_80"].any() else None),
        "reached_90_pct": float(100.0 * g["reached_90"].mean()),
        "trials_to_90_median_reached": (
            float(g.loc[g["reached_90"], "trials_to_90"].median())
            if g["reached_90"].any() else None),
        "reached_noise_pct": float(100.0 * g["reached_noise"].mean()),
        "trials_to_noise_median_reached": (
            float(g.loc[g["reached_noise"], "trials_to_noise"].median())
            if g["reached_noise"].any() else None),
        "best_true_mean": float(g["best_true"].mean()),
        "best_true_median": float(g["best_true"].median()),
        "best_true_ci": _bootstrap_ci(g["best_true"]),
        "regret_true_mean": float(g["regret_true"].mean()),
        "regret_true_median": float(g["regret_true"].median()),
        "regret_true_ci": _bootstrap_ci(g["regret_true"]),
        "selected_true_mean": float(g["selected_true"].mean()),
        "selected_true_median": float(g["selected_true"].median()),
        "best_measured_mean": float(g["best_measured"].mean()),
        "best_orac_true_mean": float(g["best_orac_true"].mean()),
        "orac_at_selected_mean": float(g["orac_at_selected"].mean()),
        "orac_regret_mean": float(g["orac_regret"].mean()),
        "n_gross_mean": float(g["n_gross"].mean()),
    }
    for key in ["ei_spearman_improvement_mean", "ei_spearman_true_mean",
                "ei_top_hit_rate", "ei_top_improved_rate", "ei_vs_true_pooled",
                "expected_vs_true_pooled", "ei_vs_measured_pooled"]:
        vals = g[key].dropna()
        d[key] = float(vals.mean()) if len(vals) else None
    return d


def _pairwise(df: pd.DataFrame, a: str, b: str) -> dict[str, Any]:
    ga = df[df["policy"] == a].set_index("world")["best_true"]
    gb = df[df["policy"] == b].set_index("world")["best_true"]
    common = ga.index.intersection(gb.index)
    if len(common) == 0:
        return {"n": 0}
    diff = (ga.loc[common] - gb.loc[common]).to_numpy(float)
    return {
        "n": int(len(diff)),
        "mean_diff": float(diff.mean()),
        "ci": _bootstrap_ci(diff),
        "a_wins_pct": float(100.0 * (diff > 0).mean()),
        "ties_pct": float(100.0 * (diff == 0).mean()),
    }


def summarize(results: list[dict[str, Any]], cfg: BenchmarkConfig) -> dict[str, Any]:
    rows = []
    for res in results:
        for policy, m in res["policies"].items():
            rows.append({"world": res["world"], "policy": policy, **m})
    df = pd.DataFrame(rows)
    splits = {
        "all": df,
        "dev": df[df["world"] < cfg.split_at],
        "test": df[df["world"] >= cfg.split_at],
    }
    out: dict[str, Any] = {"splits": {}, "pairwise": {}, "win_rates": {}}
    for name, sub in splits.items():
        if len(sub) == 0:
            out["splits"][name] = {}
            continue
        out["splits"][name] = {
            policy: _policy_summary(g) for policy, g in sub.groupby("policy")
        }
        # Winner = highest true best among the non-oracle policies.  Split
        # credit among exact ties; otherwise the first policy in the frame
        # would "win" every world where no policy improved on the seed.
        non_oracle = sub[sub["policy"] != "oracle"].copy()
        best_per_world = non_oracle.groupby("world")["best_true"].transform("max")
        non_oracle["is_best"] = np.isclose(non_oracle["best_true"],
                                           best_per_world, rtol=0.0, atol=1e-9)
        non_oracle["n_best"] = non_oracle.groupby("world")["is_best"].transform("sum")
        non_oracle["credit"] = non_oracle["is_best"] / non_oracle["n_best"]
        n_worlds = int(non_oracle["world"].nunique())
        out["win_rates"][name] = {
            p: float(100.0 * g["credit"].sum() / max(n_worlds, 1))
            for p, g in non_oracle.groupby("policy")
        }
        pairs = [("twin_current", "random"), ("twin_current", "lhc"),
                 ("twin_current", "ofat"), ("twin_current", "grid"),
                 ("twin_explore", "random"), ("twin_explore", "lhc"),
                 ("twin_current", "twin_explore")]
        out["pairwise"][name] = {
            f"{a} vs {b}": _pairwise(sub, a, b) for a, b in pairs
            if a in set(sub["policy"]) and b in set(sub["policy"])
        }
    n_dev_worlds = (int(splits["dev"]["world"].nunique())
                    if len(splits["dev"]) else 0)
    n_test_worlds = (int(splits["test"]["world"].nunique())
                     if len(splits["test"]) else 0)
    out["headline_split"] = (
        "test" if n_test_worlds >= 20
        else "dev" if n_dev_worlds >= 20
        else "all")
    out["worlds"] = sorted(int(w) for w in df["world"].unique())
    out["n_worlds"] = len(out["worlds"])
    out["split_at"] = int(cfg.split_at)
    return out


def _fmt(v, digits: int = 1, suffix: str = "") -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    return f"{v:.{digits}f}{suffix}"


def _world_label(ids: list[int]) -> str:
    """Compact label for a possibly non-contiguous set of world seeds."""
    ids = sorted(int(w) for w in ids)
    if not ids:
        return "no worlds"
    groups: list[tuple[int, int]] = []
    start = prev = ids[0]
    for world in ids[1:]:
        if world == prev + 1:
            prev = world
            continue
        groups.append((start, prev))
        start = prev = world
    groups.append((start, prev))
    if len(groups) == 1:
        a, b = groups[0]
        return f"worlds {a}–{b}" if a != b else f"world {a}"
    parts = [f"{a}–{b}" if a != b else str(a) for a, b in groups]
    return f"worlds {', '.join(parts)}"


def write_summary_md(summary: dict[str, Any], cfg: BenchmarkConfig,
                     path: Path, elapsed: float,
                     world_ids: list[int] | None = None,
                     failures: dict[str, str] | None = None,
                     config_hash: str | None = None) -> None:
    split = summary["headline_split"]
    head = summary["splits"][split]
    ids = sorted(int(w) for w in (world_ids if world_ids is not None
                                  else summary.get("worlds", [])))
    if split == "test":
        ids = [w for w in ids if w >= cfg.split_at]
        split_label = f"held-out {_world_label(ids)}"
    elif split == "dev":
        ids = [w for w in ids if w < cfg.split_at]
        split_label = f"development {_world_label(ids)}"
    else:
        split_label = f"all {_world_label(ids)} — no held-out split"
    n_worlds = len(ids)
    n_rounds = int(np.ceil(max(cfg.budget - 15, 0) / cfg.batch))
    round_word = "round" if n_rounds == 1 else "rounds"
    smoke = cfg.quick or n_worlds < 20
    failures = failures or {}
    lines = [
        "# Synthetic policy benchmark — does the loop reduce trials?",
        "",
        "> **This is synthetic evidence, not a real-world trial-reduction claim.**",
        "> The generator is a plausible two-pool hydrolysis world with lot effects,",
        "> substrate inhibition, assay noise, 5% gross errors and non-monotonic ORAC.",
        "> It is deliberately richer than the twin. A win here is necessary, not sufficient.",
        "",
    ]
    if smoke:
        lines += [
            "> **Smoke/development run — not a benchmark result.** "
            "It checks the harness, not the policy. Quote only a run with a "
            "held-out split of at least 20 worlds.",
            "",
        ]
    if split != "test":
        lines += [
            "> **Development run — not held-out evidence.** Use it to tune or "
            "debug; quote only a held-out run.",
            "",
        ]
    if failures:
        lines += [
            f"> **Partial run:** {len(failures)} world(s) failed and are excluded "
            "from every metric. See the run's `manifest.json`. Do not quote this "
            "as a complete benchmark.",
            "",
        ]
    lines += [
        f"Generated: {pd.Timestamp.now():%Y-%m-%d %H:%M}  ",
        f"Worlds: **{n_worlds}** ({_world_label(ids)}); headline split: "
        f"**{split_label}**.  ",
        f"Budget: **{cfg.budget} runs** (15-run seed campaign + "
        f"{n_rounds} adaptive {round_word} × {cfg.batch}).  ",
        f"EBM settings: epochs={cfg.epochs}, n_aug={cfg.n_aug}, "
        f"n_cand={cfg.n_cand}, Langevin={cfg.langevin_steps} steps × "
        f"{cfg.chains} chains (EI chunk {cfg.ei_chunk}); "
        f"oracle candidates={cfg.oracle_candidates:,}.  ",
        f"Config hash: `{config_hash or 'n/a'}`; git `{_git_commit()}`; "
        f"failed worlds: {len(failures)}.  ",
        f"Runtime: {elapsed / 60:.1f} min.",
        "",
        f"## Headline — {split_label}",
        "",
        "Primary metric: **mean best true DH at the run budget**. "
        "The 95%-of-oracle and lab-precision columns are secondary.",
        "",
        "| Policy | Mean best true DH | Mean true regret | Reached 95% of oracle | "
        "Trials to 95% (median, reached) | Selected true DH | Best measured | ORAC at selected |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    order = [p for p in POLICY_ORDER if p in head]
    for p in order:
        d = head[p]
        trials = _fmt(d["trials_to_95_median_reached"], 1)
        if d["trials_to_95_median_reached"] is None:
            trials = "not reached"
        lines.append(
            f"| `{p}` | {_fmt(d['best_true_mean'], 1)} | "
            f"{_fmt(d['regret_true_mean'], 1)} | "
            f"{_fmt(d['reached_95_pct'], 1, '%')} | {trials} | "
            f"{_fmt(d['selected_true_mean'], 1)} | "
            f"{_fmt(d['best_measured_mean'], 1)} | "
            f"{_fmt(d['orac_at_selected_mean'], 0)} |")
    win = summary.get("win_rates", {}).get(split, {})
    lines += [
        "",
        "## Win rates (ties split)",
        "",
        "Share of worlds where the policy had the highest best true DH; exact "
        "ties split credit equally. The oracle is excluded (it is an upper bound).",
        "",
        "| Policy | Win rate |",
        "|---|---:|",
    ]
    for p in order:
        if p == "oracle":
            continue
        lines.append(f"| `{p}` | {_fmt(win.get(p), 1, '%')} |")
    lines += [
        "",
        "`Selected true DH` is the true DH of the run the lab would advance "
        "(highest *measured* DH). It exposes the winner's curse: a gross error can "
        "make a bad run look best. `Best measured` is what the lab believes it found.",
        "",
        "## Target sensitivity",
        "",
        "A single 95% threshold can censor every policy. The 80% and 90% columns "
        "show whether the ranking is an artefact of that threshold.",
        "",
        "| Policy | Reached 80% | Trials to 80% | Reached 90% | Trials to 90% | "
        "Reached 95% | Trials to 95% |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for p in order:
        d = head[p]
        def _t(level: int) -> str:
            med = d.get(f"trials_to_{level}_median_reached")
            return _fmt(med, 1) if med is not None else "not reached"
        lines.append(
            f"| `{p}` | {_fmt(d.get('reached_80_pct'), 1, '%')} | {_t(80)} | "
            f"{_fmt(d.get('reached_90_pct'), 1, '%')} | {_t(90)} | "
            f"{_fmt(d.get('reached_95_pct'), 1, '%')} | {_t(95)} |")
    lines += [
        "",
        "## Lab-precision target — oracle best − 2.1 DH",
        "",
        "2.1 DH is twice the real-replicate repeatability (1.07 DH, "
        "the internal noise-floor notes). This is the strictest target: a policy that "
        "reaches it is at the limit of what the real assay can distinguish. "
        "The synthetic assay noise is deliberately larger than the real "
        "repeatability, so low reach rates here are expected.",
        "",
        "| Policy | Reached | Trials (median, reached) |",
        "|---|---:|---:|",
    ]
    for p in order:
        d = head[p]
        noise_trials = d.get("trials_to_noise_median_reached")
        lines.append(
            f"| `{p}` | {_fmt(d.get('reached_noise_pct'), 1, '%')} | "
            f"{_fmt(noise_trials, 1) if noise_trials is not None else 'not reached'} |")
    lines += [
        "",
        "## Uncertainty",
        "",
        "| Policy | Best true DH mean [95% CI] | True regret mean [95% CI] |",
        "|---|---:|---:|",
    ]
    for p in order:
        d = head[p]
        bt = d.get("best_true_ci") or [None, None]
        rt = d.get("regret_true_ci") or [None, None]
        lines.append(
            f"| `{p}` | {_fmt(d['best_true_mean'], 1)} "
            f"[{_fmt(bt[0], 1)}, {_fmt(bt[1], 1)}] | "
            f"{_fmt(d['regret_true_mean'], 1)} "
            f"[{_fmt(rt[0], 1)}, {_fmt(rt[1], 1)}] |")
    lines += [
        "",
        "## Is EI informative?",
        "",
        "| Policy | EI vs realised improvement (mean ρ) | Top-EI hit rate | "
        "Top-EI improved rate | EI vs true DH (pooled ρ) | Expected DH vs true DH (pooled ρ) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for p in order:
        d = head[p]
        if d.get("ei_spearman_improvement_mean") is None:
            continue
        lines.append(
            f"| `{p}` | {_fmt(d['ei_spearman_improvement_mean'], 2)} | "
            f"{_fmt(d['ei_top_hit_rate'], 1, '%')} | "
            f"{_fmt(d['ei_top_improved_rate'], 1, '%')} | "
            f"{_fmt(d['ei_vs_true_pooled'], 2)} | "
            f"{_fmt(d['expected_vs_true_pooled'], 2)} |")
    lines += [
        "",
        "Top-EI hit rate is the fraction of rounds where the highest-EI proposal had "
        f"the highest true DH; chance with {cfg.batch} proposals is "
        f"{100.0 / max(cfg.batch, 1):.0f}%. A high EI that ranks "
        "low-quality runs is the 'EI rewards ignorance' pathology.",
        "",
        f"## Pairwise — {split_label}",
        "",
        "| Comparison | Mean difference (DH) | 95% CI | A wins |",
        "|---|---:|---|---:|",
    ]
    for label, d in summary["pairwise"].get(split, {}).items():
        if d.get("n", 0) == 0:
            continue
        lines.append(
            f"| {label} | {_fmt(d['mean_diff'], 2)} | "
            f"[{_fmt(d['ci'][0], 2)}, {_fmt(d['ci'][1], 2)}] | "
            f"{_fmt(d['a_wins_pct'], 1, '%')} |")
    lines += [
        "",
        "## What this means",
        "",
    ]
    twin = head.get("twin_current")
    rand = head.get("random")
    lhc = head.get("lhc")
    oracle = head.get("oracle")
    explore = head.get("twin_explore")
    if order:
        lines.append(
            f"- Primary metric (mean best true DH at {cfg.budget} runs): "
            + ", ".join(f"`{p}` {head[p]['best_true_mean']:.1f}" for p in order)
            + ".")
    if twin and rand:
        delta = twin["best_true_mean"] - rand["best_true_mean"]
        if delta > 0:
            verb = "ahead of"
        elif delta < 0:
            verb = "behind"
        else:
            verb = "tied with"
        lines.append(
            f"- At the {cfg.budget}-run budget, the current EBM loop averaged "
            f"**{twin['best_true_mean']:.1f}% true DH**, {verb} random search "
            f"({rand['best_true_mean']:.1f}%; difference {delta:+.1f} DH).")
        lines.append(
            f"- It reached 95% of the oracle in **{twin['reached_95_pct']:.0f}%** "
            f"of worlds vs **{rand['reached_95_pct']:.0f}%** for random"
            + (f" and **{lhc['reached_95_pct']:.0f}%** for LHC." if lhc else "."))
        lines.append(
            f"- The lab-facing selected run averaged **{twin['selected_true_mean']:.1f}%** "
            f"true DH (random {rand['selected_true_mean']:.1f}%), showing the cost of "
            f"choosing on noisy measurements.")
    if twin and explore:
        delta = explore["best_true_mean"] - twin["best_true_mean"]
        lines.append(
            f"- The `MIN_CLASS_ROWS=1` ablation averaged "
            f"**{explore['best_true_mean']:.1f}%** true DH "
            f"({delta:+.1f} DH vs the production guard), isolating the eligibility "
            f"filter from the rest of the acquisition.")
    if twin and twin.get("ei_spearman_improvement_mean") is not None:
        lines.append(
            f"- EI rank vs realised improvement: mean ρ = "
            f"**{twin['ei_spearman_improvement_mean']:.2f}**; the top-EI proposal "
            f"was the best of its batch **{twin['ei_top_hit_rate']:.0f}%** of the time "
            f"(chance 33%).")
    if twin and oracle:
        lines.append(
            f"- ORAC at the selected best-DH run averaged **{twin['orac_at_selected_mean']:.0f}** "
            f"vs an oracle ORAC upper bound of about **{oracle['best_orac_true_mean']:.0f}**. "
            f"The current acquisition does not target ORAC; this gap is expected.")
    if twin and rand and twin["best_true_mean"] <= rand["best_true_mean"]:
        lines += [
            "",
            f"**In this run, the current EBM did not beat random search** "
            f"(difference {twin['best_true_mean'] - rand['best_true_mean']:+.1f} DH). "
            "If this holds on the held-out split, that is the finding. The next "
            "step is to fix the acquisition — global candidates, E/S as a feature, "
            "a distance/uncertainty penalty, and a robust loss — then rerun on "
            "development and report held-out. Do not relabel this as a win.",
        ]
    lines += [
        "",
        "## Method",
        "",
        "- **World:** `src/synthetic_lab.py`, model `two_pool_exposure_v1`. "
        "Two substrate pools, enzyme exposure with first-order deactivation, "
        "substrate inhibition, enzyme-specific asymmetric pH optima, Arrhenius "
        "catalysis, lot-to-lot activity, substrate-batch susceptibility, real "
        "material compositions bootstrapped from the 31 real batches.",
        "- **Seed design:** 15 runs with the same arm structure as the real campaign "
        "(7 gap-fill, 5 process LHC, 3 dose sweep). Every policy sees the same "
        "measured seed data, including its gross errors.",
        f"- **Oracle:** true top runs from {cfg.oracle_candidates:,} space-filling "
        "candidates plus local refinement. It is a finite approximation of the "
        "true global optimum.",
        f"- **Primary metric:** mean best *true* DH at the run budget "
        f"({cfg.budget} runs, including the 15-run seed campaign). "
        "Secondary: trials to 95% of oracle, "
        "trials to the lab-precision band, true regret, and the lab-facing selected "
        "run.",
        "- **Regret:** oracle best true DH minus the policy's best true DH. "
        "`regret_selected` uses the run the lab would pick by measured DH.",
        "- **Held-out split:** worlds below 100 are development; worlds 100+ are "
        "held-out. Step-5 tuning must not use the held-out half.",
        "",
        "## Caveats (read before quoting any number)",
        "",
        "- **Synthetic ≠ real.** The generator is a stress test, not a validated "
        "model. Parameter ranges are literature-anchored and qualitatively matched "
        "to the real data, but not fitted. See the internal parameter-provenance notes.",
        f"- **The oracle is finite.** {cfg.oracle_candidates:,} candidates + "
        "refinement can miss the true optimum; regret is therefore a lower bound "
        "on the true regret.",
        "- **Noise matters.** A 5% gross-error rate and 1.5–3.5 DH occasion noise "
        "mean the highest measured run is not always the best true run. The "
        "`selected_true` column is the honest lab-facing metric.",
        f"- **Reduced EBM fidelity.** This run used epochs={cfg.epochs}, "
        f"n_aug={cfg.n_aug}, n_cand={cfg.n_cand}, Langevin={cfg.langevin_steps}×"
        f"{cfg.chains}. Production (`run_ebm_loop.py`) uses 800 epochs and 500 "
        "candidates. The relative ranking is the claim; the 500-candidate "
        "sensitivity check is the guard against a budget artefact.",
        "- **Conditional on the seed design.** A different 15-run campaign could "
        "change the ranking. The world sample varies world parameters, not campaign "
        "designs.",
        "- **Chunked runs are resumable, not pooled.** Per-world files live under "
        "`data/synthetic/runs/<prefix>/`; the config hash refuses to mix settings "
        "or code versions.",
        "",
        "## Reproduce",
        "",
        "```powershell",
    ]
    all_ids = sorted(int(w) for w in summary.get("worlds", []))
    contiguous = bool(all_ids) and all_ids == list(range(all_ids[0], all_ids[-1] + 1))
    if contiguous:
        lines.append(
            f"python -m src.benchmark_policy --worlds {len(all_ids)} "
            f"--world-start {all_ids[0]} --budget {cfg.budget} "
            f"--batch {cfg.batch} --epochs {cfg.epochs} --n-aug {cfg.n_aug} "
            f"--n-cand {cfg.n_cand} --langevin-steps {cfg.langevin_steps} "
            f"--chains {cfg.chains} --ei-chunk {cfg.ei_chunk} "
            f"--oracle-candidates {cfg.oracle_candidates} "
            f"--workers {min(max(int(cfg.workers), 1), MAX_WORKERS)} "
            f"--policies {','.join(cfg.policies)} --resume")
    else:
        lines.append(
            "# Non-contiguous chunks: rerun each chunk with the same --prefix "
            "and --resume; see the run manifest.")
    lines += [
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# -------------------------------------------------------------------- runner
@lru_cache(maxsize=1)
def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=BASE, text=True).strip()
    except Exception:
        return "unknown"


@lru_cache(maxsize=1)
def _code_hash() -> str:
    """Hash the three modules that define the benchmark's truth and policy.

    The settings hash alone is not enough: editing the EBM or the generator
    between chunks would silently mix incompatible worlds.  Any code change
    forces a new prefix.
    """
    digest = hashlib.sha256()
    for rel in ("src/benchmark_policy.py", "src/ebm_optimizer.py",
                "src/synthetic_lab.py"):
        digest.update((BASE / rel).read_bytes())
    return digest.hexdigest()[:16]


def _config_identity(cfg: BenchmarkConfig) -> dict[str, Any]:
    """Settings that must match across chunks of the same run.

    World range and worker count are deliberately excluded: chunks cover
    different ranges and may use a different worker count.  Everything that can
    change a metric is included, plus the code hash.
    """
    d = _jsonable(asdict(cfg))
    for key in ("n_worlds", "world_start", "workers", "quick"):
        d.pop(key, None)
    d["schema"] = SCHEMA_VERSION
    d["model"] = MODEL_NAME
    d["code_hash"] = _code_hash()
    return d


def _config_hash(cfg: BenchmarkConfig) -> str:
    blob = json.dumps(_config_identity(cfg), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _run_dir(prefix: str) -> Path:
    return RUNS_DIR / prefix


def _manifest_path(prefix: str) -> Path:
    return _run_dir(prefix) / "manifest.json"


def _world_json_path(prefix: str, world: int) -> Path:
    return _run_dir(prefix) / f"world_{int(world):03d}.json"


def _world_hist_path(prefix: str, world: int) -> Path:
    return _run_dir(prefix) / f"world_{int(world):03d}_histories.csv"


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(_jsonable(payload), indent=2, allow_nan=False),
                   encoding="utf-8")
    tmp.replace(path)


def _load_manifest(prefix: str) -> dict[str, Any] | None:
    path = _manifest_path(prefix)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest(prefix: str, manifest: dict[str, Any]) -> None:
    manifest["updated"] = pd.Timestamp.now().isoformat(timespec="seconds")
    _write_json_atomic(_manifest_path(prefix), manifest)


def _new_manifest(prefix: str, cfg: BenchmarkConfig,
                  cfg_hash: str) -> dict[str, Any]:
    now = pd.Timestamp.now().isoformat(timespec="seconds")
    return {
        "schema": SCHEMA_VERSION,
        "prefix": prefix,
        "created": now,
        "updated": now,
        "git_commit": _git_commit(),
        "code_hash": _code_hash(),
        "config_hash": cfg_hash,
        "config": _config_identity(cfg),
        "model": MODEL_NAME,
        "worlds_requested": [],
        "worlds_completed": [],
        "worlds_failed": {},
        "status": "running",
    }


def _completed_worlds(prefix: str, cfg: BenchmarkConfig,
                      manifest: dict[str, Any]) -> set[int]:
    completed: set[int] = set()
    for raw in manifest.get("worlds_completed", []):
        world = int(raw)
        if not _world_json_path(prefix, world).exists():
            continue
        if cfg.save_histories and not _world_hist_path(prefix, world).exists():
            continue
        completed.add(world)
    return completed


def _available_ram_gb() -> float | None:
    if os.name == "nt":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return float(stat.ullAvailPhys) / (1024 ** 3)
        except Exception:
            pass
    try:
        import psutil
        return float(psutil.virtual_memory().available) / (1024 ** 3)
    except Exception:
        return None


def _worker_init() -> None:
    """Pin every worker to one BLAS/torch thread (memory + CPU safety)."""
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[var] = "1"
    try:
        import torch
        torch.set_num_threads(1)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            pass
    except Exception:
        pass


def _write_world(prefix: str, cfg: BenchmarkConfig, cfg_hash: str,
                 result: dict[str, Any]) -> None:
    world = int(result["world"])
    payload = {
        "world": world,
        "config_hash": cfg_hash,
        "oracle": result["oracle"],
        "policies": result["policies"],
    }
    _write_json_atomic(_world_json_path(prefix, world), payload)
    histories = result.get("histories") or []
    if cfg.save_histories:
        if not histories:
            raise RuntimeError(f"world {world} returned no histories")
        hist = pd.concat(histories, ignore_index=True)
        hist = hist[[c for c in HISTORY_COLS if c in hist.columns]]
        path = _world_hist_path(prefix, world)
        tmp = path.with_name(path.name + ".tmp")
        hist.to_csv(tmp, index=False)
        tmp.replace(path)


def _record_result(prefix: str, cfg: BenchmarkConfig, cfg_hash: str,
                   manifest: dict[str, Any], result: dict[str, Any],
                   completed: set[int], failed: dict[str, str]) -> None:
    world = int(result["world"])
    _write_world(prefix, cfg, cfg_hash, result)
    completed.add(world)
    failed.pop(str(world), None)
    manifest["worlds_completed"] = sorted(completed)
    manifest["worlds_failed"] = dict(failed)
    _write_manifest(prefix, manifest)


def _progress(done: int, total: int, world: int, t0: float) -> None:
    step = max(1, total // 10)
    if done == 1 or done % step == 0 or done == total:
        elapsed = time.time() - t0
        eta = elapsed * (total - done) / max(done, 1)
        print(f"  {done}/{total} worlds (seed {world}) "
              f"{elapsed:.0f}s elapsed, ~{eta:.0f}s left")


def _run_tasks(prefix: str, cfg: BenchmarkConfig, cfg_hash: str,
               manifest: dict[str, Any], missing: list[int], workers: int,
               completed: set[int], failed: dict[str, str]) -> None:
    total = len(missing)
    if total == 0:
        print("[benchmark] all requested worlds already complete")
        return
    print(f"[benchmark] running {total} world(s) with {workers} worker(s)")
    t0 = time.time()
    done = 0
    if workers == 1:
        for world in missing:
            try:
                result = run_world_task((world, asdict(cfg)))
            except Exception:
                failed[str(world)] = traceback.format_exc(limit=8)
                manifest["worlds_failed"] = dict(failed)
                _write_manifest(prefix, manifest)
                print(f"  world {world} FAILED; recorded in manifest")
                continue
            _record_result(prefix, cfg, cfg_hash, manifest, result,
                           completed, failed)
            done += 1
            _progress(done, total, world, t0)
        return

    # Recycle the pool every POOL_CHUNK worlds.  This bounds per-worker memory
    # growth on 8 GB machines and gives a clean retry boundary after a crash.
    for start in range(0, total, POOL_CHUNK):
        chunk = missing[start:start + POOL_CHUNK]
        with ProcessPoolExecutor(max_workers=workers,
                                 initializer=_worker_init) as ex:
            futures = {ex.submit(run_world_task, (world, asdict(cfg))): world
                       for world in chunk}
            for fut in as_completed(futures):
                world = futures[fut]
                try:
                    result = fut.result()
                except Exception:
                    failed[str(world)] = traceback.format_exc(limit=8)
                    manifest["worlds_failed"] = dict(failed)
                    _write_manifest(prefix, manifest)
                    print(f"  world {world} FAILED; recorded in manifest")
                    continue
                _record_result(prefix, cfg, cfg_hash, manifest, result,
                               completed, failed)
                done += 1
                _progress(done, total, world, t0)


def _load_world_results(prefix: str, cfg: BenchmarkConfig,
                        worlds: list[int]) -> tuple[list[dict[str, Any]],
                                                    list[pd.DataFrame]]:
    results: list[dict[str, Any]] = []
    histories: list[pd.DataFrame] = []
    cfg_hash = _config_hash(cfg)
    for world in worlds:
        payload = json.loads(
            _world_json_path(prefix, world).read_text(encoding="utf-8"))
        if payload.get("config_hash") != cfg_hash:
            raise SystemExit(
                f"world {world} was produced by a different configuration; "
                f"refusing to aggregate mixed settings")
        results.append({
            "world": int(payload["world"]),
            "oracle": payload["oracle"],
            "policies": payload["policies"],
        })
        if cfg.save_histories:
            histories.append(pd.read_csv(_world_hist_path(prefix, world)))
    return results, histories


def _aggregate(prefix: str, cfg: BenchmarkConfig, cfg_hash: str,
               completed: set[int], failed: dict[str, str],
               elapsed: float) -> tuple[dict[str, Any], Path, Path]:
    worlds = sorted(completed)
    if not worlds:
        raise SystemExit("no completed worlds; refusing to write a summary")
    results, histories = _load_world_results(prefix, cfg, worlds)
    summary_cfg = replace(cfg, n_worlds=len(worlds), world_start=min(worlds))
    summary = summarize(results, summary_cfg)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "generated": pd.Timestamp.now().isoformat(timespec="seconds"),
            "git_commit": _git_commit(),
            "code_hash": _code_hash(),
            "config_hash": cfg_hash,
            "config": _jsonable(asdict(cfg)),
            "runtime_sec": round(elapsed, 1),
            "model": MODEL_NAME,
            "worlds_completed": worlds,
            "worlds_failed": dict(failed),
            "run_dir": str(_run_dir(prefix)),
            "note": "Synthetic benchmark. Not real data. See the internal parameter-provenance notes.",
        },
        "summary": summary,
        "worlds": results,
    }
    json_path = OUT_DIR / f"{prefix}.json"
    _write_json_atomic(json_path, payload)

    if cfg.save_histories and histories:
        hist = pd.concat(histories, ignore_index=True)
        hist = hist[[c for c in HISTORY_COLS if c in hist.columns]]
        path = OUT_DIR / f"{prefix}_histories.csv"
        tmp = path.with_name(path.name + ".tmp")
        hist.to_csv(tmp, index=False)
        tmp.replace(path)

    md_path = OUT_DIR / f"{prefix}_summary.md"
    write_summary_md(summary, summary_cfg, md_path, elapsed,
                     world_ids=worlds, failures=failed, config_hash=cfg_hash)
    return payload, json_path, md_path


def run_benchmark(cfg: BenchmarkConfig, prefix: str = "benchmark",
                  resume: bool = False, overwrite: bool = False,
                  min_free_gb: float = 2.5) -> dict[str, Any]:
    t0 = time.time()
    if not prefix or Path(prefix).name != prefix:
        raise SystemExit("prefix must be a simple name (no path separators)")
    if resume and overwrite:
        raise SystemExit("--resume and --overwrite are mutually exclusive")

    workers = 1 if cfg.quick else max(1, int(cfg.workers))
    if workers > MAX_WORKERS:
        print(f"[benchmark] WARNING: workers={workers} exceeds the safe cap of "
              f"{MAX_WORKERS}; using {MAX_WORKERS}")
        workers = MAX_WORKERS
    available = _available_ram_gb()
    required = min_free_gb if workers > 1 else min(1.0, min_free_gb)
    if min_free_gb > 0 and available is not None and available < required:
        raise SystemExit(
            f"only {available:.1f} GB RAM available; {required:.1f} GB required "
            f"for {workers} worker(s). Close other apps, use --workers 1, or "
            f"pass --min-free-gb 0 to override.")
    if available is not None:
        print(f"[benchmark] available RAM: {available:.1f} GB")

    cfg_hash = _config_hash(cfg)
    run_dir = _run_dir(prefix)
    if overwrite:
        if run_dir.exists():
            shutil.rmtree(run_dir)
        for suffix in (".json", "_histories.csv", "_summary.md"):
            path = OUT_DIR / f"{prefix}{suffix}"
            if path.exists():
                path.unlink()

    manifest = _load_manifest(prefix)
    requested = [cfg.world_start + i for i in range(cfg.n_worlds)]
    if manifest is not None:
        if manifest.get("config_hash") != cfg_hash:
            raise SystemExit(
                f"run '{prefix}' exists with a different configuration or code "
                f"version (hash {manifest.get('config_hash')} != {cfg_hash}). "
                f"Use a new --prefix; do not mix settings.")
        if not resume:
            raise SystemExit(
                f"run '{prefix}' already exists at {run_dir}. Pass --resume to "
                f"add missing worlds, or --overwrite to start over.")
        completed = _completed_worlds(prefix, cfg, manifest)
        failed = {str(k): v for k, v in manifest.get("worlds_failed", {}).items()}
        manifest["worlds_requested"] = sorted(
            set(int(w) for w in manifest.get("worlds_requested", []))
            | set(requested))
        _write_manifest(prefix, manifest)
        print(f"[benchmark] resuming {prefix}: {len(completed)} world(s) complete")
    else:
        if (OUT_DIR / f"{prefix}.json").exists() and not overwrite:
            raise SystemExit(
                f"{OUT_DIR / (prefix + '.json')} exists but no run directory was "
                f"found. Pass --overwrite or use a new --prefix.")
        completed = set()
        failed = {}
        manifest = _new_manifest(prefix, cfg, cfg_hash)
        manifest["worlds_requested"] = sorted(requested)
        _write_manifest(prefix, manifest)
        print(f"[benchmark] new run {prefix} at {run_dir}")

    missing = [world for world in requested if world not in completed]
    print(f"[benchmark] config hash {cfg_hash}; requested {len(requested)} "
          f"world(s), {len(missing)} to run, workers={workers}")
    _run_tasks(prefix, cfg, cfg_hash, manifest, missing, workers,
               completed, failed)

    if not completed:
        raise SystemExit("no worlds completed; refusing to write a summary")
    manifest["status"] = "complete" if not failed else "partial"
    manifest["worlds_completed"] = sorted(completed)
    manifest["worlds_failed"] = dict(failed)
    _write_manifest(prefix, manifest)

    elapsed = time.time() - t0
    payload, json_path, md_path = _aggregate(
        prefix, cfg, cfg_hash, completed, failed, elapsed)
    print(f"[benchmark] wrote {json_path}")
    print(f"[benchmark] wrote {md_path}")
    split = payload["summary"]["headline_split"]
    head = payload["summary"]["splits"][split]
    for p in [x for x in POLICY_ORDER if x in head]:
        d = head[p]
        print(f"  {p:<14} reached95={d['reached_95_pct']:5.1f}%  "
              f"best_true={d['best_true_mean']:5.1f}  "
              f"regret={d['regret_true_mean']:5.1f}  "
              f"selected={d['selected_true_mean']:5.1f}")
    if failed:
        print(f"[benchmark] WARNING: {len(failed)} world(s) failed; see manifest")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Benchmark the acquisition loop in the synthetic lab.")
    ap.add_argument("--worlds", type=int, default=200)
    ap.add_argument("--world-start", type=int, default=0)
    ap.add_argument("--budget", type=int, default=30)
    ap.add_argument("--batch", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20261029)
    ap.add_argument("--epochs", type=int, default=250)
    ap.add_argument("--n-aug", type=int, default=6)
    ap.add_argument("--n-cand", type=int, default=150)
    ap.add_argument("--langevin-steps", type=int, default=120)
    ap.add_argument("--chains", type=int, default=4)
    ap.add_argument("--ei-chunk", type=int, default=64,
                    help="candidates per batched EI/Langevin pass")
    ap.add_argument("--oracle-candidates", type=int, default=50000)
    ap.add_argument("--history-rows", type=int, default=0,
                    help="free pre-campaign history rows (31 mimics the real "
                         "31-batch history); 0 = cold start")
    ap.add_argument("--workers", type=int, default=2,
                    help=f"parallel worlds (safe cap {MAX_WORKERS} on 8 GB)")
    ap.add_argument("--min-free-gb", type=float, default=2.5,
                    help="abort below this much free RAM (0 disables)")
    ap.add_argument("--policies", default=",".join(POLICY_ORDER))
    ap.add_argument("--prefix", default="benchmark")
    ap.add_argument("--resume", action="store_true",
                    help="add missing worlds to an existing prefix")
    ap.add_argument("--overwrite", action="store_true",
                    help="delete an existing run directory and start over")
    ap.add_argument("--no-histories", action="store_true")
    ap.add_argument("--quick", action="store_true",
                    help="4 worlds, 18 runs, tiny EBM settings (smoke test)")
    args = ap.parse_args()
    if args.worlds < 1:
        raise SystemExit("--worlds must be >= 1")
    if args.resume and args.overwrite:
        raise SystemExit("--resume and --overwrite are mutually exclusive")

    policies = tuple(p.strip() for p in args.policies.split(",") if p.strip())
    unknown = [p for p in policies if p not in POLICY_ORDER]
    if unknown:
        raise SystemExit(f"unknown policy/policies: {unknown}")
    cfg = BenchmarkConfig(
        n_worlds=args.worlds, world_start=args.world_start,
        budget=args.budget, batch=args.batch, seed=args.seed,
        epochs=args.epochs, n_aug=args.n_aug, n_cand=args.n_cand,
        langevin_steps=args.langevin_steps, chains=args.chains,
        ei_chunk=args.ei_chunk,
        oracle_candidates=args.oracle_candidates, workers=args.workers,
        policies=policies, save_histories=not args.no_histories,
        history_rows=args.history_rows,
    )
    if args.quick:
        cfg.n_worlds = 4
        cfg.budget = 18
        cfg.batch = 3
        cfg.epochs = 80
        cfg.n_aug = 4
        cfg.n_cand = 40
        cfg.langevin_steps = 40
        cfg.chains = 2
        cfg.ei_chunk = 32
        cfg.oracle_candidates = 2000
        cfg.workers = 1
        cfg.quick = True
        cfg.policies = tuple(p for p in policies if p != "twin_explore")
    run_benchmark(cfg, prefix=args.prefix, resume=args.resume,
                  overwrite=args.overwrite, min_free_gb=args.min_free_gb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
