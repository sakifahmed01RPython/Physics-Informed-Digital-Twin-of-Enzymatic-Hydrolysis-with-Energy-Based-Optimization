"""synthetic_lab.py - an independent, richer in-silico world for policy benchmarks.

This is NOT the twin.  The twin is a one-pool Michaelis-Menten ODE fitted to
Alcalase.  This generator is a two-pool (fast + slow) hydrolysis model with a
closed-form enzyme-exposure term, substrate inhibition, enzyme-specific
pH/temperature optima, lot-to-lot activity, substrate-batch susceptibility,
assay noise, 5% gross errors, slow drift, and a non-monotonic ORAC response.

Why a different structure: generating benchmark data from the twin's own ODE
would only test the software, not the decision policy.  The benchmark is
allowed to be wrong about the real world; it must be hard enough that a policy
which wins there is not winning by construction.

Everything written by this module goes under ``data/synthetic/``.  Synthetic
rows must never be merged into ``data/processed/main_batch_clean.csv`` or any
golden file.

Model
-----
For a run with enzyme e, material m and process x = (pH, T, t, S0, E/S):

    S0_gL = S0 * protein_pct / 100
    E0    = (E/S) * S0_gL
    f_T   = exp(-Ea_cat/R * (1/T - 1/T_ref))
    kd    = kd_ref * exp(-Ea_deact/R * (1/T - 1/T_ref))
    exposure = (1 - exp(-kd*t)) / kd          # integral of active enzyme
    f_pH  = exp(-0.5*((pH-pH_opt)/sigma_side)^2)
    f_S   = 1 / (1 + (S0/Ki)^n)               # substrate inhibition
    A0    = lot * substrate_batch * (E0/E0_ref)^alpha
            * f_T * f_pH * f_S * f_collagen * f_lipid
    DH(t) = 100 * Pmax * [f_fast*(1-exp(-k1*A0*exposure))
                         + (1-f_fast)*(1-exp(-k2*A0*exposure))]

The exposure term makes the temperature optimum shift down as duration grows:
short runs reward Arrhenius acceleration, long runs punish deactivation.

ORAC is a Gaussian in DH (peak at an intermediate DH) plus enzyme/material
offsets; it is deliberately non-monotonic, so maximising DH is not the same as
maximising bioactivity.

References and the status of each parameter range are in the internal parameter-provenance notes.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
MAIN = BASE / "data" / "processed" / "main_batch_clean.csv"
SYNTH_DIR = BASE / "data" / "synthetic"

ENZYMES = ["Alcalase", "Alcalase+Flavourzyme", "Alcalase+Kojizyme",
           "Alcalase+Neutrase", "Flavourzyme", "Neutrase", "Pepsin"]
MATERIALS = ["cod_frames", "cod_heads", "herring_byproduct",
             "salmon_frames", "salmon_trimmings"]
COMPOSITION_COLS = ["Moisture_pct", "CrudeProtein_pct", "CrudeLipid_pct",
                    "Ash_pct", "Hydroxyproline_pct", "Collagen_pct"]
PROCESS_COLS = ["pH", "Temp_C", "Duration_min", "SubstrateConc_gL"]
ES_VALUES = (0.01, 0.02, 0.04, 0.06)

PROCESS_BOUNDS = {"pH": (2.0, 10.0), "Temp_C": (30.0, 60.0),
                  "Duration_min": (15.0, 300.0), "SubstrateConc_gL": (30.0, 70.0)}

R_GAS = 8.314
T_REF_K = 323.15                       # 50 C reference
E0_REF = 0.02 * 50.0 * 16.5 / 100.0    # 0.165 g/L at the campaign reference

# Enzyme windows used by the 15-run seed design (same arm structure as the
# real campaign).  These are design windows, not hard model constraints.
ENZYME_WINDOWS = {
    "Pepsin": ("pH", 2.0, 3.5, "Temp_C", 35, 40),
    "Flavourzyme": ("pH", 6.0, 8.0, "Temp_C", 45, 55),
    "Alcalase+Kojizyme": ("pH", 7.0, 8.5, "Temp_C", 50, 60),
    "Alcalase+Neutrase": ("pH", 7.0, 8.0, "Temp_C", 48, 55),
    "Alcalase+Flavourzyme": ("pH", 7.0, 8.0, "Temp_C", 50, 58),
}

# Base parameters at the 50 C / pH-optimum / S0=50 g/L / E/S=0.02 reference.
# Ranges are deliberately broad enough to cover literature-plausible values;
# the internal parameter-provenance notes labels every one as anchored, plausible or arbitrary.
BASE_SPECS: dict[str, dict[str, float]] = {
    "Alcalase": dict(pH_opt=8.0, sigma_lo=1.4, sigma_hi=1.1,
                     Ea_cat_kJ=42.0, Ea_deact_kJ=95.0, kd_ref=0.0025,
                     k1=0.060, k2=0.0065, f_fast=0.12, Pmax=0.52, alpha=0.65),
    "Neutrase": dict(pH_opt=7.0, sigma_lo=1.3, sigma_hi=1.2,
                     Ea_cat_kJ=30.0, Ea_deact_kJ=80.0, kd_ref=0.0040,
                     k1=0.045, k2=0.0025, f_fast=0.30, Pmax=0.50, alpha=0.60),
    "Flavourzyme": dict(pH_opt=7.0, sigma_lo=1.5, sigma_hi=1.4,
                        Ea_cat_kJ=30.0, Ea_deact_kJ=75.0, kd_ref=0.0040,
                        k1=0.012, k2=0.0005, f_fast=0.22, Pmax=0.38, alpha=0.55),
    "Pepsin": dict(pH_opt=2.5, sigma_lo=0.7, sigma_hi=0.9,
                   Ea_cat_kJ=15.0, Ea_deact_kJ=80.0, kd_ref=0.0100,
                   k1=0.025, k2=0.0010, f_fast=0.28, Pmax=0.48, alpha=0.55),
    "Alcalase+Kojizyme": dict(pH_opt=7.6, sigma_lo=1.5, sigma_hi=1.3,
                              Ea_cat_kJ=40.0, Ea_deact_kJ=90.0, kd_ref=0.0020,
                              k1=0.070, k2=0.0075, f_fast=0.15, Pmax=0.56, alpha=0.65),
    "Alcalase+Neutrase": dict(pH_opt=7.5, sigma_lo=1.4, sigma_hi=1.2,
                              Ea_cat_kJ=38.0, Ea_deact_kJ=88.0, kd_ref=0.0028,
                              k1=0.055, k2=0.0055, f_fast=0.18, Pmax=0.51, alpha=0.62),
    "Alcalase+Flavourzyme": dict(pH_opt=7.5, sigma_lo=1.4, sigma_hi=1.3,
                                 Ea_cat_kJ=38.0, Ea_deact_kJ=85.0, kd_ref=0.0030,
                                 k1=0.045, k2=0.0045, f_fast=0.18, Pmax=0.49, alpha=0.60),
}

_MAIN_CACHE: pd.DataFrame | None = None


def _load_main() -> pd.DataFrame:
    global _MAIN_CACHE
    if _MAIN_CACHE is None:
        _MAIN_CACHE = pd.read_csv(MAIN)
    return _MAIN_CACHE


def _jsonable(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays to plain JSON types.

    Non-finite floats become ``None`` so callers can serialise with
    ``allow_nan=False``.  A metric that is undefined (e.g. a rank correlation
    with no adaptive proposals) must be written as JSON null, never as NaN:
    NaN is not valid JSON and silently poisons downstream parsers.
    """
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (float, np.floating)):
        value = float(obj)
        return value if math.isfinite(value) else None
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    return obj


