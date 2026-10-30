"""Regression tests for the resumable benchmark runner (step 4 hardening).

The heavy world simulation is replaced by a deterministic fake; these tests
exercise the manifest, config hash, per-world files, resume and failure paths.

Run from the repo root:
    python -m unittest tests.test_benchmark_runner -v
"""
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

import src.benchmark_policy as bp


def _cfg(**kwargs) -> bp.BenchmarkConfig:
    base = dict(n_worlds=2, world_start=0, budget=5, batch=4, epochs=20,
                n_aug=2, n_cand=8, langevin_steps=4, chains=2, ei_chunk=4,
                oracle_candidates=300, workers=1,
                policies=("twin_current", "random"))
    base.update(kwargs)
    return bp.BenchmarkConfig(**base)


def _history() -> pd.DataFrame:
    rows = [
        (1, "seed", 0, 30.0, 30.0, 400.0, 400.0, False, np.nan, np.nan),
        (2, "adaptive", 1, 35.0, 34.0, 420.0, 420.0, False, 2.0, 33.0),
        (3, "adaptive", 1, 32.0, 33.0, 410.0, 410.0, False, 1.0, 31.0),
    ]
    return pd.DataFrame(rows, columns=[
        "trial", "source", "round", "true_DH_pct", "FinalDH_pct",
        "true_ORAC", "ORAC", "gross_error", "proposed_EI",
        "proposed_expected_DH"])


class TestRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.old_out = bp.OUT_DIR
        self.old_runs = bp.RUNS_DIR
        self.old_task = bp.run_world_task
        bp.OUT_DIR = self.out
        bp.RUNS_DIR = self.out / "runs"
        self.calls: list[int] = []
        self.fail_world: int | None = None
        bp.run_world_task = self._fake_task

    def tearDown(self):
        bp.OUT_DIR = self.old_out
        bp.RUNS_DIR = self.old_runs
        bp.run_world_task = self.old_task

    def _fake_task(self, task):
        world, cfg_dict = task
        self.calls.append(world)
        if self.fail_world == world:
            self.fail_world = None
            raise RuntimeError("synthetic worker failure")
        cfg = bp.BenchmarkConfig(**cfg_dict)
        hist = _history()
        metrics = bp.policy_metrics(hist, 50.0, 550.0, cfg)
        return {
            "world": world,
            "oracle": {"best_dh": 50.0, "best_orac": 550.0,
                       "n_evaluated": 1000},
            "policies": {"twin_current": metrics},
            "histories": [hist],
        }

    def test_config_hash_ignores_range_and_workers(self):
        a = _cfg(n_worlds=2, world_start=0, workers=1)
        b = _cfg(n_worlds=25, world_start=100, workers=3)
        self.assertEqual(bp._config_hash(a), bp._config_hash(b))
        c = _cfg(epochs=21)
        self.assertNotEqual(bp._config_hash(a), bp._config_hash(c))

    def test_history_rows_are_part_of_config_identity(self):
        a = _cfg(history_rows=0)
        b = _cfg(history_rows=31)
        self.assertNotEqual(bp._config_hash(a), bp._config_hash(b))

    def test_world_label_handles_chunks(self):
        self.assertEqual(bp._world_label([100, 101, 102]), "worlds 100–102")
        self.assertEqual(bp._world_label([100, 101, 150, 151]),
                         "worlds 100–101, 150–151")
        self.assertEqual(bp._world_label([]), "no worlds")

    def test_run_writes_manifest_and_resume_does_not_rerun(self):
        cfg = _cfg()
        bp.run_benchmark(cfg, prefix="t", min_free_gb=0)
        self.assertEqual(self.calls, [0, 1])
        manifest = json.loads(
            (self.out / "runs" / "t" / "manifest.json").read_text())
        self.assertEqual(manifest["worlds_completed"], [0, 1])
        self.assertEqual(manifest["status"], "complete")
        self.assertTrue((self.out / "t.json").exists())
        self.assertTrue((self.out / "t_summary.md").exists())

        self.calls.clear()
        bp.run_benchmark(cfg, prefix="t", resume=True, min_free_gb=0)
        self.assertEqual(self.calls, [])

    def test_chunked_resume_adds_only_missing_worlds(self):
        bp.run_benchmark(_cfg(n_worlds=2, world_start=0), prefix="c",
                         min_free_gb=0)
        self.calls.clear()
        bp.run_benchmark(_cfg(n_worlds=2, world_start=2), prefix="c",
                         resume=True, min_free_gb=0)
        self.assertEqual(self.calls, [2, 3])
        manifest = json.loads(
            (self.out / "runs" / "c" / "manifest.json").read_text())
        self.assertEqual(manifest["worlds_completed"], [0, 1, 2, 3])

    def test_changed_settings_are_refused(self):
        cfg = _cfg()
        bp.run_benchmark(cfg, prefix="t", min_free_gb=0)
        with self.assertRaises(SystemExit):
            bp.run_benchmark(replace(cfg, epochs=cfg.epochs + 1), prefix="t",
                             resume=True, min_free_gb=0)

    def test_failed_world_is_recorded_then_retried(self):
        cfg = _cfg()
        self.fail_world = 1
        bp.run_benchmark(cfg, prefix="f", min_free_gb=0)
        manifest = json.loads(
            (self.out / "runs" / "f" / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "partial")
        self.assertIn("1", manifest["worlds_failed"])
        self.assertEqual(manifest["worlds_completed"], [0])

        bp.run_benchmark(cfg, prefix="f", resume=True, min_free_gb=0)
        manifest = json.loads(
            (self.out / "runs" / "f" / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["worlds_failed"], {})
        self.assertEqual(manifest["worlds_completed"], [0, 1])
        self.assertEqual(self.calls, [0, 1, 1])


if __name__ == "__main__":
    unittest.main()
