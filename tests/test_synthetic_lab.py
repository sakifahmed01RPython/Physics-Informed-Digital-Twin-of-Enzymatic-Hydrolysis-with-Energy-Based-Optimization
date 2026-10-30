"""Regression tests for the independent synthetic lab (step 3).

Run from the repo root:
    python -m unittest discover -s tests -t . -v
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.ode_model import dh_curve
from src.synthetic_lab import (COMPOSITION_COLS, MATERIALS, PROCESS_BOUNDS,
                               SyntheticLab, _jsonable)

ROOT = Path(__file__).resolve().parents[1]
ODE_PARAMS = ROOT / "models" / "ode_params_alcalase.json"


def base_row(lab, enzyme="Alcalase", material="salmon_frames"):
    return {
        "Enzyme": enzyme, "RawMaterial": material,
        "pH": 8.0, "Temp_C": 50.0, "Duration_min": 180.0,
        "SubstrateConc_gL": 50.0, "EnzymeToSubstrateRatio": 0.02,
        **lab.world.material_comp[material],
    }


class TestDeterminism(unittest.TestCase):
    def test_seed_design_is_deterministic(self):
        a = SyntheticLab(0).seed_design()
        b = SyntheticLab(0).seed_design()
        pd.testing.assert_frame_equal(a, b)

    def test_measurement_is_deterministic_with_same_rng(self):
        lab = SyntheticLab(0)
        design = lab.seed_design()
        a = lab.measure(design, rng=np.random.default_rng(123),
                        trial_start=1, budget=30)
        b = lab.measure(design, rng=np.random.default_rng(123),
                        trial_start=1, budget=30)
        pd.testing.assert_frame_equal(a, b)

    def test_world_json_roundtrip_preserves_truth(self):
        lab = SyntheticLab(0)
        design = lab.seed_design()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "world.json"
            lab.to_json(path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("NaN", text)
            self.assertNotIn("Infinity", text)
            loaded = SyntheticLab.from_json(path)
        np.testing.assert_allclose(lab.true_dh(design), loaded.true_dh(design))


class TestSeedDesign(unittest.TestCase):
    def test_schema_and_arms(self):
        design = SyntheticLab(0).seed_design()
        self.assertEqual(len(design), 15)
        self.assertEqual(design["BatchID"].nunique(), 15)
        # The real campaign design has six enzyme labels: plain Neutrase is
        # not one of its arms.  The generator mirrors that, even though the
        # candidate space contains all seven labels.
        self.assertEqual(set(design["Enzyme"]),
                         {"Alcalase", "Pepsin", "Flavourzyme",
                          "Alcalase+Kojizyme", "Alcalase+Neutrase",
                          "Alcalase+Flavourzyme"})
        self.assertEqual(design["arm"].value_counts().to_dict(),
                         {"gap_fill": 7, "process_lhc": 5, "dose_sweep": 3})
        self.assertEqual(set(design.loc[design["arm"] == "dose_sweep",
                                        "EnzymeToSubstrateRatio"]),
                         {0.01, 0.04, 0.06})

    def test_process_values_are_inside_the_acquisition_box(self):
        design = SyntheticLab(0).seed_design()
        for col, (lo, hi) in PROCESS_BOUNDS.items():
            self.assertTrue((design[col] >= lo).all(), col)
            self.assertTrue((design[col] <= hi).all(), col)

    def test_materials_and_composition_are_consistent(self):
        lab = SyntheticLab(0)
        design = lab.seed_design()
        self.assertTrue(set(design["RawMaterial"]).issubset(set(MATERIALS)))
        for _, row in design.iterrows():
            for col in COMPOSITION_COLS:
                self.assertAlmostEqual(float(row[col]),
                                       float(lab.world.material_comp[row["RawMaterial"]][col]))


class TestMeasurementSchema(unittest.TestCase):
    def test_measured_rows_have_truth_and_noise_columns(self):
        lab = SyntheticLab(0)
        measured = lab.measure(lab.seed_design(), rng=np.random.default_rng(1),
                               trial_start=1, budget=30)
        self.assertEqual(len(measured), 15)
        for col in ["FinalDH_pct", "ORAC", "PeptideYield_pct",
                    "ProteinRecovery_pct", "true_DH_pct", "true_ORAC",
                    "gross_error", "occasion_DH_pts", "drift_DH_pts"]:
            self.assertIn(col, measured.columns)
        self.assertTrue(np.isfinite(measured["FinalDH_pct"]).all())
        self.assertTrue(np.isfinite(measured["true_DH_pct"]).all())
        self.assertTrue(measured["true_DH_pct"].between(0, 100).all())
        self.assertTrue(measured["true_ORAC"].between(200, 700).all())
        self.assertTrue(measured["FinalDH_pct"].between(0, 100).all())
        self.assertTrue(measured["ORAC"].between(100, 800).all())

    def test_gross_errors_exist_and_are_large(self):
        lab = SyntheticLab(0)
        big = lab.candidate_space(500, rng=np.random.default_rng(7))
        measured = lab.measure(big, rng=np.random.default_rng(11),
                               trial_start=1, budget=30)
        frac = float(measured["gross_error"].mean())
        self.assertGreater(frac, 0.01)
        self.assertLess(frac, 0.12)
        gross = measured[measured["gross_error"]]
        self.assertGreater(len(gross), 0)
        # A gross error is at least 8 DH away before noise; after noise it
        # should still be visibly separated from the latent truth.
        residual = (gross["FinalDH_pct"] - gross["true_DH_pct"]
                    - gross["occasion_DH_pts"] - gross["drift_DH_pts"])
        self.assertGreater(float(residual.abs().median()), 3.0)


class TestQualitativeWorld(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.diagnostics = {seed: SyntheticLab(seed).validate_world()
                           for seed in range(8)}

    def test_substrate_inhibition_is_present_in_most_worlds(self):
        interior = [d["substrate_inhibition"]["interior"]
                    for d in self.diagnostics.values()]
        self.assertGreaterEqual(sum(interior), 6)
        for d in self.diagnostics.values():
            self.assertGreater(d["substrate_inhibition"]["span_dh"], 0.5)

    def test_temperature_optimum_shifts_down_with_duration(self):
        for d in self.diagnostics.values():
            self.assertTrue(d["temperature_shift"]["shifts_down"])
            self.assertGreater(d["temperature_shift"]["argmax_T_60min"],
                               d["temperature_shift"]["argmax_T_300min"])

    def test_lot_effect_is_detectable(self):
        for d in self.diagnostics.values():
            self.assertTrue(d["lot_effect"]["detectable"])
            self.assertGreater(d["lot_effect"]["relative_gap"], 0.05)

    def test_orac_is_non_monotonic_in_dh(self):
        for d in self.diagnostics.values():
            self.assertTrue(d["orac_non_monotonic"]["interior"])
            self.assertGreater(d["orac_non_monotonic"]["span"], 50.0)

    def test_gross_error_fraction_is_near_nominal(self):
        for d in self.diagnostics.values():
            self.assertGreater(d["gross_error_fraction"], 0.0)
            self.assertLess(d["gross_error_fraction"], 0.15)


class TestModelIndependence(unittest.TestCase):
    """The generator must not be the twin's one-pool ODE in disguise."""

    def test_es_and_lot_effects_exist(self):
        lab = SyntheticLab(0)
        row = pd.DataFrame([base_row(lab)])
        low = row.copy()
        low["EnzymeToSubstrateRatio"] = 0.01
        high = row.copy()
        high["EnzymeToSubstrateRatio"] = 0.06
        dh_low = float(lab.true_dh(low)[0])
        dh_high = float(lab.true_dh(high)[0])
        self.assertGreater(abs(dh_high - dh_low), 3.0)

        lot_world = copy.deepcopy(lab.world)
        lot_world.lot_activity["Alcalase"] *= 1.20
        lot_lab = SyntheticLab(0, world=lot_world)
        self.assertGreater(abs(float(lot_lab.true_dh(row)[0])
                               - float(lab.true_dh(row)[0])), 0.5)

    def test_composition_effects_exist(self):
        lab = SyntheticLab(0)
        base = base_row(lab)
        low = pd.DataFrame([{**base, "Collagen_pct": 3.43,
                             "CrudeLipid_pct": 0.2}])
        high = pd.DataFrame([{**base, "Collagen_pct": 6.78,
                              "CrudeLipid_pct": 22.24}])
        self.assertGreater(abs(float(lab.true_dh(low)[0])
                               - float(lab.true_dh(high)[0])), 1.0)

    def test_truth_is_not_the_fitted_twin_ode(self):
        if not ODE_PARAMS.exists():
            self.skipTest("fitted ODE parameters not present")
        lab = SyntheticLab(0)
        row = pd.DataFrame([base_row(lab)])
        params = json.loads(ODE_PARAMS.read_text(encoding="utf-8"))
        protein = float(row["CrudeProtein_pct"].iloc[0])
        s0 = 50.0 * protein / 100.0
        e0 = 0.02 * s0
        ode = float(dh_curve(s0, e0, 50.0, 8.0,
                             np.array([0.0, 180.0]), params=params)[-1])
        syn = float(lab.true_dh(row)[0])
        self.assertGreater(abs(syn - ode), 1.0,
                           "synthetic truth is too close to the twin ODE")


