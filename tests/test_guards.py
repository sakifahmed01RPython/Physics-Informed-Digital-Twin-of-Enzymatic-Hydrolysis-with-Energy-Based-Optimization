"""Regression tests for the bench -> training handoff (step 1 guards).

Run from the repo root:
    python -m unittest discover -s tests -t . -v
"""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src import run_ebm_loop as loop
from src.csv_io import read_raw_csv
from src.ebm_optimizer import feasible_mask, feasible_y_best
from src.noise_floor import pooled_sd, replicate_groups
from src.twin_predict import TOL_FIT, TOL_PREDICTIVE, predict_run, run_confirmation
from src.validate_measured import check

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "data" / "processed" / "main_batch_clean.csv"
MEASURED = ROOT / "data" / "campaign" / "measured_runs.csv"
DESIGN = ROOT / "data" / "campaign" / "campaign_design.csv"


def raw_measured():
    return read_raw_csv(MEASURED)


def write_temp(df, directory, name="measured.csv"):
    path = Path(directory) / name
    df.to_csv(path, index=False)
    return path


def numeric(df):
    out = df.copy()
    for col in loop.NUMERIC:
        out[col] = pd.to_numeric(out[col], errors="raise")
    return out


class TestMeasuredLoader(unittest.TestCase):
    def test_blank_template_has_no_completed_rows(self):
        done = loop.load_measured_campaign_runs(MEASURED)
        self.assertTrue(done.empty)

    def test_one_completed_row_survives(self):
        raw = raw_measured()
        raw.loc[0, "FinalDH_pct"] = "21.4"
        with tempfile.TemporaryDirectory() as td:
            path = write_temp(raw, td)
            done = loop.load_measured_campaign_runs(path)
        self.assertEqual(len(done), 1)
        self.assertEqual(done.iloc[0]["BatchID"], "CAMPAIGN_001")
        self.assertAlmostEqual(float(done.iloc[0]["FinalDH_pct"]), 21.4)

    def test_time_formatted_cell_fails_loudly(self):
        raw = raw_measured()
        raw.loc[0, "FinalDH_pct"] = "4:48"
        with tempfile.TemporaryDirectory() as td:
            path = write_temp(raw, td)
            with self.assertRaises(ValueError) as ctx:
                loop.load_measured_campaign_runs(path)
        self.assertIn("CAMPAIGN_001", str(ctx.exception))
        self.assertIn("FinalDH_pct", str(ctx.exception))

    def test_completed_row_missing_setpoint_fails_loudly(self):
        raw = raw_measured()
        raw.loc[0, "FinalDH_pct"] = "21.4"
        raw.loc[0, "pH"] = np.nan
        with tempfile.TemporaryDirectory() as td:
            path = write_temp(raw, td)
            with self.assertRaises(ValueError) as ctx:
                loop.load_measured_campaign_runs(path)
        self.assertIn("missing setpoints", str(ctx.exception))


class TestAppendMeasured(unittest.TestCase):
    def test_pending_template_is_a_noop(self):
        main = pd.read_csv(MAIN)
        merged = loop.append_measured(main, loop.load_measured_campaign_runs(MEASURED))
        self.assertEqual(len(merged), len(main))
        self.assertFalse(merged[loop.MODEL_COLS].isna().any().any())

    def test_one_filled_row_trains_nan_free(self):
        raw = raw_measured()
        raw.loc[0, "FinalDH_pct"] = "21.4"
        done = numeric(raw[raw["FinalDH_pct"].notna()].copy())
        main = pd.read_csv(MAIN)
        merged = loop.append_measured(main, done)

        self.assertEqual(len(merged), len(main) + 1)
        self.assertEqual(merged.iloc[-1]["BatchID"], "CAMPAIGN_001")
        self.assertFalse(merged[loop.MODEL_COLS].isna().any().any())
        self.assertTrue(np.isfinite(merged[loop.MODEL_COLS].to_numpy(float)).all())

    def test_imputation_uses_the_material_median(self):
        main = pd.read_csv(MAIN)
        raw = raw_measured()
        idx = raw.index[raw["BatchID"] == "CAMPAIGN_008"][0]
        raw.loc[idx, "FinalDH_pct"] = "22.9"
        done = numeric(raw[raw["FinalDH_pct"].notna()].copy())

        prepared, notes = loop.prepare_measured(done, main)
        expected = float(main[main["RawMaterial"] == "salmon_frames"]["CrudeProtein_pct"].median())
        self.assertAlmostEqual(float(prepared.iloc[0]["CrudeProtein_pct"]), expected)
        self.assertTrue(any("CAMPAIGN_008" in n for n in notes))

    def test_nonfinite_proposal_is_rejected(self):
        with self.assertRaises(RuntimeError):
            loop.check_proposals([{
                "EI": float("nan"), "expected_DH": 1.0, "pH": 7.0,
                "Temp_C": 50.0, "Duration_min": 60.0, "SubstrateConc_gL": 50.0,
                "EnzymeToSubstrateRatio": 0.02,
            }])


