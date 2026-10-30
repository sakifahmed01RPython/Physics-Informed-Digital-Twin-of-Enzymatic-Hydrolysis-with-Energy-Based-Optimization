# Synthetic policy benchmark — does the loop reduce trials?

> **This is synthetic evidence, not a real-world trial-reduction claim.**
> The generator is a plausible two-pool hydrolysis world with lot effects,
> substrate inhibition, assay noise, 5% gross errors and non-monotonic ORAC.
> It is deliberately richer than the twin. A win here is necessary, not sufficient.

> **Development run — not held-out evidence.** Use it to tune or debug; quote only a held-out run.

Generated: 2026-10-30 10:29  
Worlds: **25** (worlds 25–49); headline split: **development worlds 25–49**.  
Budget: **30 runs** (15-run seed campaign + 5 adaptive rounds × 3).  
EBM settings: epochs=120, n_aug=3, n_cand=60, Langevin=60 steps × 2 chains (EI chunk 64); oracle candidates=10,000.  
Config hash: `a43acfa05ea647a5`; git `45aecae`; failed worlds: 0.  
Runtime: 1.0 min.

## Headline — development worlds 25–49

Primary metric: **mean best true DH at the run budget**. The 95%-of-oracle and lab-precision columns are secondary.

| Policy | Mean best true DH | Mean true regret | Reached 95% of oracle | Trials to 95% (median, reached) | Selected true DH | Best measured | ORAC at selected |
|---|---:|---:|---:|---:|---:|---:|---:|
| `twin_current` | 34.3 | 15.4 | 0.0% | not reached | 30.6 | 38.8 | 404 |
| `twin_explore` | 36.4 | 13.2 | 0.0% | not reached | 31.5 | 42.7 | 395 |
| `twin_random_rank` | 34.0 | 15.7 | 0.0% | not reached | 30.7 | 37.9 | 398 |
| `random` | 35.6 | 14.1 | 4.0% | 28.0 | 32.1 | 37.9 | 399 |
| `lhc` | 33.5 | 16.1 | 0.0% | not reached | 29.6 | 35.6 | 409 |
| `ofat` | 38.6 | 11.0 | 8.0% | 28.0 | 33.6 | 43.5 | 387 |
| `grid` | 34.4 | 15.3 | 0.0% | not reached | 31.3 | 36.9 | 397 |
| `oracle` | 49.6 | 0.0 | 100.0% | 16.0 | 48.3 | 58.8 | 308 |

## Win rates (ties split)

Share of worlds where the policy had the highest best true DH; exact ties split credit equally. The oracle is excluded (it is an upper bound).

| Policy | Win rate |
|---|---:|
| `twin_current` | 5.1% |
| `twin_explore` | 9.1% |
| `twin_random_rank` | 9.1% |
| `random` | 13.1% |
| `lhc` | 5.1% |
| `ofat` | 57.1% |
| `grid` | 1.1% |

`Selected true DH` is the true DH of the run the lab would advance (highest *measured* DH). It exposes the winner's curse: a gross error can make a bad run look best. `Best measured` is what the lab believes it found.

## Target sensitivity

A single 95% threshold can censor every policy. The 80% and 90% columns show whether the ranking is an artefact of that threshold.

| Policy | Reached 80% | Trials to 80% | Reached 90% | Trials to 90% | Reached 95% | Trials to 95% |
|---|---:|---:|---:|---:|---:|---:|
| `twin_current` | 12.0% | 15.0 | 0.0% | not reached | 0.0% | not reached |
| `twin_explore` | 24.0% | 15.5 | 4.0% | 28.0 | 0.0% | not reached |
| `twin_random_rank` | 16.0% | 15.0 | 0.0% | not reached | 0.0% | not reached |
| `random` | 28.0% | 18.0 | 8.0% | 25.0 | 4.0% | 28.0 |
| `lhc` | 16.0% | 15.0 | 0.0% | not reached | 0.0% | not reached |
| `ofat` | 40.0% | 20.0 | 16.0% | 22.5 | 8.0% | 28.0 |
| `grid` | 16.0% | 15.0 | 0.0% | not reached | 0.0% | not reached |
| `oracle` | 100.0% | 16.0 | 100.0% | 16.0 | 100.0% | 16.0 |

## Lab-precision target — oracle best − 2.1 DH

2.1 DH is twice the real-replicate repeatability (1.07 DH, the internal noise-floor notes). This is the strictest target: a policy that reaches it is at the limit of what the real assay can distinguish. The synthetic assay noise is deliberately larger than the real repeatability, so low reach rates here are expected.

| Policy | Reached | Trials (median, reached) |
|---|---:|---:|
| `twin_current` | 0.0% | not reached |
| `twin_explore` | 0.0% | not reached |
| `twin_random_rank` | 0.0% | not reached |
| `random` | 4.0% | 28.0 |
| `lhc` | 0.0% | not reached |
| `ofat` | 8.0% | 28.0 |
| `grid` | 0.0% | not reached |
| `oracle` | 100.0% | 16.0 |

## Uncertainty

| Policy | Best true DH mean [95% CI] | True regret mean [95% CI] |
|---|---:|---:|
| `twin_current` | 34.3 [32.4, 36.1] | 15.4 [13.4, 17.5] |
| `twin_explore` | 36.4 [34.2, 38.9] | 13.2 [11.3, 15.1] |
| `twin_random_rank` | 34.0 [32.1, 35.9] | 15.7 [13.6, 17.8] |
| `random` | 35.6 [33.0, 38.7] | 14.1 [11.7, 16.2] |
| `lhc` | 33.5 [31.8, 35.2] | 16.1 [14.1, 18.2] |
| `ofat` | 38.6 [36.1, 41.3] | 11.0 [8.7, 13.3] |
| `grid` | 34.4 [32.6, 36.2] | 15.3 [13.4, 17.3] |
| `oracle` | 49.6 [48.4, 51.0] | 0.0 [0.0, 0.0] |

