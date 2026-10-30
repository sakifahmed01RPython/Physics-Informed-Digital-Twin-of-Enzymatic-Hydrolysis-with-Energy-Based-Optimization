# Synthetic policy benchmark — does the loop reduce trials?

> **This is synthetic evidence, not a real-world trial-reduction claim.**
> The generator is a plausible two-pool hydrolysis world with lot effects,
> substrate inhibition, assay noise, 5% gross errors and non-monotonic ORAC.
> It is deliberately richer than the twin. A win here is necessary, not sufficient.

> **Smoke/development run — not a benchmark result.** It checks the harness, not the policy. Quote only a run with a held-out split of at least 20 worlds.

> **Development run — not held-out evidence.** Use it to tune or debug; quote only a held-out run.

Generated: 2026-10-30 10:19  
Worlds: **12** (worlds 0–11); headline split: **all worlds 0–11 — no held-out split**.  
Budget: **30 runs** (15-run seed campaign + 5 adaptive rounds × 3).  
EBM settings: epochs=120, n_aug=3, n_cand=60, Langevin=60 steps × 2 chains (EI chunk 64); oracle candidates=10,000.  
Config hash: `d0977079c1a4eb0d`; git `45aecae`; failed worlds: 0.  
Runtime: 0.4 min.

## Headline — all worlds 0–11 — no held-out split

Primary metric: **mean best true DH at the run budget**. The 95%-of-oracle and lab-precision columns are secondary.

| Policy | Mean best true DH | Mean true regret | Reached 95% of oracle | Trials to 95% (median, reached) | Selected true DH | Best measured | ORAC at selected |
|---|---:|---:|---:|---:|---:|---:|---:|
| `twin_current` | 34.9 | 15.1 | 0.0% | not reached | 33.8 | 38.0 | 384 |
| `twin_explore` | 35.8 | 14.2 | 0.0% | not reached | 33.1 | 39.3 | 384 |
| `random` | 34.3 | 15.7 | 0.0% | not reached | 29.9 | 38.5 | 404 |
| `lhc` | 34.3 | 15.7 | 0.0% | not reached | 30.8 | 37.1 | 397 |
| `ofat` | 41.1 | 8.9 | 16.7% | 28.0 | 36.2 | 48.2 | 365 |
| `grid` | 35.1 | 14.9 | 0.0% | not reached | 31.6 | 37.2 | 389 |
| `oracle` | 50.0 | 0.0 | 100.0% | 16.0 | 49.4 | 58.0 | 291 |

## Win rates (ties split)

Share of worlds where the policy had the highest best true DH; exact ties split credit equally. The oracle is excluded (it is an upper bound).

| Policy | Win rate |
|---|---:|
| `twin_current` | 0.0% |
| `twin_explore` | 16.7% |
| `random` | 0.0% |
| `lhc` | 0.0% |
| `ofat` | 75.0% |
| `grid` | 8.3% |

`Selected true DH` is the true DH of the run the lab would advance (highest *measured* DH). It exposes the winner's curse: a gross error can make a bad run look best. `Best measured` is what the lab believes it found.

## Target sensitivity

A single 95% threshold can censor every policy. The 80% and 90% columns show whether the ranking is an artefact of that threshold.

| Policy | Reached 80% | Trials to 80% | Reached 90% | Trials to 90% | Reached 95% | Trials to 95% |
|---|---:|---:|---:|---:|---:|---:|
| `twin_current` | 0.0% | not reached | 0.0% | not reached | 0.0% | not reached |
| `twin_explore` | 16.7% | 26.0 | 0.0% | not reached | 0.0% | not reached |
| `random` | 0.0% | not reached | 0.0% | not reached | 0.0% | not reached |
| `lhc` | 0.0% | not reached | 0.0% | not reached | 0.0% | not reached |
| `ofat` | 50.0% | 20.0 | 33.3% | 21.0 | 16.7% | 28.0 |
| `grid` | 16.7% | 22.0 | 0.0% | not reached | 0.0% | not reached |
| `oracle` | 100.0% | 16.0 | 100.0% | 16.0 | 100.0% | 16.0 |

## Lab-precision target — oracle best − 2.1 DH

