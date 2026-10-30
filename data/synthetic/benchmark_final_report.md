# Synthetic policy benchmark - final report

**Status:** completed in-silico evidence for the acquisition loop. Synthetic only.
**Scope:** `two_pool_exposure_v1` worlds. This is **not** a real-world
trial-reduction claim and **not** a validation of the twin's ODE.
**Frozen held-out run:** `data/synthetic/runs/benchmark_heldout` (worlds
100-199), config hash `2de0ff3889ec1fb1`, code hash `a6b3c7985347a10d`.
**Post-hoc analyses:** 500-candidate sensitivity, 102-199 leave-out, and
cold-vs-warm-start check. These are labelled post-hoc throughout.

---

## 1. The question

At the same 30-run lab budget (15-run seed campaign + 15 adaptive runs), does
the production-style EBM acquisition loop reach a better true DH than random,
LHC, OFAT or grid search in a world it was not tuned on?

The benchmark deliberately does **not** generate data from the twin's ODE.
Generating from the twin would test the software, not the decision policy. The
world is a different two-pool exposure model with lot effects, substrate
inhibition, enzyme-specific pH/temperature optima, assay noise, 5% gross errors,
slow drift, and non-monotonic ORAC. A win here is necessary, not sufficient.

---

## 2. Frozen protocol and provenance

| Item | Value |
|---|---|
| Development worlds | 0-24 (tuning), 25-49 (confirmation), 50-99 (spare) |
| Held-out worlds | 100-199, pre-registered before the run |
| Primary metric | Mean best **true** DH at the 30-run budget |
| Secondary metrics | Trials to 95% of oracle, trials to oracle-2.1 DH, true regret, selected true DH |
| Budget | 30 runs: 15-run seed + 5 adaptive rounds x 3 |
| EBM settings | 250 epochs, n_aug=6, n_cand=150, Langevin 120 steps x 4 chains, EI chunk 64 |
| Oracle | 50,000 candidates + local refinement; finite, so regret is a lower bound |
| Frozen policy | `twin_explore` (`MIN_CLASS_ROWS=1`); the name is historical |
| Workers | 2, BLAS/OpenMP pinned to 1; 3.2-3.4 GB free RAM observed |
| Pre-registration | the internal benchmark protocol |

The held-out run was executed in four resumable chunks. The manifest records
git `45aecae` because the step-4/5 code was still uncommitted at run time. The
exact code is identified by the manifest `code_hash` `a6b3c7985347a10d` and was
committed afterwards as `ae3c9c2`. The per-world files, not the aggregate
summary, are the frozen evidence.

**Post-hoc code note.** The `--history-rows` option was added after the frozen
run for the warm-start check. It does not alter the frozen per-world files, and
the cold-start path (`history_rows=0`) is unchanged; the config hash changes
because the option is part of the run identity. Re-running the original
cold-start benchmark now requires `--history-rows 0` and will produce a new
config hash, not the frozen `2de0ff3889ec1fb1`.

The cold-start and warm-start post-hoc runs used code hash
`aaaa8e1e03dc5cae` (HEAD `ae3c9c2` plus the uncommitted `--history-rows`
option). The manifest in each `runs/<prefix>/` directory is the exact
provenance record. Later documentation-only edits do not change the behaviour,
but they do change the code hash.

The generated summary's "Runtime: 1.1 min" is the final chunk's runtime, not the
full wall time. The four chunks took roughly 4.5 min in total.

---

## 3. Headline held-out result (worlds 100-199)

Primary metric: mean best true DH at 30 runs. 95% CIs are world-bootstrap.

| Policy | Mean best true DH | 95% CI | Mean true regret | Reached 95% of oracle | Trials to 95% (median, reached) | Selected true DH | Best measured |
|---|---:|---|---:|---:|---:|---:|---:|
| `twin_explore` | **38.4** | [37.2, 39.6] | 11.2 | 4.0% | 24.5 | 35.2 | 43.7 |
| `random` | 34.8 | [33.9, 35.8] | 14.8 | 0.0% | not reached | 32.2 | 37.4 |
| `lhc` | 35.0 | [34.1, 36.1] | 14.6 | 0.0% | not reached | 31.8 | 37.9 |
| **`ofat`** | **40.5** | **[39.2, 41.7]** | **9.1** | **15.0%** | **27.0** | **35.4** | **45.7** |
| `grid` | 35.9 | [34.9, 37.0] | 13.7 | 1.0% | 23.0 | 32.8 | 38.6 |
| `oracle` | 49.6 | [48.9, 50.3] | 0.0 | 100.0% | 16.0 | 49.1 | 57.7 |

Win rates (ties split; oracle excluded):

