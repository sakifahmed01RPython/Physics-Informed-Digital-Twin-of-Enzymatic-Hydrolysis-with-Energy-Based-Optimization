"""Regression tests for the policy benchmark (step 3).

Run from the repo root:
    python -m unittest discover -s tests -t . -v
"""
import json
import unittest
from dataclasses import asdict

import numpy as np
import pandas as pd

from src.benchmark_policy import (BenchmarkConfig, _jsonable, _legacy_design,
                                  policy_metrics, run_world_task, summarize)
from src.synthetic_lab import SyntheticLab


def _history():
    """One seed + four adaptive runs, including a gross-error 'winner'."""
    rows = [
        # trial, source, round, true, measured, true_orac, orac, gross, EI, expected
        (1, "seed", 0, 30.0, 30.0, 400.0, 400.0, False, np.nan, np.nan),
        (2, "adaptive", 1, 20.0, 45.0, 300.0, 500.0, True, 10.0, 40.0),
        (3, "adaptive", 1, 38.0, 35.0, 450.0, 450.0, False, 5.0, 30.0),
        (4, "adaptive", 1, 25.0, 28.0, 350.0, 350.0, False, 2.0, 20.0),
        (5, "adaptive", 1, 32.0, 33.0, 380.0, 380.0, False, 1.0, 25.0),
    ]
    return pd.DataFrame(rows, columns=[
        "trial", "source", "round", "true_DH_pct", "FinalDH_pct",
        "true_ORAC", "ORAC", "gross_error", "proposed_EI",
        "proposed_expected_DH"])


def _cfg(**kwargs):
    base = dict(n_worlds=1, world_start=0, budget=5, batch=4, epochs=20,
                n_aug=2, n_cand=8, oracle_candidates=300, workers=1,
                policies=("twin_current", "random"))
    base.update(kwargs)
    return BenchmarkConfig(**base)


class TestPolicyMetrics(unittest.TestCase):
    def test_winner_curse_and_metric_keys(self):
        cfg = _cfg()
        m = policy_metrics(_history(), oracle_best_dh=50.0,
                           oracle_best_orac=550.0, cfg=cfg)
        # The lab would advance the gross-error run (measured 45, true 20),
        # not the best true run (38).
        self.assertAlmostEqual(m["best_measured"], 45.0)
        self.assertAlmostEqual(m["selected_true"], 20.0)
        self.assertAlmostEqual(m["best_true"], 38.0)
        self.assertEqual(m["selected_trial"], 2)
        self.assertAlmostEqual(m["regret_true"], 12.0)
        self.assertAlmostEqual(m["regret_selected"], 30.0)
        self.assertAlmostEqual(m["regret_measured"], 5.0)
        self.assertFalse(m["reached_95"])
        self.assertEqual(m["trials_to_95"], 6)  # budget + 1 (censored)
        for key in ["reached_80", "trials_to_80", "reached_90", "trials_to_90",
                    "reached_95", "trials_to_95", "orac_at_selected",
                    "ei_vs_true_pooled", "expected_vs_true_pooled"]:
            self.assertIn(key, m)

    def test_ei_rewards_the_gross_error(self):
        cfg = _cfg()
        m = policy_metrics(_history(), oracle_best_dh=50.0,
                           oracle_best_orac=550.0, cfg=cfg)
        # The highest-EI proposal is the gross-error row: it looks like the
        # biggest improvement but is the worst true run of the batch.
        self.assertEqual(m["ei_top_hit_rate"], 0.0)
        self.assertEqual(m["ei_top_improved_rate"], 1.0)
        self.assertLess(m["ei_spearman_true_mean"], 0.0)
        self.assertGreater(m["ei_spearman_improvement_mean"], 0.0)
        self.assertLess(m["ei_vs_true_pooled"], 0.0)
        self.assertGreater(m["ei_vs_measured_pooled"], 0.0)

    def test_best_true_cannot_exceed_oracle(self):
        cfg = _cfg()
        m = policy_metrics(_history(), oracle_best_dh=50.0,
                           oracle_best_orac=550.0, cfg=cfg)
        self.assertLessEqual(m["best_true"], 50.0 + 1e-9)
        self.assertGreaterEqual(m["regret_true"], -1e-9)


