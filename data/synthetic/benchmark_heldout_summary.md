# Synthetic policy benchmark — does the loop reduce trials?

> **This is synthetic evidence, not a real-world trial-reduction claim.**
> The generator is a plausible two-pool hydrolysis world with lot effects,
> substrate inhibition, assay noise, 5% gross errors and non-monotonic ORAC.
> It is deliberately richer than the twin. A win here is necessary, not sufficient.

Generated: 2026-10-30 10:38  
Worlds: **100** (worlds 100–199); headline split: **held-out worlds 100–199**.  
Budget: **30 runs** (15-run seed campaign + 5 adaptive rounds × 3).  
EBM settings: epochs=250, n_aug=6, n_cand=150, Langevin=120 steps × 4 chains (EI chunk 64); oracle candidates=50,000.  
Config hash: `2de0ff3889ec1fb1`; code hash `a6b3c7985347a10d`; git `45aecae` at run time (committed later as `ae3c9c2`); failed worlds: 0.  
Runtime: about 4.5 min across four resumed chunks (the generated line records only the final chunk's 1.1 min). The `--history-rows` option was added after this run for the warm-start check; it does not alter the frozen per-world files.

## Headline - held-out worlds 100-199

Primary metric: **mean best true DH at the run budget**. The 95%-of-oracle and lab-precision columns are secondary.

| Policy | Mean best true DH | Mean true regret | Reached 95% of oracle | Trials to 95% (median, reached) | Selected true DH | Best measured | ORAC at selected |
|---|---:|---:|---:|---:|---:|---:|---:|
| `twin_explore` | 38.4 | 11.2 | 4.0% | 24.5 | 35.2 | 43.7 | 372 |
| `random` | 34.8 | 14.8 | 0.0% | not reached | 32.2 | 37.4 | 393 |
| `lhc` | 35.0 | 14.6 | 0.0% | not reached | 31.8 | 37.9 | 396 |
| `ofat` | 40.5 | 9.1 | 15.0% | 27.0 | 35.4 | 45.7 | 373 |
| `grid` | 35.9 | 13.7 | 1.0% | 23.0 | 32.8 | 38.6 | 392 |
| `oracle` | 49.6 | 0.0 | 100.0% | 16.0 | 49.1 | 57.7 | 302 |

## Win rates (ties split)

Share of worlds where the policy had the highest best true DH; exact ties split credit equally. The oracle is excluded (it is an upper bound).

| Policy | Win rate |
|---|---:|
| `twin_explore` | 29.2% |
| `random` | 5.2% |
| `lhc` | 3.2% |
| `ofat` | 55.2% |
| `grid` | 7.2% |

`Selected true DH` is the true DH of the run the lab would advance (highest *measured* DH). It exposes the winner's curse: a gross error can make a bad run look best. `Best measured` is what the lab believes it found.

## Target sensitivity

A single 95% threshold can censor every policy. The 80% and 90% columns show whether the ranking is an artefact of that threshold.

| Policy | Reached 80% | Trials to 80% | Reached 90% | Trials to 90% | Reached 95% | Trials to 95% |
|---|---:|---:|---:|---:|---:|---:|
| `twin_explore` | 40.0% | 20.0 | 11.0% | 23.0 | 4.0% | 24.5 |
| `random` | 12.0% | 15.0 | 2.0% | 23.0 | 0.0% | not reached |
| `lhc` | 14.0% | 15.0 | 0.0% | not reached | 0.0% | not reached |
| `ofat` | 56.0% | 18.0 | 28.0% | 21.5 | 15.0% | 27.0 |
| `grid` | 20.0% | 16.5 | 5.0% | 21.0 | 1.0% | 23.0 |
| `oracle` | 100.0% | 16.0 | 100.0% | 16.0 | 100.0% | 16.0 |

## Lab-precision target — oracle best − 2.1 DH

2.1 DH is twice the real-replicate repeatability (1.07 DH, the internal noise-floor notes). This is the strictest target: a policy that reaches it is at the limit of what the real assay can distinguish. The synthetic assay noise is deliberately larger than the real repeatability, so low reach rates here are expected.

| Policy | Reached | Trials (median, reached) |
|---|---:|---:|
| `twin_explore` | 4.0% | 24.5 |
| `random` | 0.0% | not reached |
| `lhc` | 0.0% | not reached |
| `ofat` | 14.0% | 27.0 |
| `grid` | 1.0% | 23.0 |
| `oracle` | 100.0% | 16.0 |

## Uncertainty

| Policy | Best true DH mean [95% CI] | True regret mean [95% CI] |
|---|---:|---:|
| `twin_explore` | 38.4 [37.2, 39.6] | 11.2 [10.3, 12.2] |
| `random` | 34.8 [33.9, 35.8] | 14.8 [13.9, 15.6] |
| `lhc` | 35.0 [34.1, 36.1] | 14.6 [13.7, 15.4] |
| `ofat` | 40.5 [39.2, 41.7] | 9.1 [7.9, 10.3] |
| `grid` | 35.9 [34.9, 37.0] | 13.7 [12.6, 14.6] |
| `oracle` | 49.6 [48.9, 50.3] | 0.0 [0.0, 0.0] |

## Is EI informative?

| Policy | EI vs realised improvement (mean ρ) | Top-EI hit rate | Top-EI improved rate | EI vs true DH (pooled ρ) | Expected DH vs true DH (pooled ρ) |
|---|---:|---:|---:|---:|---:|
| `twin_explore` | 0.02 | 0.4% | 0.2% | -0.14 | 0.29 |

Top-EI hit rate is the fraction of rounds where the highest-EI proposal had the highest true DH; chance with 3 proposals is 33%. A high EI that ranks low-quality runs is the 'EI rewards ignorance' pathology.

## Pairwise — held-out worlds 100–199

| Comparison | Mean difference (DH) | 95% CI | A wins |
|---|---:|---|---:|
| twin_explore vs random | 3.55 | [2.60, 4.38] | 83.0% |
| twin_explore vs lhc | 3.31 | [2.41, 4.12] | 84.0% |
| twin_explore vs grid | 2.42 | [1.41, 3.42] | 67.0% |
| twin_explore vs ofat | -2.11 | [-3.13, -1.08] | 33.0% |

**OFAT is the strongest baseline.** It is 2.1 DH ahead of the frozen twin
policy, wins 55.2% of worlds outright, and wins 64% of the pairwise world
comparisons. The twin beats random, LHC and grid; it does not beat OFAT.

## What this means

- Primary metric (mean best true DH at 30 runs): `twin_explore` 38.4, `random` 34.8, `lhc` 35.0, `ofat` 40.5, `grid` 35.9, `oracle` 49.6.

## Post-hoc checks (not pre-registered)

Full tables and caveats are in `data/synthetic/benchmark_final_report.md`.

- **Acquisition-compute sensitivity (worlds 100-109):** at 500 candidates the
  twin-vs-random win rate was 70.0% vs 80.0% at 150 candidates, a -10 point
  change inside the pre-registered 15-point limit. More candidates did not
  improve the twin mean (34.16 vs 34.48 DH). The headline is not a
  150-candidate artefact.
- **Leave-out check (worlds 102-199):** twin 38.47 DH, OFAT 40.53, random
  34.87, LHC 35.11, grid 35.95, oracle 49.65. Twin vs OFAT is -2.06 DH
  [-3.05, -1.03]. The conclusion is unchanged.
- **Cold-vs-warm-start check:** the frozen run is a cold start. Giving every
  policy 31 free synthetic history rows with the real enzyme counts raises
  `twin_current` (min 3) by 2.18 DH on development worlds and removes the
  `min_class_rows=1` advantage (warm-start twin_current 36.89 vs twin_explore
  37.66; cold-start 34.71 vs 37.73). In warm-start held-out worlds 100-109,
  twin_current 35.46, twin_explore 34.29, OFAT 35.86. The production
  `MIN_CLASS_ROWS=3` default is defensible; the held-out result is a
  cold-start result and must not be quoted as proof that the guard is harmful.
- **EI is weak even where the policy wins.** Held-out EI vs realised
  improvement is rho=0.02 and the top-EI proposal is best 0.4% of the time.
  The advantage over random is more plausibly the trust-region candidate
  distribution, the E/S decision variable and the relaxed eligibility guard
  than a smart energy landscape.

## Method

- **World:** `src/synthetic_lab.py`, model `two_pool_exposure_v1`. Two substrate pools, enzyme exposure with first-order deactivation, substrate inhibition, enzyme-specific asymmetric pH optima, Arrhenius catalysis, lot-to-lot activity, substrate-batch susceptibility, real material compositions bootstrapped from the 31 real batches.
- **Seed design:** 15 runs with the same arm structure as the real campaign (7 gap-fill, 5 process LHC, 3 dose sweep). Every policy sees the same measured seed data, including its gross errors.
- **Oracle:** true top runs from 50,000 space-filling candidates plus local refinement. It is a finite approximation of the true global optimum.
- **Primary metric:** mean best *true* DH at the run budget (30 runs, including the 15-run seed campaign). Secondary: trials to 95% of oracle, trials to the lab-precision band, true regret, and the lab-facing selected run.
- **Regret:** oracle best true DH minus the policy's best true DH. `regret_selected` uses the run the lab would pick by measured DH.
- **Held-out split:** worlds below 100 are development; worlds 100+ are held-out. Step-5 tuning must not use the held-out half.

## Caveats (read before quoting any number)

- **Synthetic ≠ real.** The generator is a stress test, not a validated model. Parameter ranges are literature-anchored and qualitatively matched to the real data, but not fitted. See the internal parameter-provenance notes.
- **The oracle is finite.** 50,000 candidates + refinement can miss the true optimum; regret is therefore a lower bound on the true regret.
- **Noise matters.** A 5% gross-error rate and 1.5–3.5 DH occasion noise mean the highest measured run is not always the best true run. The `selected_true` column is the honest lab-facing metric.
- **Reduced EBM fidelity.** This run used epochs=250, n_aug=6, n_cand=150, Langevin=120×4. Production (`run_ebm_loop.py`) uses 800 epochs and 500 candidates. The relative ranking is the claim; the 500-candidate sensitivity check is the guard against a budget artefact.
- **Conditional on the seed design.** A different 15-run campaign could change the ranking. The world sample varies world parameters, not campaign designs.
- **Chunked runs are resumable, not pooled.** Per-world files live under `data/synthetic/runs/<prefix>/`; the config hash refuses to mix settings or code versions.

## Reproduce

```powershell
python -m src.benchmark_policy --worlds 100 --world-start 100 --budget 30 --batch 3 --epochs 250 --n-aug 6 --n-cand 150 --langevin-steps 120 --chains 4 --ei-chunk 64 --oracle-candidates 50000 --workers 2 --policies twin_explore,random,lhc,ofat,grid,oracle --resume
```