| Policy | Win rate |
|---|---:|
| `twin_explore` | 29.2% |
| `random` | 5.2% |
| `lhc` | 3.2% |
| **`ofat`** | **55.2%** |
| `grid` | 7.2% |

**The headline is not a win over the strongest baseline.** OFAT is 2.1 DH
ahead of the frozen twin policy and wins 55.2% of worlds outright. The twin
beats random, LHC and grid, but not OFAT.

---

## 4. Pairwise comparisons (held-out 100-199)

| Comparison | Mean difference (DH) | 95% CI | A wins | Ties | B wins |
|---|---:|---|---:|---:|---:|
| twin_explore vs random | **+3.55** | [2.64, 4.42] | 83.0% | 10.0% | 7.0% |
| twin_explore vs LHC | **+3.31** | [2.42, 4.13] | 84.0% | 10.0% | 6.0% |
| twin_explore vs grid | **+2.42** | [1.41, 3.42] | 67.0% | 5.0% | 28.0% |
| twin_explore vs OFAT | **-2.11** | [-3.13, -1.08] | 33.0% | 3.0% | 64.0% |
| OFAT vs random | +5.65 | [4.57, 6.70] | 82.0% | 11.0% | 7.0% |
| OFAT vs grid | +4.53 | [3.72, 5.35] | 78.0% | 14.0% | 8.0% |

### Leave-out check excluding timing worlds 100-101

Worlds 100-101 were run once before the main held-out run solely to measure
runtime; no setting changed. Excluding them (worlds 102-199):

| Policy | Mean best true DH | 95% CI | Win rate |
|---|---:|---|---:|
| `twin_explore` | 38.47 | [37.23, 39.78] | 29.8% |
| `random` | 34.87 | [33.86, 35.87] | 5.3% |
| `lhc` | 35.11 | [34.13, 36.13] | 3.3% |
| `ofat` | 40.53 | [39.26, 41.80] | 54.3% |
| `grid` | 35.95 | [34.92, 37.00] | 7.3% |
| `oracle` | 49.65 | [48.95, 50.34] | - |

Pairwise: twin vs random +3.61 [2.69, 4.52], twin wins 82.7%; twin vs OFAT
-2.06 [-3.05, -1.03], OFAT wins 63.3%. The conclusion is unchanged.

---

## 5. Target sensitivity

A single 95%-of-oracle threshold can censor every policy. The 80%/90% columns
show whether the ranking is an artefact of that threshold.

| Policy | Reached 80% | Reached 90% | Reached 95% | Lab-precision (oracle-2.1 DH) |
|---|---:|---:|---:|---:|
| `twin_explore` | 40.0% | 11.0% | 4.0% | 4.0% |
| `random` | 12.0% | 2.0% | 0.0% | 0.0% |
| `lhc` | 14.0% | 0.0% | 0.0% | 0.0% |
| `ofat` | 56.0% | 28.0% | 15.0% | 14.0% |
| `grid` | 20.0% | 5.0% | 1.0% | 1.0% |
| `oracle` | 100.0% | 100.0% | 100.0% | 100.0% |

The 2.1 DH lab-precision band is twice the real-replicate repeatability
(1.07 DH), i.e. the limit of what the real assay can distinguish. The synthetic
assay noise is deliberately larger than that, so low reach rates are expected.

---

## 6. Is the energy model doing the work?

Held-out EI diagnostics for `twin_explore`:

| Diagnostic | Value | Interpretation |
|---|---:|---|
| EI vs realised improvement (mean Spearman rho) | 0.02 | essentially no rank information |
| Top-EI proposal was best of its batch | 0.4% | chance with 3 proposals is 33% |
| Top-EI proposal improved on the incumbent | 0.2% | almost never |
| EI vs true DH (pooled rho) | -0.14 | EI is slightly anti-correlated with truth |
| Expected DH vs true DH (pooled rho) | 0.29 | weak positive signal from the mean head |

The held-out evidence does **not** show that expected improvement is a good
ranker. The twin's advantage over random/LHC/grid is more plausibly explained
by the candidate distribution (trust region around the best measured rows),
the E/S decision variable, and the relaxed eligibility guard, not by a smart
energy landscape.

The development-only ablation is consistent with a small EI effect, but it is
not held-out evidence: on worlds 0-24, the same candidate pool with EI ranking
averaged 37.5 DH vs 36.0 with random ranking (+1.5 DH). Treat that as a
hypothesis, not a result.

---

## 7. Pre-registered acquisition-compute sensitivity

Pre-registered rule: rerun worlds 100-109 at 500 candidates (same epochs,
Langevin settings and oracle). If the twin-vs-random win rate changes by more
than 15 percentage points, the headline becomes "sensitive to acquisition
compute" and no win is claimed.