2.1 DH is twice the real-replicate repeatability (1.07 DH, the internal noise-floor notes). This is the strictest target: a policy that reaches it is at the limit of what the real assay can distinguish. The synthetic assay noise is deliberately larger than the real repeatability, so low reach rates here are expected.

| Policy | Reached | Trials (median, reached) |
|---|---:|---:|
| `twin_current` | 0.0% | not reached |
| `twin_explore` | 0.0% | not reached |
| `random` | 0.0% | not reached |
| `lhc` | 0.0% | not reached |
| `ofat` | 8.3% | 30.0 |
| `grid` | 0.0% | not reached |
| `oracle` | 100.0% | 16.0 |

## Uncertainty

| Policy | Best true DH mean [95% CI] | True regret mean [95% CI] |
|---|---:|---:|
| `twin_current` | 34.9 [31.8, 37.7] | 15.1 [12.9, 17.6] |
| `twin_explore` | 35.8 [32.9, 38.3] | 14.2 [11.7, 16.7] |
| `random` | 34.3 [30.9, 37.5] | 15.7 [13.7, 18.0] |
| `lhc` | 34.3 [31.1, 37.6] | 15.7 [13.5, 18.0] |
| `ofat` | 41.1 [36.7, 46.0] | 8.9 [5.6, 12.1] |
| `grid` | 35.1 [31.7, 38.1] | 14.9 [12.4, 17.8] |
| `oracle` | 50.0 [47.8, 52.4] | 0.0 [0.0, 0.0] |

## Is EI informative?

| Policy | EI vs realised improvement (mean ρ) | Top-EI hit rate | Top-EI improved rate | EI vs true DH (pooled ρ) | Expected DH vs true DH (pooled ρ) |
|---|---:|---:|---:|---:|---:|
| `twin_current` | 0.07 | 0.4% | 0.0% | -0.03 | 0.05 |
| `twin_explore` | -0.03 | 0.3% | 0.1% | -0.04 | 0.20 |

Top-EI hit rate is the fraction of rounds where the highest-EI proposal had the highest true DH; chance with 3 proposals is 33%. A high EI that ranks low-quality runs is the 'EI rewards ignorance' pathology.

## Pairwise — all worlds 0–11 — no held-out split

| Comparison | Mean difference (DH) | 95% CI | A wins |
|---|---:|---|---:|
| twin_current vs random | 0.61 | [-0.29, 1.48] | 50.0% |
| twin_current vs lhc | 0.54 | [-0.25, 1.42] | 50.0% |
| twin_current vs ofat | -6.27 | [-9.13, -3.59] | 16.7% |
| twin_current vs grid | -0.22 | [-2.08, 1.34] | 41.7% |
| twin_explore vs random | 1.54 | [0.18, 2.90] | 50.0% |
| twin_explore vs lhc | 1.47 | [0.20, 2.88] | 50.0% |
| twin_current vs twin_explore | -0.93 | [-1.57, -0.32] | 0.0% |

## What this means

- Primary metric (mean best true DH at 30 runs): `twin_current` 34.9, `twin_explore` 35.8, `random` 34.3, `lhc` 34.3, `ofat` 41.1, `grid` 35.1, `oracle` 50.0.
- At the 30-run budget, the current EBM loop averaged **34.9% true DH**, ahead of random search (34.3%; difference +0.6 DH).
- It reached 95% of the oracle in **0%** of worlds vs **0%** for random and **0%** for LHC.
- The lab-facing selected run averaged **33.8%** true DH (random 29.9%), showing the cost of choosing on noisy measurements.
- The `MIN_CLASS_ROWS=1` ablation averaged **35.8%** true DH (+0.9 DH vs the production guard), isolating the eligibility filter from the rest of the acquisition.
- EI rank vs realised improvement: mean ρ = **0.07**; the top-EI proposal was the best of its batch **0%** of the time (chance 33%).
- ORAC at the selected best-DH run averaged **384** vs an oracle ORAC upper bound of about **517**. The current acquisition does not target ORAC; this gap is expected.

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
python -m src.benchmark_policy --worlds 12 --world-start 0 --budget 30 --batch 3 --epochs 120 --n-aug 3 --n-cand 60 --langevin-steps 60 --chains 2 --ei-chunk 64 --oracle-candidates 10000 --workers 2 --policies twin_current,twin_explore,random,lhc,ofat,grid,oracle --resume
```