class TestValidator(unittest.TestCase):
    def test_blank_template_is_structurally_valid_but_empty(self):
        rep = check(MEASURED, DESIGN)
        self.assertEqual(rep.problems, [])
        self.assertEqual(rep.n_complete, 0)
        self.assertEqual(rep.n_pending, 15)
        self.assertEqual(rep.n_rows, 15)

    def test_partial_row_is_a_problem(self):
        raw = raw_measured()
        raw.loc[0, "Moisture_pct"] = "72.0"
        with tempfile.TemporaryDirectory() as td:
            rep = check(write_temp(raw, td), DESIGN)
        self.assertTrue(any("PARTIAL" in p for p in rep.problems))
        self.assertEqual(rep.n_complete, 0)
        self.assertEqual(rep.n_pending, 14)

    def test_completed_row_without_composition_warns_not_fails(self):
        raw = raw_measured()
        raw.loc[0, "FinalDH_pct"] = "21.4"
        with tempfile.TemporaryDirectory() as td:
            rep = check(write_temp(raw, td), DESIGN)
        self.assertEqual(rep.problems, [])
        self.assertEqual(rep.n_complete, 1)
        self.assertTrue(any("impute" in w for w in rep.warnings))

    def test_time_format_is_caught(self):
        raw = raw_measured()
        raw.loc[0, "FinalDH_pct"] = "4:48"
        with tempfile.TemporaryDirectory() as td:
            rep = check(write_temp(raw, td), DESIGN)
        self.assertTrue(any("time-formatted" in p for p in rep.problems))


class TestConfirmationReport(unittest.TestCase):
    def test_blank_campaign_has_no_false_flags(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "confirm.md"
            run_confirmation(MEASURED, out)
            text = out.read_text(encoding="utf-8")
        self.assertIn("0 of 15", text)
        self.assertNotIn("FLAG", text)
        self.assertNotIn("nan", text.lower())

    def test_only_measured_rows_are_scored(self):
        raw = raw_measured()
        idx = raw.index[raw["BatchID"] == "CAMPAIGN_008"][0]
        raw.loc[idx, "FinalDH_pct"] = "22.9"
        with tempfile.TemporaryDirectory() as td:
            path = write_temp(raw, td)
            out = Path(td) / "confirm.md"
            run_confirmation(path, out)
            text = out.read_text(encoding="utf-8")
        self.assertIn("CAMPAIGN_008", text)
        self.assertNotIn("| CAMPAIGN_001 |", text)
        self.assertIn("1 measured", text)
        self.assertIn("14 pending", text)
        self.assertNotIn("nan", text.lower())


class TestAcquisitionAnchor(unittest.TestCase):
    def test_feasible_best_excludes_720_min_runs(self):
        main = pd.read_csv(MAIN)
        self.assertAlmostEqual(feasible_y_best(main), 40.3, places=6)
        mask = feasible_mask(main)
        excluded = main["BatchID"].isin(["BATCH_009", "BATCH_010"])
        self.assertFalse(mask[excluded].any())
        self.assertTrue(mask[~excluded].any())

    def test_new_run_uses_predictive_band(self):
        pred = predict_run("Alcalase", "salmon_frames", 55.0, 8.0, 120.0, 50.0, 0.02)
        self.assertEqual(pred["tolerance_DH_pts"], TOL_PREDICTIVE)
        self.assertEqual(pred["fit_tolerance_DH_pts"], TOL_FIT)


class TestNoiseFloor(unittest.TestCase):
    def test_pooled_sd_from_real_replicates(self):
        df = pd.read_csv(MAIN)
        groups = replicate_groups(df)
        self.assertEqual(len(groups), 5)
        pooled, dof = pooled_sd(groups)
        self.assertAlmostEqual(pooled, 5.93, places=2)
        self.assertEqual(dof, 7)


if __name__ == "__main__":
    unittest.main()
