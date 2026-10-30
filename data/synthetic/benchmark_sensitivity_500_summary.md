# Synthetic policy benchmark — does the loop reduce trials?

> **This is synthetic evidence, not a real-world trial-reduction claim.**
> The generator is a plausible two-pool hydrolysis world with lot effects,
> substrate inhibition, assay noise, 5% gross errors and non-monotonic ORAC.
> It is deliberately richer than the twin. A win here is necessary, not sufficient.

> **Smoke/development run — not a benchmark result.** It checks the harness, not the policy. Quote only a run with a held-out split of at least 20 worlds.

> **Development run — not held-out evidence.** Use it to tune or debug; quote only a held-out run.

> **This file is the pre-registered 10-world acquisition-compute sensitivity**, paired against the
> frozen 150-candidate held-out run on the same worlds. It is not a headline result.

Generated: 2026-10-30 10:42  
Worlds: **10** (worlds 100–109); headline split: **all worlds 100–109 — no held-out split**.  
Budget: **30 runs** (15-run seed campaign + 5 adaptive rounds × 3).  
EBM settings: epochs=250, n_aug=6, n_cand=500, Langevin=120 steps × 4 chains (EI chunk 64); oracle candidates=50,000.  
Config hash: `97952c8112b19315`; git `ae3c9c2`; failed worlds: 0.  
Runtime: 0.6 min.

## Headline — all worlds 100–109 — no held-out split

Primary metric: **mean best true DH at the run budget**. The 95%-of-oracle and lab-precision columns are secondary.

| Policy | Mean best true DH | Mean true regret | Reached 95% of oracle | Trials to 95% (median, reached) | Selected true DH | Best measured | ORAC at selected |
|---|---:|---:|---:|---:|---:|---:|---:|
| `twin_explore` | 34.2 | 14.2 | 0.0% | not reached | 30.5 | 42.5 | 384 |
| `random` | 32.6 | 15.8 | 0.0% | not reached | 27.4 | 35.5 | 421 |
| `lhc` | 31.7 | 16.7 | 0.0% | not reached | 25.4 | 35.9 | 438 |
| `ofat` | 35.9 | 12.5 | 20.0% | 27.0 | 29.3 | 45.2 | 413 |
| `grid` | 33.8 | 14.6 | 0.0% | not reached | 29.5 | 36.7 | 409 |
| `oracle` | 48.4 | 0.0 | 100.0% | 16.0 | 47.9 | 54.1 | 303 |

## Win rates (ties split)

Share of worlds where the policy had the highest best true DH; exact ties split credit equally. The oracle is excluded (it is an upper bound).

| Policy | Win rate |
|---|---:|
| `twin_explore` | 22.0% |
| `random` | 12.0% |
| `lhc` | 2.0% |
| `ofat` | 52.0% |
| `grid` | 12.0% |

`Selected true DH` is the true DH of the run the lab would advance (highest *measured* DH). It exposes the winner's curse: a gross error can make a bad run look best. `Best measured` is what the lab believes it found.

## Target sensitivity

A single 95% threshold can censor every policy. The 80% and 90% columns show whether the ranking is an artefact of that threshold.

| Policy | Reached 80% | Trials to 80% | Reached 90% | Trials to 90% | Reached 95% | Trials to 95% |
|---|---:|---:|---:|---:|---:|---:|
| `twin_explore` | 10.0% | 29.0 | 0.0% | not reached | 0.0% | not reached |
| `random` | 0.0% | not reached | 0.0% | not reached | 0.0% | not reached |
| `lhc` | 0.0% | not reached | 0.0% | not reached | 0.0% | not reached |
| `ofat` | 40.0% | 19.0 | 20.0% | 27.0 | 20.0% | 27.0 |
| `grid` | 30.0% | 19.0 | 10.0% | 23.0 | 0.0% | not reached |
| `oracle` | 100.0% | 16.0 | 100.0% | 16.0 | 100.0% | 16.0 |

## Lab-precision target — oracle best − 2.1 DH

2.1 DH is twice the real-replicate repeatability (1.07 DH, the internal noise-floor notes). This is the strictest target: a policy that reaches it is at the limit of what the real assay can distinguish. The synthetic assay noise is deliberately larger than the real repeatability, so low reach rates here are expected.

| Policy | Reached | Trials (median, reached) |
|---|---:|---:|
| `twin_explore` | 0.0% | not reached |
| `random` | 0.0% | not reached |
| `lhc` | 0.0% | not reached |
| `ofat` | 20.0% | 27.0 |
| `grid` | 0.0% | not reached |
| `oracle` | 100.0% | 16.0 |

## Uncertainty

| Policy | Best true DH mean [95% CI] | True regret mean [95% CI] |
|---|---:|---:|
| `twin_explore` | 34.2 [32.3, 36.2] | 14.2 [11.8, 16.7] |
| `random` | 32.6 [29.6, 35.6] | 15.8 [13.0, 18.9] |
| `lhc` | 31.7 [29.2, 34.3] | 16.7 [13.7, 19.6] |
| `ofat` | 35.9 [31.3, 41.0] | 12.5 [7.7, 17.1] |
| `grid` | 33.8 [30.0, 37.8] | 14.6 [10.6, 18.5] |
| `oracle` | 48.4 [46.4, 50.2] | 0.0 [0.0, 0.0] |

## Is EI informative?

| Policy | EI vs realised improvement (mean ρ) | Top-EI hit rate | Top-EI improved rate | EI vs true DH (pooled ρ) | Expected DH vs true DH (pooled ρ) |
|---|---:|---:|---:|---:|---:|
| `twin_explore` | -0.08 | 0.4% | 0.1% | -0.10 | 0.32 |

Top-EI hit rate is the fraction of rounds where the highest-EI proposal had the highest true DH; chance with 3 proposals is 33%. A high EI that ranks low-quality runs is the 'EI rewards ignorance' pathology.

## Pairwise — all worlds 100–109 — no held-out split

| Comparison | Mean difference (DH) | 95% CI | A wins |
|---|---:|---|---:|
| twin_explore vs random | 1.56 | [-0.73, 4.06] | 70.0% |
| twin_explore vs lhc | 2.48 | [0.76, 4.46] | 80.0% |

## What this means

- Primary metric (mean best true DH at 30 runs): `twin_explore` 34.2, `random` 32.6, `lhc` 31.7, `ofat` 35.9, `grid` 33.8, `oracle` 48.4.

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
- **Reduced EBM fidelity.** This run used epochs=250, n_aug=6, n_cand=500, Langevin=120×4. Production (`run_ebm_loop.py`) uses 800 epochs and 500 candidates. The relative ranking is the claim; the 500-candidate sensitivity check is the guard against a budget artefact.
- **Conditional on the seed design.** A different 15-run campaign could change the ranking. The world sample varies world parameters, not campaign designs.
- **Chunked runs are resumable, not pooled.** Per-world files live under `data/synthetic/runs/<prefix>/`; the config hash refuses to mix settings or code versions.

## Reproduce

```powershell
python -m src.benchmark_policy --worlds 10 --world-start 100 --budget 30 --batch 3 --epochs 250 --n-aug 6 --n-cand 500 --langevin-steps 120 --chains 4 --ei-chunk 64 --oracle-candidates 50000 --workers 2 --policies twin_explore,random,lhc,ofat,grid,oracle --resume
```