class TestCandidateAndOracle(unittest.TestCase):
    def test_candidate_space_is_consistent_with_material(self):
        lab = SyntheticLab(0)
        cand = lab.candidate_space(200, rng=np.random.default_rng(3))
        self.assertEqual(len(cand), 200)
        for _, row in cand.iterrows():
            for col in COMPOSITION_COLS:
                self.assertAlmostEqual(float(row[col]),
                                       float(lab.world.material_comp[row["RawMaterial"]][col]))

    def test_oracle_is_sorted_and_scored_at_lab_precision(self):
        lab = SyntheticLab(0)
        oracle = lab.oracle_table(n=400, refine=True)
        top = oracle["top_dh"]
        self.assertGreater(len(top), 0)
        self.assertTrue(top["true_DH_pct"].is_monotonic_decreasing)
        self.assertAlmostEqual(float(top["true_DH_pct"].iloc[0]),
                               float(oracle["best_dh"]), places=9)
        self.assertAlmostEqual(float(oracle["top_orac"]["true_ORAC"].iloc[0]),
                               float(oracle["best_orac"]), places=9)
        for col, decimals in [("pH", 2), ("Temp_C", 1),
                              ("Duration_min", 1), ("SubstrateConc_gL", 2)]:
            self.assertTrue(np.allclose(top[col], top[col].round(decimals)),
                            f"{col} is not at lab precision")

    def test_jsonable_turns_non_finite_into_null(self):
        payload = {"a": float("nan"), "b": np.float64("inf"),
                   "c": [1.0, float("-inf")], "d": np.int64(3)}
        text = json.dumps(_jsonable(payload), allow_nan=False)
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)
        self.assertEqual(json.loads(text),
                         {"a": None, "b": None, "c": [1.0, None], "d": 3})


if __name__ == "__main__":
    unittest.main()