class TestSummary(unittest.TestCase):
    def _results(self, identical=True):
        cfg = _cfg(n_worlds=2, budget=5, batch=4)
        results = []
        for world in (0, 1):
            hist = _history()
            m = policy_metrics(hist, oracle_best_dh=50.0,
                               oracle_best_orac=550.0, cfg=cfg)
            policies = {"twin_current": dict(m)}
            if identical:
                policies["random"] = dict(m)
            else:
                other = dict(m)
                other["best_true"] = 35.0
                other["regret_true"] = 15.0
                policies["random"] = other
            results.append({
                "world": world,
                "oracle": {"best_dh": 50.0, "best_orac": 550.0,
                           "n_evaluated": 1000},
                "policies": policies,
            })
        return results, cfg

    def test_ties_split_win_credit(self):
        results, cfg = self._results(identical=True)
        summary = summarize(results, cfg)
        self.assertEqual(summary["headline_split"], "all")
        wr = summary["win_rates"]["all"]
        self.assertAlmostEqual(wr["twin_current"], 50.0)
        self.assertAlmostEqual(wr["random"], 50.0)
        head = summary["splits"]["all"]["twin_current"]
        self.assertIn("best_true_ci", head)
        self.assertIn("regret_true_ci", head)
        pair = summary["pairwise"]["all"]["twin_current vs random"]
        self.assertEqual(pair["n"], 2)
        self.assertAlmostEqual(pair["mean_diff"], 0.0)
        self.assertAlmostEqual(pair["a_wins_pct"], 0.0)
        self.assertAlmostEqual(pair["ties_pct"], 100.0)

    def test_summary_is_json_safe_with_undefined_metrics(self):
        results, cfg = self._results(identical=True)
        summary = summarize(results, cfg)
        # 'random' has no EI, so its rank metrics are NaN.  They must become
        # JSON null, not NaN.
        text = json.dumps(_jsonable(summary), allow_nan=False)
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)
        parsed = json.loads(text)
        self.assertIn("splits", parsed)
        self.assertIn("pairwise", parsed)
        self.assertIn("win_rates", parsed)


class TestWarmStart(unittest.TestCase):
    def test_legacy_design_matches_real_enzyme_counts(self):
        lab = SyntheticLab(0)
        design = _legacy_design(lab, 31, np.random.default_rng(1))
        self.assertEqual(len(design), 31)
        expected = {"Alcalase": 20, "Neutrase": 3, "Pepsin": 2,
                    "Alcalase+Kojizyme": 2, "Flavourzyme": 2,
                    "Alcalase+Neutrase": 1, "Alcalase+Flavourzyme": 1}
        self.assertEqual(design["Enzyme"].value_counts().to_dict(), expected)
        self.assertTrue(np.allclose(design["EnzymeToSubstrateRatio"], 0.02))

    def test_history_does_not_consume_campaign_trials(self):
        cfg = _cfg(n_worlds=1, budget=18, batch=3, epochs=20, n_aug=2,
                   n_cand=8, oracle_candidates=300, history_rows=31,
                   policies=("twin_current", "random"))
        res = run_world_task((0, asdict(cfg)))
        self.assertEqual(set(res["policies"]), {"twin_current", "random"})
        for hist in res["histories"]:
            # 18 campaign rows; the 31 history rows are training data only.
            self.assertEqual(len(hist), 18)
            self.assertEqual(int(hist["trial"].max()), 18)
            self.assertEqual(set(hist["source"]), {"seed", "adaptive"})


class TestOneWorldSmoke(unittest.TestCase):
    def test_one_world_runs_end_to_end(self):
        cfg = _cfg(n_worlds=1, budget=18, batch=3, epochs=20, n_aug=2,
                   n_cand=8, oracle_candidates=300,
                   policies=("random", "twin_current"))
        res = run_world_task((0, asdict(cfg)))
        self.assertEqual(res["world"], 0)
        self.assertEqual(set(res["policies"]), {"random", "twin_current"})
        self.assertEqual(len(res["histories"]), 2)
        self.assertGreater(res["oracle"]["best_dh"], 0.0)
        for hist in res["histories"]:
            self.assertEqual(len(hist), 18)
            self.assertTrue(np.isfinite(hist["true_DH_pct"]).all())
            self.assertTrue(np.isfinite(hist["FinalDH_pct"]).all())
            self.assertTrue(hist["true_DH_pct"].between(0, 100).all())
            self.assertTrue(hist["FinalDH_pct"].between(0, 100).all())
        for policy, m in res["policies"].items():
            self.assertGreaterEqual(m["regret_true"], -1e-6, policy)
            self.assertLessEqual(m["best_true"],
                                 res["oracle"]["best_dh"] + 1e-6, policy)

        # The eligibility guard still leaves only Alcalase with >=3 seed rows.
        # E/S is now a modelled decision variable (step 5), so it must be one
        # of the weighed dose levels rather than forced to 0.02.
        twin = [h for h in res["histories"] if h["policy"].iloc[0] == "twin_current"][0]
        adaptive = twin[twin["source"] == "adaptive"]
        self.assertEqual(set(adaptive["Enzyme"]), {"Alcalase"})
        self.assertTrue(adaptive["EnzymeToSubstrateRatio"].isin(
            (0.01, 0.02, 0.04, 0.06)).all())


if __name__ == "__main__":
    unittest.main()