| Metric, worlds 100-109 | 150 candidates | 500 candidates | Change |
|---|---:|---:|---:|
| `twin_explore` mean best true DH | 34.48 | 34.16 | -0.32 |
| `random` mean best true DH | 32.60 | 32.60 | 0.00 |
| Twin-vs-random mean advantage | +1.88 | +1.56 | -0.32 |
| Twin-vs-random win rate | 80.0% | 70.0% | **-10.0 points** |
| `ofat` mean best true DH | 35.86 | 35.86 | 0.00 |

The rule passes: the change is -10 points, inside the 15-point limit. More
candidate compute did **not** improve the twin's mean; it slightly reduced it.
The 150-candidate headline is therefore not a compute artefact. The sample is
only 10 worlds, so the CIs are wide and this is a guard, not a precise estimate.

---

## 8. Post-hoc warm-start check: does the eligibility guard matter in production?

### The problem

The original benchmark seed is only the 15 synthetic campaign runs. It does not
include the 31 historical batches that the production loop trains on. As a
result, after the synthetic seed only Alcalase has at least 3 rows, and the
production guard `MIN_CLASS_ROWS=3` excludes almost every enzyme. The frozen
`twin_explore` policy (`MIN_CLASS_ROWS=1`) was partly winning by escaping a
cold-start artefact.

In the real lab, the 31 historical rows plus the 15-run campaign put every
enzyme at 3 or more rows:

| Enzyme | Historical | Gap-fill | Total |
|---|---:|---:|---:|
| Alcalase | 20 | 8 | 28 |
| Neutrase | 3 | 0 | 3 |
| Pepsin | 2 | 1 | 3 |
| Alcalase+Kojizyme | 2 | 1 | 3 |
| Flavourzyme | 2 | 1 | 3 |
| Alcalase+Neutrase | 1 | 2 | 3 |
| Alcalase+Flavourzyme | 1 | 2 | 3 |

### The check

A post-hoc warm-start variant gives every policy 31 free synthetic history rows
with exactly the real enzyme counts. History rows are training data only; they
do not consume campaign trials and are not part of the campaign metrics. The
rest of the configuration is identical to the frozen run.

**Development worlds 0-24 (paired cold vs warm):**

| Policy | Cold start | Warm start | Cold - warm (95% CI) |
|---|---:|---:|---:|
| `twin_current` (min 3) | 34.71 | 36.89 | -2.18 [-4.19, -0.32] |
| `twin_explore` (min 1) | 37.73 | 37.66 | +0.06 [-2.43, +2.64] |
| `ofat` | 39.63 | 38.99 | +0.64 [-0.44, +1.86] |
| `random` | 33.75 | 33.75 | 0.00 |

Cold-start `twin_explore` vs `twin_current`: +3.02 DH [0.84, 5.35], min 1 wins
64% of worlds. Warm-start: +0.77 DH [-0.49, 2.14], min 1 wins 40%, min 3 wins
44%, 16% ties. **The guard advantage disappears once realistic history exists.**

**Held-out worlds 100-109 (post-hoc, warm start only):**

| Policy | Mean best true DH | 95% CI | Win rate |
|---|---:|---|---:|
| `twin_current` (min 3) | 35.46 | [32.71, 38.36] | 30.0% |
| `twin_explore` (min 1) | 34.29 | [31.68, 36.94] | 20.0% |
| `ofat` | 35.86 | [31.24, 41.07] | 40.0% |
| `random` | 32.60 | [29.62, 35.61] | 10.0% |
| `lhc` | 31.68 | [29.10, 34.34] | 0.0% |
| `grid` | 33.79 | [29.92, 38.00] | 0.0% |

On these 10 worlds, `twin_current` (35.5) is slightly ahead of `twin_explore`
(34.3) and essentially tied with OFAT (35.9); the CIs overlap heavily. This is
a post-hoc sensitivity, not the pre-registered held-out result.

### What it means for production

- The production default `MIN_CLASS_ROWS=3` is defensible when the 31 historical
  rows are present. The warm-start check does not justify switching production
  to `min_class_rows=1` on synthetic evidence.
- The frozen held-out result still stands as a **cold-start** result. It should
  not be quoted as proof that the production guard is harmful.
- A future benchmark version should include a matched synthetic history in the
  default protocol, not as a post-hoc check.

---

## 9. What the evidence supports

Supported, in the synthetic world:

1. At a fixed 30-run budget, the frozen twin policy reaches a higher best true
   DH than random search (+3.55 DH, 83% world wins), LHC (+3.31 DH, 84%) and
   grid search (+2.42 DH, 67%).