## Is EI informative?

| Policy | EI vs realised improvement (mean ρ) | Top-EI hit rate | Top-EI improved rate | EI vs true DH (pooled ρ) | Expected DH vs true DH (pooled ρ) |
|---|---:|---:|---:|---:|---:|
| `twin_current` | 0.10 | 0.4% | 0.1% | 0.01 | 0.01 |
| `twin_explore` | 0.01 | 0.4% | 0.1% | -0.11 | 0.18 |

Top-EI hit rate is the fraction of rounds where the highest-EI proposal had the highest true DH; chance with 3 proposals is 33%. A high EI that ranks low-quality runs is the 'EI rewards ignorance' pathology.

## Pairwise — development worlds 25–49

| Comparison | Mean difference (DH) | 95% CI | A wins |
|---|---:|---|---:|
| twin_current vs random | -1.31 | [-4.36, 1.00] | 56.0% |
| twin_current vs lhc | 0.78 | [-0.36, 1.85] | 60.0% |
| twin_current vs ofat | -4.34 | [-6.69, -2.11] | 20.0% |
| twin_current vs grid | -0.12 | [-1.39, 1.11] | 48.0% |
| twin_explore vs random | 0.83 | [-1.32, 2.59] | 64.0% |
| twin_explore vs lhc | 2.92 | [1.23, 4.68] | 76.0% |
| twin_current vs twin_explore | -2.14 | [-3.84, -0.76] | 24.0% |

## What this means

- Primary metric (mean best true DH at 30 runs): `twin_current` 34.3, `twin_explore` 36.4, `twin_random_rank` 34.0, `random` 35.6, `lhc` 33.5, `ofat` 38.6, `grid` 34.4, `oracle` 49.6.
- At the 30-run budget, the current EBM loop averaged **34.3% true DH**, behind random search (35.6%; difference -1.3 DH).
- It reached 95% of the oracle in **0%** of worlds vs **4%** for random and **0%** for LHC.
- The lab-facing selected run averaged **30.6%** true DH (random 32.1%), showing the cost of choosing on noisy measurements.
- The `MIN_CLASS_ROWS=1` ablation averaged **36.4%** true DH (+2.1 DH vs the production guard), isolating the eligibility filter from the rest of the acquisition.
- EI rank vs realised improvement: mean ρ = **0.10**; the top-EI proposal was the best of its batch **0%** of the time (chance 33%).
- ORAC at the selected best-DH run averaged **404** vs an oracle ORAC upper bound of about **523**. The current acquisition does not target ORAC; this gap is expected.

**In this run, the current EBM did not beat random search** (difference -1.3 DH). If this holds on the held-out split, that is the finding. The next step is to fix the acquisition — global candidates, E/S as a feature, a distance/uncertainty penalty, and a robust loss — then rerun on development and report held-out. Do not relabel this as a win.

## Method

- **World:** `src/synthetic_lab.py`, model `two_pool_exposure_v1`. Two substrate pools, enzyme exposure with first-order deactivation, substrate inhibition, enzyme-specific asymmetric pH optima, Arrhenius catalysis, lot-to-lot activity, substrate-batch susceptibility, real material compositions bootstrapped from the 31 real batches.
- **Seed design:** 15 runs with the same arm structure as the real campaign (7 gap-fill, 5 process LHC, 3 dose sweep). Every policy sees the same measured seed data, including its gross errors.
- **Oracle:** true top runs from 10,000 space-filling candidates plus local refinement. It is a finite approximation of the true global optimum.
- **Primary metric:** mean best *true* DH at the run budget (30 runs, including the 15-run seed campaign). Secondary: trials to 95% of oracle, trials to the lab-precision band, true regret, and the lab-facing selected run.
- **Regret:** oracle best true DH minus the policy's best true DH. `regret_selected` uses the run the lab would pick by measured DH.
- **Held-out split:** worlds below 100 are development; worlds 100+ are held-out. Step-5 tuning must not use the held-out half.

## Caveats (read before quoting any number)

- **Synthetic ≠ real.** The generator is a stress test, not a validated model. Parameter ranges are literature-anchored and qualitatively matched to the real data, but not fitted. See the internal parameter-provenance notes.
- **The oracle is finite.** 10,000 candidates + refinement can miss the true optimum; regret is therefore a lower bound on the true regret.
- **Noise matters.** A 5% gross-error rate and 1.5–3.5 DH occasion noise mean the highest measured run is not always the best true run. The `selected_true` column is the honest lab-facing metric.
- **Reduced EBM fidelity.** This run used epochs=120, n_aug=3, n_cand=60, Langevin=60×2. Production (`run_ebm_loop.py`) uses 800 epochs and 500 candidates. The relative ranking is the claim; the 500-candidate sensitivity check is the guard against a budget artefact.
- **Conditional on the seed design.** A different 15-run campaign could change the ranking. The world sample varies world parameters, not campaign designs.
- **Chunked runs are resumable, not pooled.** Per-world files live under `data/synthetic/runs/<prefix>/`; the config hash refuses to mix settings or code versions.

## Reproduce

```powershell
python -m src.benchmark_policy --worlds 25 --world-start 25 --budget 30 --batch 3 --epochs 120 --n-aug 3 --n-cand 60 --langevin-steps 60 --chains 2 --ei-chunk 64 --oracle-candidates 10000 --workers 2 --policies twin_explore,twin_current,twin_random_rank,random,lhc,ofat,grid,oracle --resume
```
