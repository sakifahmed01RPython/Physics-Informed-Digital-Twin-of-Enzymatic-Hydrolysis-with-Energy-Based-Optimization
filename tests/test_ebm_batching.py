"""Regression tests for the batched EBM acquisition (step 5 speed fix).

Run from the repo root:
    python -m unittest tests.test_ebm_batching -v
"""
import unittest

import numpy as np
import pandas as pd

from src.ebm_optimizer import COMPOSITION_COLS, ENZYMES, EBMOptimizer


def _frame(n: int = 28) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "BatchID": [f"T_{i:03d}" for i in range(1, n + 1)],
        "Enzyme": [ENZYMES[i % len(ENZYMES)] for i in range(n)],
        "RawMaterial": ["salmon_frames"] * n,
        "pH": rng.uniform(6.0, 9.0, n),
        "Temp_C": rng.uniform(40.0, 60.0, n),
        "Duration_min": rng.uniform(30.0, 300.0, n),
        "SubstrateConc_gL": rng.uniform(30.0, 70.0, n),
        "EnzymeToSubstrateRatio": [(0.01, 0.02, 0.04, 0.06)[i % 4]
                                   for i in range(n)],
        "Moisture_pct": rng.uniform(60.0, 75.0, n),
        "CrudeProtein_pct": rng.uniform(14.0, 20.0, n),
        "CrudeLipid_pct": rng.uniform(5.0, 15.0, n),
        "Ash_pct": rng.uniform(5.0, 15.0, n),
        "Hydroxyproline_pct": rng.uniform(0.5, 1.2, n),
        "Collagen_pct": rng.uniform(3.0, 7.0, n),
        "FinalDH_pct": rng.uniform(20.0, 45.0, n),
    })


def _trained(seed: int = 3) -> tuple[EBMOptimizer, pd.DataFrame]:
    df = _frame()
    opt = EBMOptimizer(seed=seed)
    opt.meta = df.copy()
    opt.fit_x_stats(opt.make_x(df))
    opt.train(df, seed=seed, epochs=4, n_aug=1)
    return opt, df


class TestBatchedAcquisition(unittest.TestCase):
    def test_chunk_size_does_not_change_proposals(self):
        opt, df = _trained()
        kwargs = dict(n_new=3, n_cand=13, seed=11, min_class_rows=1,
                      chains=2, langevin_steps=4)
        small = opt.acquire(df, ei_chunk=3, **kwargs)
        large = opt.acquire(df, ei_chunk=64, **kwargs)
        self.assertEqual(small, large)
        self.assertEqual(len(small), 3)

    def test_proposals_are_finite_and_in_bounds(self):
        opt, df = _trained()
        props = opt.acquire(df, n_new=5, n_cand=17, seed=5, min_class_rows=1,
                            chains=2, langevin_steps=4, ei_chunk=8)
        self.assertEqual(len(props), 5)
        for p in props:
            self.assertTrue(np.isfinite(p["EI"]))
            self.assertTrue(np.isfinite(p["expected_DH"]))
            self.assertIn(p["Enzyme"], ENZYMES)
            self.assertGreaterEqual(p["pH"], 2.0)
            self.assertLessEqual(p["pH"], 10.0)
            self.assertGreaterEqual(p["Temp_C"], 30.0)
            self.assertLessEqual(p["Temp_C"], 60.0)
            self.assertGreaterEqual(p["Duration_min"], 15.0)
            self.assertLessEqual(p["Duration_min"], 300.0)
            self.assertGreaterEqual(p["SubstrateConc_gL"], 30.0)
            self.assertLessEqual(p["SubstrateConc_gL"], 70.0)
            self.assertIn(p["EnzymeToSubstrateRatio"], (0.01, 0.02, 0.04, 0.06))
            for col in COMPOSITION_COLS:
                self.assertIn(col, p)

    def test_constant_dose_column_is_scaled_safely(self):
        # Historical E/S is constant at 0.02.  A 0.06 proposal must not become
        # a 4e7 normalized feature (the old std+1e-9 bug).
        opt, df = _trained()
        df = df.copy()
        df["EnzymeToSubstrateRatio"] = 0.02
        opt.fit_x_stats(opt.make_x(df))
        row = df.iloc[[0]].copy()
        row["EnzymeToSubstrateRatio"] = 0.06
        xn = opt.normalize_x(opt.make_x(row))
        self.assertTrue(np.isfinite(xn).all())
        self.assertLess(float(np.abs(xn).max()), 100.0)

    def test_empty_eligibility_falls_back_to_all_rows(self):
        # One row cannot satisfy MIN_CLASS_ROWS=3.  The fallback must still
        # produce a proposal instead of crashing on an empty base list.
        opt, df = _trained()
        props = opt.acquire(df.head(1), n_new=1, n_cand=5, seed=2,
                            min_class_rows=3, chains=2, langevin_steps=3,
                            ei_chunk=4)
        self.assertEqual(len(props), 1)

    def test_zero_candidates_and_invalid_settings(self):
        opt, df = _trained()
        self.assertEqual(opt.acquire(df, n_cand=0, seed=1), [])
        with self.assertRaises(ValueError):
            opt.acquire(df, n_cand=3, seed=1, chains=0)

    def test_langevin_samples_shape(self):
        opt, df = _trained()
        x = opt.normalize_x(opt.make_x(df.iloc[[0]]))[0]
        draws = opt.langevin_samples(x, k=3, steps=4)
        self.assertEqual(draws.shape, (3, 1))
        self.assertTrue(np.isfinite(draws).all())


if __name__ == "__main__":
    unittest.main()