def _lhc(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    """Small Latin-hypercube sampler in [0,1]^d (no scipy dependency)."""
    u = np.empty((n, d), dtype=float)
    for j in range(d):
        u[:, j] = (rng.permutation(n) + rng.random(n)) / n
    return u


@dataclass
class World:
    """Latent truth for one synthetic world (serialisable, no twin parameters)."""
    seed: int
    model: str
    material_comp: dict[str, dict[str, float]]
    enzyme_params: dict[str, dict[str, float]]
    lot_activity: dict[str, float]
    sub_factor: dict[str, float]
    Ki: float
    Ki_n: float
    collagen_coef: float
    lipid_coef: float
    assay_sd: float
    occasion_sd: float
    orac_sd: float
    gross_rate: float
    drift_DH: float
    drift_ORAC: float
    orac_base: float
    orac_amp: float
    orac_dh_opt: float
    orac_width: float
    orac_enzyme_offset: dict[str, float]
    orac_material_offset: dict[str, float]
    peptide_material_offset: dict[str, float]
    budget: int = 30


def _sample_world(seed: int) -> World:
    rng = np.random.default_rng(seed)
    main = _load_main()

    material_comp: dict[str, dict[str, float]] = {}
    for mat in MATERIALS:
        sub = main[main["RawMaterial"] == mat]
        if sub.empty:
            sub = main
        row = sub.iloc[int(rng.integers(0, len(sub)))]
        comp = {}
        for col in COMPOSITION_COLS:
            value = float(row[col])
            # bootstrap the real composition, then a small batch-to-batch jitter
            value += rng.normal(0.0, max(0.02 * abs(value), 0.02))
            comp[col] = value
        # plausible physical ranges (the real rows already sit inside these)
        comp["Moisture_pct"] = float(np.clip(comp["Moisture_pct"], 40.0, 85.0))
        comp["CrudeProtein_pct"] = float(np.clip(comp["CrudeProtein_pct"], 8.0, 22.0))
        comp["CrudeLipid_pct"] = float(np.clip(comp["CrudeLipid_pct"], 0.1, 30.0))
        comp["Ash_pct"] = float(np.clip(comp["Ash_pct"], 1.0, 25.0))
        comp["Hydroxyproline_pct"] = float(np.clip(comp["Hydroxyproline_pct"], 0.2, 1.5))
        comp["Collagen_pct"] = float(np.clip(comp["Collagen_pct"], 2.0, 9.0))
        material_comp[mat] = comp

    enzyme_params: dict[str, dict[str, float]] = {}
    for enzyme, base in BASE_SPECS.items():
        p = dict(base)
        p["pH_opt"] = float(np.clip(p["pH_opt"] + rng.normal(0.0, 0.15), 1.8, 9.2))
        p["sigma_lo"] = float(p["sigma_lo"] * rng.uniform(0.90, 1.10))
        p["sigma_hi"] = float(p["sigma_hi"] * rng.uniform(0.90, 1.10))
        p["Ea_cat_kJ"] = float(p["Ea_cat_kJ"] * rng.uniform(0.85, 1.15))
        p["Ea_deact_kJ"] = float(p["Ea_deact_kJ"] * rng.uniform(0.90, 1.10))
        p["kd_ref"] = float(p["kd_ref"] * rng.lognormal(0.0, 0.15))
        p["k1"] = float(p["k1"] * rng.lognormal(0.0, 0.15))
        p["k2"] = float(p["k2"] * rng.lognormal(0.0, 0.20))
        p["f_fast"] = float(np.clip(p["f_fast"] + rng.normal(0.0, 0.03), 0.05, 0.60))
        p["Pmax"] = float(np.clip(p["Pmax"] + rng.normal(0.0, 0.02), 0.30, 0.65))
        p["alpha"] = float(np.clip(p["alpha"] + rng.normal(0.0, 0.05), 0.40, 0.90))
        enzyme_params[enzyme] = p

    lot_activity = {}
    for enzyme in ENZYMES:
        sigma = rng.uniform(0.08, 0.16)
        lot_activity[enzyme] = float(rng.lognormal(-0.5 * sigma ** 2, sigma))
    sub_factor = {}
    for mat in MATERIALS:
        sigma = rng.uniform(0.08, 0.16)
        sub_factor[mat] = float(rng.lognormal(-0.5 * sigma ** 2, sigma))

    return World(
        seed=int(seed),
        model="two_pool_exposure_v1",
        material_comp=material_comp,
        enzyme_params=enzyme_params,
        lot_activity=lot_activity,
        sub_factor=sub_factor,
        Ki=float(rng.uniform(50.0, 60.0)),
        Ki_n=float(rng.uniform(1.6, 2.0)),
        collagen_coef=float(rng.uniform(0.01, 0.04)),
        lipid_coef=float(rng.uniform(0.005, 0.025)),
        assay_sd=float(rng.uniform(0.8, 1.4)),
        occasion_sd=float(rng.uniform(1.5, 3.5)),
        orac_sd=float(rng.uniform(20.0, 40.0)),
        gross_rate=0.05,
        drift_DH=float(rng.normal(0.0, 1.5)),
        drift_ORAC=float(rng.normal(0.0, 25.0)),
        orac_base=float(rng.uniform(260.0, 320.0)),
        orac_amp=float(rng.uniform(160.0, 260.0)),
        orac_dh_opt=float(rng.uniform(14.0, 24.0)),
        orac_width=float(rng.uniform(8.0, 14.0)),
        orac_enzyme_offset={e: float(rng.normal(0.0, 15.0)) for e in ENZYMES},
        orac_material_offset={m: float(rng.normal(0.0, 15.0)) for m in MATERIALS},
        peptide_material_offset={m: float(rng.normal(0.0, 1.5)) for m in MATERIALS},
        budget=30,
    )


class SyntheticLab:
    """A single synthetic world, with deterministic design/measurement helpers."""

    def __init__(self, seed: int, world: World | None = None):
        self.seed = int(seed)
        self.world = world if world is not None else _sample_world(self.seed)
        self._design_rng = np.random.default_rng(self.seed + 101)
        self._measure_rng = np.random.default_rng(self.seed + 202)

    # ------------------------------------------------------------------ IO
    @classmethod
    def from_json(cls, path: str | Path) -> "SyntheticLab":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(seed=int(data["seed"]), world=World(**data["world"]))

    def to_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seed": self.seed, "model": self.world.model,
                   "world": _jsonable(asdict(self.world))}
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # -------------------------------------------------------------- truth
    def _arrays(self, df: pd.DataFrame) -> dict[str, np.ndarray]:
        enz = df["Enzyme"].astype(str).to_numpy()
        mat = df["RawMaterial"].astype(str).to_numpy()
        p = self.world.enzyme_params
        m = self.world.material_comp
        return {
            "enzyme": enz,
            "material": mat,
            "pH": df["pH"].to_numpy(float),
            "T": df["Temp_C"].to_numpy(float),
            "duration": df["Duration_min"].to_numpy(float),
            "S0": df["SubstrateConc_gL"].to_numpy(float),
            "es": df["EnzymeToSubstrateRatio"].to_numpy(float),
            "protein": df["CrudeProtein_pct"].to_numpy(float),
            "lipid": df["CrudeLipid_pct"].to_numpy(float),
            "collagen": df["Collagen_pct"].to_numpy(float),
            "pH_opt": np.array([p[e]["pH_opt"] for e in enz]),
            "sigma_lo": np.array([p[e]["sigma_lo"] for e in enz]),
            "sigma_hi": np.array([p[e]["sigma_hi"] for e in enz]),
            "Ea_cat": np.array([p[e]["Ea_cat_kJ"] for e in enz]),
            "Ea_deact": np.array([p[e]["Ea_deact_kJ"] for e in enz]),
            "kd_ref": np.array([p[e]["kd_ref"] for e in enz]),
            "k1": np.array([p[e]["k1"] for e in enz]),
            "k2": np.array([p[e]["k2"] for e in enz]),
            "f_fast": np.array([p[e]["f_fast"] for e in enz]),
            "Pmax": np.array([p[e]["Pmax"] for e in enz]),
            "alpha": np.array([p[e]["alpha"] for e in enz]),
            "lot": np.array([self.world.lot_activity[e] for e in enz]),
            "sub": np.array([self.world.sub_factor[x] for x in mat]),
            "collagen_ref": np.array([m[x]["Collagen_pct"] for x in mat]),
        }

    def true_dh(self, df: pd.DataFrame) -> np.ndarray:
        """Noiseless degree of hydrolysis (%) for each row."""
        a = self._arrays(df)
        T_k = a["T"] + 273.15
        inv = 1.0 / T_k - 1.0 / T_REF_K
        f_T = np.exp(-a["Ea_cat"] * 1000.0 / R_GAS * inv)
        kd = a["kd_ref"] * np.exp(-a["Ea_deact"] * 1000.0 / R_GAS * inv)
        kd = np.clip(kd, 1e-9, 10.0)
        exposure = (1.0 - np.exp(-kd * a["duration"])) / kd

        sigma = np.where(a["pH"] < a["pH_opt"], a["sigma_lo"], a["sigma_hi"])
        f_pH = np.exp(-0.5 * ((a["pH"] - a["pH_opt"]) / sigma) ** 2)
        f_S = 1.0 / (1.0 + (a["S0"] / self.world.Ki) ** self.world.Ki_n)

        s0_gL = a["S0"] * a["protein"] / 100.0
        e0 = a["es"] * s0_gL
        e0_factor = np.clip((e0 / E0_REF) ** a["alpha"], 0.01, 20.0)

        f_coll = np.exp(-self.world.collagen_coef *
                        np.maximum(0.0, a["collagen"] - 4.0))
        f_lipid = np.exp(-self.world.lipid_coef *
                         np.maximum(0.0, a["lipid"] - 10.0))

        A0 = (a["lot"] * a["sub"] * e0_factor * f_T * f_pH * f_S
              * f_coll * f_lipid)
        fast = 1.0 - np.exp(-a["k1"] * A0 * exposure)
        slow = 1.0 - np.exp(-a["k2"] * A0 * exposure)
        dh = 100.0 * a["Pmax"] * (a["f_fast"] * fast + (1.0 - a["f_fast"]) * slow)
        return np.clip(dh, 0.0, 100.0)

    def true_orac_from_dh(self, dh: np.ndarray, enzyme: np.ndarray,
                          material: np.ndarray) -> np.ndarray:
        dh = np.asarray(dh, dtype=float)
        enzyme = np.asarray(enzyme, dtype=object)
        material = np.asarray(material, dtype=object)
        pep = 18.0 + 0.22 * dh + np.array(
            [self.world.peptide_material_offset[m] for m in material])
        pep = np.clip(pep, 5.0, 35.0)
        orac = (self.world.orac_base
                + self.world.orac_amp *
                np.exp(-0.5 * ((dh - self.world.orac_dh_opt) / self.world.orac_width) ** 2)
                + np.array([self.world.orac_enzyme_offset[e] for e in enzyme])
                + np.array([self.world.orac_material_offset[m] for m in material])
                + 0.3 * (pep - 23.0))
        return np.clip(orac, 200.0, 700.0)

    def true_orac(self, df: pd.DataFrame, dh: np.ndarray | None = None
                  ) -> tuple[np.ndarray, np.ndarray]:
        if dh is None:
            dh = self.true_dh(df)
        enz = df["Enzyme"].astype(str).to_numpy()
        mat = df["RawMaterial"].astype(str).to_numpy()
        orac = self.true_orac_from_dh(dh, enz, mat)
        pep = np.clip(18.0 + 0.22 * np.asarray(dh)
                      + np.array([self.world.peptide_material_offset[m] for m in mat]),
                      5.0, 35.0)
        return orac, pep

    # ----------------------------------------------------------- measure
    def measure(self, df: pd.DataFrame, rng: np.random.Generator | None = None,
                trial_start: int = 1, budget: int | None = None,
                add_noise: bool = True) -> pd.DataFrame:
        """Return measured rows plus latent truth columns.

        ``trial_start`` is the 1-based campaign position of the first row; it
        drives the slow drift.  The caller supplies an independent ``rng`` per
        policy so that two policies measuring different conditions do not share
        assay noise.
        """
        rng = self._measure_rng if rng is None else rng
        budget = self.world.budget if budget is None else int(budget)
        n = len(df)
        if n == 0:
            return df.copy()
        trial = np.arange(trial_start, trial_start + n, dtype=int)
        dh_true = self.true_dh(df)
        orac_true, pep_true = self.true_orac(df, dh_true)

        if add_noise:
            occasion = rng.normal(0.0, self.world.occasion_sd, n)
            drift_dh = self.world.drift_DH * (trial / max(budget, 1))
            dh_meas = dh_true + occasion + drift_dh + rng.normal(0.0, self.world.assay_sd, n)
            gross_mask = rng.random(n) < self.world.gross_rate
            gross_dh = np.where(gross_mask,
                                rng.choice([-1.0, 1.0], n) * rng.uniform(8.0, 25.0, n),
                                0.0)
            dh_meas = np.clip(dh_meas + gross_dh, 0.0, 100.0)

            drift_orac = self.world.drift_ORAC * (trial / max(budget, 1))
            orac_meas = orac_true + rng.normal(0.0, self.world.orac_sd, n) + drift_orac
            gross_orac = np.where(gross_mask,
                                  rng.choice([-1.0, 1.0], n) * rng.uniform(60.0, 180.0, n),
                                  0.0)
            orac_meas = np.clip(orac_meas + gross_orac, 100.0, 800.0)
            pep_meas = np.clip(pep_true + rng.normal(0.0, 1.2, n), 5.0, 35.0)
            recovery = np.clip(50.0 + 0.3 * dh_true + rng.normal(0.0, 20.0, n), 5.0, 95.0)
        else:
            occasion = np.zeros(n)
            drift_dh = np.zeros(n)
            gross_mask = np.zeros(n, dtype=bool)
            gross_dh = np.zeros(n)
            drift_orac = np.zeros(n)
            gross_orac = np.zeros(n)
            dh_meas, orac_meas, pep_meas = dh_true, orac_true, pep_true
            recovery = np.clip(50.0 + 0.3 * dh_true, 5.0, 95.0)

        out = df.copy()
        if "BatchID" not in out.columns:
            out.insert(0, "BatchID", [f"SYN_{i:04d}" for i in range(1, n + 1)])
        out["FinalDH_pct"] = dh_meas
        out["ORAC"] = orac_meas
        out["PeptideYield_pct"] = pep_meas
        out["ProteinRecovery_pct"] = recovery
        out["S0_gL"] = out["SubstrateConc_gL"].to_numpy(float) * \
            out["CrudeProtein_pct"].to_numpy(float) / 100.0
        out["E0_gL"] = out["EnzymeToSubstrateRatio"].to_numpy(float) * out["S0_gL"]
        out["trial"] = trial
        out["true_DH_pct"] = dh_true
        out["true_ORAC"] = orac_true
        out["true_PeptideYield_pct"] = pep_true
        out["occasion_DH_pts"] = occasion
        out["drift_DH_pts"] = drift_dh
        out["drift_ORAC_units"] = drift_orac
        out["gross_error_DH_pts"] = gross_dh
        out["gross_error_ORAC_units"] = gross_orac
        out["gross_error"] = gross_mask
        return out

    # ------------------------------------------------------------- design
    def seed_design(self) -> pd.DataFrame:
        """15-run seed design with the same arms as the real campaign."""
        rng = self._design_rng
        rows: list[dict[str, Any]] = []
        idx = 1

        def add(enzyme: str, pH: float, temp: float, duration: float,
                s0: float, es: float, material: str, arm: str, note: str) -> None:
            nonlocal idx
            rows.append({
                "BatchID": f"SYN_{idx:03d}", "Enzyme": enzyme,
                "pH": round(float(pH), 2), "Temp_C": round(float(temp), 1),
                "Duration_min": round(float(duration), 1),
                "SubstrateConc_gL": float(s0),
                "EnzymeToSubstrateRatio": float(es),
                "RawMaterial": material,
                **{c: self.world.material_comp[material][c] for c in COMPOSITION_COLS},
                "arm": arm, "note": note,
            })
            idx += 1

        gap_specs = [("Pepsin", 1), ("Flavourzyme", 1), ("Alcalase+Kojizyme", 1),
                     ("Alcalase+Neutrase", 2), ("Alcalase+Flavourzyme", 2)]
        for enzyme, n in gap_specs:
            _, lo_pH, hi_pH, _, lo_T, hi_T = ENZYME_WINDOWS[enzyme]
            u = _lhc(n, 2, rng)
            for k in range(n):
                add(enzyme, lo_pH + u[k, 0] * (hi_pH - lo_pH),
                    lo_T + u[k, 1] * (hi_T - lo_T),
                    rng.integers(60, 301), 50.0, 0.02,
                    str(rng.choice(MATERIALS)), "gap_fill",
                    f"raise {enzyme} rows to n>=3")

        u = _lhc(5, 4, rng)
        mats = list(MATERIALS)
        rng.shuffle(mats)
        for k in range(5):
            add("Alcalase", 7.0 + 2.0 * u[k, 0], 50.0 + 10.0 * u[k, 1],
                60.0 + 240.0 * u[k, 2], 30.0 + 40.0 * u[k, 3], 0.02,
                mats[k], "process_lhc", "process space; material gap")

        for es in (0.01, 0.04, 0.06):
            add("Alcalase", rng.uniform(7.5, 8.5), rng.uniform(53.0, 57.0),
                120.0, 50.0, es, "salmon_frames", "dose_sweep",
                f"weighed enzyme charge E/S={es}")

        df = pd.DataFrame(rows)
        if len(df) != 15:
            raise RuntimeError(f"seed design has {len(df)} rows, expected 15")
        return df

    # ----------------------------------------------------------- candidates
    def candidate_space(self, n: int, rng: np.random.Generator | None = None,
                        balanced_enzymes: bool = True) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed + 303) if rng is None else rng
        if balanced_enzymes:
            enzyme = np.tile(ENZYMES, int(np.ceil(n / len(ENZYMES))))[:n]
            rng.shuffle(enzyme)
        else:
            enzyme = rng.choice(ENZYMES, n)
        material = rng.choice(MATERIALS, n)
        pH = rng.uniform(*PROCESS_BOUNDS["pH"], n)
        temp = rng.uniform(*PROCESS_BOUNDS["Temp_C"], n)
        duration = rng.uniform(*PROCESS_BOUNDS["Duration_min"], n)
        s0 = rng.uniform(*PROCESS_BOUNDS["SubstrateConc_gL"], n)
        es = rng.choice(ES_VALUES, n, p=[0.15, 0.55, 0.15, 0.15])
        df = pd.DataFrame({
            "BatchID": [f"CAND_{i:06d}" for i in range(1, n + 1)],
            "Enzyme": enzyme, "pH": pH, "Temp_C": temp,
            "Duration_min": duration, "SubstrateConc_gL": s0,
            "EnzymeToSubstrateRatio": es, "RawMaterial": material,
        })
        # Match the precision a bench protocol can actually set.  The oracle
        # must be scored on the same grid as the lab, otherwise its "best" is
        # an unrounded condition no policy can request (and regret can go
        # slightly negative).
        df["pH"] = df["pH"].round(2)
        df["Temp_C"] = df["Temp_C"].round(1)
        df["Duration_min"] = df["Duration_min"].round(1)
        df["SubstrateConc_gL"] = df["SubstrateConc_gL"].round(2)
        for col in COMPOSITION_COLS:
            df[col] = df["RawMaterial"].map(
                {m: self.world.material_comp[m][col] for m in MATERIALS})
        return df

    def oracle_table(self, n: int = 50000, refine: bool = True) -> dict[str, Any]:
        """Top candidates by true DH and true ORAC, plus the oracle maxima.

        This is the benchmark's upper bound.  It uses the latent truth and is
        never available to a policy except the explicit oracle baseline.
        """
        rng = np.random.default_rng(self.seed + 404)
        cand = self.candidate_space(n, rng=rng)
        dh = self.true_dh(cand)
        orac, _ = self.true_orac(cand, dh)
        cand = cand.assign(true_DH_pct=dh, true_ORAC=orac)

        if refine:
            top = cand.nlargest(min(50, len(cand)), "true_DH_pct")
            jitters = []
            for _ in range(40):
                j = top.copy()
                j["pH"] = np.clip(j["pH"] + rng.normal(0.0, 0.2, len(j)),
                                  *PROCESS_BOUNDS["pH"])
                j["Temp_C"] = np.clip(j["Temp_C"] + rng.normal(0.0, 1.0, len(j)),
                                      *PROCESS_BOUNDS["Temp_C"])
                j["Duration_min"] = np.clip(j["Duration_min"] * rng.uniform(0.9, 1.1, len(j)),
                                            *PROCESS_BOUNDS["Duration_min"])
                j["SubstrateConc_gL"] = np.clip(
                    j["SubstrateConc_gL"] * rng.uniform(0.95, 1.05, len(j)),
                    *PROCESS_BOUNDS["SubstrateConc_gL"])
                j["EnzymeToSubstrateRatio"] = rng.choice(ES_VALUES, len(j))
                j["BatchID"] = [f"REF_{i:06d}" for i in range(1, len(j) + 1)]
                jitters.append(j)
            ref = pd.concat(jitters, ignore_index=True)
            ref["pH"] = ref["pH"].round(2)
            ref["Temp_C"] = ref["Temp_C"].round(1)
            ref["Duration_min"] = ref["Duration_min"].round(1)
            ref["SubstrateConc_gL"] = ref["SubstrateConc_gL"].round(2)
            ref_dh = self.true_dh(ref)
            ref_orac, _ = self.true_orac(ref, ref_dh)
            ref = ref.assign(true_DH_pct=ref_dh, true_ORAC=ref_orac)
            cand = pd.concat([cand, ref], ignore_index=True)

        by_dh = cand.nlargest(self.world.budget, "true_DH_pct").reset_index(drop=True)
        by_orac = cand.nlargest(self.world.budget, "true_ORAC").reset_index(drop=True)
        return {
            "best_dh": float(cand["true_DH_pct"].max()),
            "best_orac": float(cand["true_ORAC"].max()),
            "top_dh": by_dh,
            "top_orac": by_orac,
            "n_evaluated": int(len(cand)),
        }

    # ---------------------------------------------------------- diagnostics
    def validate_world(self) -> dict[str, Any]:
        """Check the qualitative features the benchmark relies on."""
        base = {
            "Enzyme": "Alcalase", "RawMaterial": "salmon_frames",
            "pH": 8.0, "Temp_C": 50.0, "Duration_min": 300.0,
            "SubstrateConc_gL": 50.0, "EnzymeToSubstrateRatio": 0.02,
            **{c: self.world.material_comp["salmon_frames"][c] for c in COMPOSITION_COLS},
        }
        df = pd.DataFrame([base])
        s0_vals = np.array([30.0, 40.0, 50.0, 60.0, 70.0])
        s0_dh = []
        for s0 in s0_vals:
            row = df.copy()
            row["SubstrateConc_gL"] = s0
            s0_dh.append(float(self.true_dh(row)[0]))
        s0_dh = np.array(s0_dh)

        t_vals = np.array([40.0, 45.0, 50.0, 55.0, 60.0])
        t_opt = {}
        for duration in (60.0, 300.0):
            vals = []
            for temp in t_vals:
                row = df.copy()
                row["Temp_C"] = temp
                row["Duration_min"] = duration
                vals.append(float(self.true_dh(row)[0]))
            t_opt[str(int(duration))] = int(np.argmax(vals))

        lot = self.world.lot_activity["Alcalase"]
        low = copy.deepcopy(self.world)
        high = copy.deepcopy(self.world)
        low.lot_activity["Alcalase"] = lot * 0.85
        high.lot_activity["Alcalase"] = lot * 1.15
        low_lab = SyntheticLab(self.seed, world=low)
        high_lab = SyntheticLab(self.seed, world=high)
        lot_low = float(low_lab.true_dh(df)[0])
        lot_high = float(high_lab.true_dh(df)[0])

        dh_grid = np.linspace(5.0, 45.0, 9)
        orac_grid = self.true_orac_from_dh(
            dh_grid, np.array(["Alcalase"] * len(dh_grid)),
            np.array(["salmon_frames"] * len(dh_grid)))
        orac_peak = int(np.argmax(orac_grid))

        big = self.candidate_space(300, rng=np.random.default_rng(self.seed + 505))
        measured = self.measure(big, rng=np.random.default_rng(self.seed + 606),
                                trial_start=1, budget=30)
        gross_frac = float(measured["gross_error"].mean())

        return {
            "substrate_inhibition": {
                "s0": s0_vals.tolist(), "dh": [round(float(v), 2) for v in s0_dh],
                "argmax_s0": float(s0_vals[int(np.argmax(s0_dh))]),
                "interior": bool(0 < int(np.argmax(s0_dh)) < len(s0_vals) - 1),
                "span_dh": round(float(s0_dh.max() - s0_dh.min()), 2),
            },
            "temperature_shift": {
                "T": t_vals.tolist(),
                "argmax_T_60min": float(t_vals[t_opt["60"]]),
                "argmax_T_300min": float(t_vals[t_opt["300"]]),
                "shifts_down": bool(t_opt["60"] >= t_opt["300"]),
            },
            "lot_effect": {
                "dh_low_lot": round(lot_low, 2), "dh_high_lot": round(lot_high, 2),
                "relative_gap": round((lot_high - lot_low) / max(lot_low, 1e-6), 3),
                "detectable": bool(abs(lot_high - lot_low) > 0.05 * max(lot_low, 1.0)),
            },
            "orac_non_monotonic": {
                "dh": dh_grid.tolist(), "orac": [round(float(v), 1) for v in orac_grid],
                "argmax_dh": float(dh_grid[orac_peak]),
                "interior": bool(0 < orac_peak < len(dh_grid) - 1),
                "span": round(float(orac_grid.max() - orac_grid.min()), 1),
            },
            "gross_error_fraction": round(gross_frac, 3),
            "gross_error_nominal": self.world.gross_rate,
        }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate one synthetic world (never golden data).")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(SYNTH_DIR / "world_000"))
    ap.add_argument("--n-oracle", type=int, default=20000)
    args = ap.parse_args()

    out = Path(args.out)
    lab = SyntheticLab(args.seed)
    design = lab.seed_design()
    measured = lab.measure(design, trial_start=1, budget=lab.world.budget)
    oracle = lab.oracle_table(n=args.n_oracle, refine=True)
    diag = lab.validate_world()

    out.mkdir(parents=True, exist_ok=True)
    lab.to_json(out / "world.json")
    design.to_csv(out / "design.csv", index=False)
    measured.to_csv(out / "measured.csv", index=False)
    (out / "oracle.json").write_text(json.dumps(_jsonable({
        "best_dh": oracle["best_dh"], "best_orac": oracle["best_orac"],
        "n_evaluated": oracle["n_evaluated"],
        "top_dh": oracle["top_dh"].head(10).to_dict(orient="records"),
    }), indent=2), encoding="utf-8")
    (out / "diagnostics.json").write_text(json.dumps(_jsonable(diag), indent=2),
                                          encoding="utf-8")
    (out / "README.md").write_text(
        "# Synthetic world (not real data)\n\n"
        f"Generated by `src/synthetic_lab.py --seed {args.seed}`.\n\n"
        "Every row here is synthetic. Do not merge it into `data/processed/` or "
        "use it as evidence about the real process. The generator is a two-pool "
        "hydrolysis world with lot effects, substrate inhibition, assay noise, "
        "gross errors and a non-monotonic ORAC response; it is deliberately "
        "richer than the twin. See the internal parameter-provenance notes for parameter anchors.\n",
        encoding="utf-8")

    print(f"[synthetic_lab] seed={args.seed} -> {out}")
    print(f"  seed design true DH: {measured['true_DH_pct'].min():.1f}-"
          f"{measured['true_DH_pct'].max():.1f}% (mean {measured['true_DH_pct'].mean():.1f})")
    best = measured.loc[measured["true_DH_pct"].idxmax()]
    print(f"  best seed: {best['BatchID']} {best['Enzyme']} pH={best['pH']} "
          f"T={best['Temp_C']} t={best['Duration_min']} -> {best['true_DH_pct']:.1f}%")
    print(f"  oracle best DH={oracle['best_dh']:.1f}% ORAC={oracle['best_orac']:.0f} "
          f"(n={oracle['n_evaluated']})")
    print(f"  diagnostics: substrate interior={diag['substrate_inhibition']['interior']}, "
          f"T shift={diag['temperature_shift']['shifts_down']}, "
          f"ORAC interior={diag['orac_non_monotonic']['interior']}, "
          f"gross={diag['gross_error_fraction']:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