2. The advantage is not caused by the 150-candidate acquisition budget: the
   500-candidate sensitivity changes the twin-vs-random win rate by -10 points,
   inside the pre-registered 15-point limit.
3. The result is not driven by the two timing worlds: excluding 100-101 leaves
   the conclusion unchanged.
4. The production `min_class_rows=3` guard is not harmful once realistic
   historical data is present; the cold-start guard penalty is an artefact of
   the benchmark's seed design.

Not supported:

1. **The twin does not beat OFAT.** OFAT is 2.1 DH ahead and wins 55.2% of
   worlds. Any claim that the loop reduces trials against the strongest
   baseline is false in this benchmark.
2. **Expected improvement is not shown to be a good ranker.** EI vs realised
   improvement is rho=0.02; the top-EI proposal is best 0.4% of the time. The
   gain over random is not evidence of a smart energy landscape.
3. **No real-world trial reduction.** The world is synthetic and deliberately
   different from the twin. Real-data validation is future work.
4. **No claim about ORAC.** The loop targets DH; ORAC is a secondary logged
   outcome, and the acquisition does not optimise it.

---

## 10. Threats to validity

- **Synthetic world misspecification.** The generator is plausible, not fitted.
  Its smooth, low-dimensional response may favour OFAT more than a real
  hydrolysate system would. This is a stress test, not a forecast.
- **One seed design.** The 100 worlds vary world parameters, not campaign
  designs. A different 15-run seed campaign could change the ranking.
- **Finite oracle.** 50,000 candidates + refinement can miss the true optimum;
  regret is a lower bound.
- **Winner's curse.** The selected true DH is lower than the best measured DH
  for every policy because gross errors can make a bad run look best. The
  lab-facing selection metric is the honest one.
- **Cold-start headline.** The pre-registered held-out policy was tuned in a
  cold-start world. The warm-start check reduces, but does not eliminate, the
  concern that the frozen policy is a benchmark artefact.
- **Small sensitivity sample.** The 500-candidate check uses 10 worlds; its CIs
  are wide. It is a guard against a compute artefact, not a precise estimate.
- **Post-hoc analyses.** The leave-out, 500-candidate and warm-start checks were
  run after the held-out result was seen. They are labelled post-hoc and do not
  replace the pre-registered result.
- **Noise and lot effects.** The synthetic assay noise is larger than the real
  repeatability, and lot/occasion effects are simulated, not estimated from the
  campaign.

---

## 11. Reproduction

Frozen held-out run (four chunks; `--resume` after the first):

```powershell
python -m src.benchmark_policy --worlds 100 --world-start 100 --budget 30 `
  --batch 3 --epochs 250 --n-aug 6 --n-cand 150 --langevin-steps 120 `
  --chains 4 --ei-chunk 64 --oracle-candidates 50000 --workers 2 `
  --policies twin_explore,random,lhc,ofat,grid,oracle `
  --prefix benchmark_heldout --resume
```

500-candidate sensitivity (worlds 100-109):

```powershell
python -m src.benchmark_policy --worlds 10 --world-start 100 --budget 30 `
  --batch 3 --epochs 250 --n-aug 6 --n-cand 500 --langevin-steps 120 `
  --chains 4 --ei-chunk 64 --oracle-candidates 50000 --workers 2 `
  --policies twin_explore,random,lhc,ofat,grid,oracle `
  --prefix benchmark_sensitivity_500
```

Warm-start sensitivity (31 free history rows):

```powershell
python -m src.benchmark_policy --worlds 25 --world-start 0 --budget 30 `
  --batch 3 --epochs 250 --n-aug 6 --n-cand 150 --langevin-steps 120 `
  --chains 4 --ei-chunk 64 --oracle-candidates 50000 --history-rows 31 `
  --workers 2 --policies twin_current,twin_explore,random,lhc,ofat,grid,oracle `
  --prefix benchmark_warm_start_dev
```

Post-hoc analysis:

```powershell
python src/benchmark_analysis.py
```

---

## 12. Files

- `data/synthetic/runs/benchmark_heldout/` - frozen per-world files + manifest
- `data/synthetic/benchmark_heldout.json` - aggregate
- `data/synthetic/benchmark_heldout_histories.csv` - all policy histories
- `data/synthetic/benchmark_sensitivity_500.json` - acquisition-compute check
- `data/synthetic/benchmark_cold_start_dev.json` - paired cold-start control
- `data/synthetic/benchmark_warm_start_dev.json` - warm-start development check
- `data/synthetic/benchmark_warm_start_heldout.json` - warm-start 100-109 check
- `src/benchmark_analysis.py` - post-hoc tables and CIs
- the internal benchmark protocol - pre-registration + amendments
- the internal parameter-provenance notes - parameter provenance and synthetic caveats
