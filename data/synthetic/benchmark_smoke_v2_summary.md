# Synthetic policy benchmark — does the loop reduce trials?

> **This is synthetic evidence, not a real-world trial-reduction claim.**
> The generator is a plausible two-pool hydrolysis world with lot effects,
> substrate inhibition, assay noise, 5% gross errors and non-monotonic ORAC.
> It is deliberately richer than the twin. A win here is necessary, not sufficient.

> **Smoke/development run — not a benchmark result.** It checks the harness, not the policy. Quote only a run with a held-out split of at least 20 worlds.

> **Development run — not held-out evidence.** Use it to tune or debug; quote only a held-out run.

Generated: 2026-10-30 10:08  
Worlds: **4** (worlds 0–3); headline split: **all worlds 0–3 — no held-out split**.  
Budget: **18 runs** (15-run seed campaign + 1 adaptive round × 3).  
EBM settings: epochs=80, n_aug=4, n_cand=40, Langevin=40 steps × 2 chains (EI chunk 32); oracle candidates=2,000.  
Config hash: `5834dbb33b0cfb04`; git `45aecae`; failed worlds: 0.  
Runtime: 0.1 min.

## Headline — all worlds 0–3 — no held-out split

Primary metric: **mean best true DH at the run budget**. The 95%-of-oracle and lab-precision columns are secondary.

| Policy | Mean best true DH | Mean true regret | Reached 95% of oracle | Trials to 95% (median, reached) | Selected true DH | Best measured | ORAC at selected |
|---|---:|---:|---:|---:|---:|---:|---:|
| `twin_current` | 36.2 | 13.1 | 0.0% | not reached | 31.1 | 39.0 | 353 |
| `random` | 36.2 | 13.1 | 0.0% | not reached | 31.1 | 39.0 | 353 |
| `lhc` | 36.2 | 13.1 | 0.0% | not reached | 31.1 | 39.0 | 353 |
| `ofat` | 38.4 | 10.9 | 0.0% | not reached | 32.3 | 42.6 | 345 |
| `grid` | 36.2 | 13.1 | 0.0% | not reached | 31.1 | 39.0 | 353 |
| `oracle` | 49.3 | 0.0 | 100.0% | 16.0 | 49.0 | 52.1 | 271 |

## Win rates (ties split)

Share of worlds where the policy had the highest best true DH; exact ties split credit equally. The oracle is excluded (it is an upper bound).

| Policy | Win rate |
|---|---:|
| `twin_current` | 5.0% |
| `random` | 5.0% |
| `lhc` | 5.0% |
| `ofat` | 80.0% |
| `grid` | 5.0% |

`Selected true DH` is the true DH of the run the lab would advance (highest *measured* DH). It exposes the winner's curse: a gross error can make a bad run look best. `Best measured` is what the lab believes it found.

## Target sensitivity

A single 95% threshold can censor every policy. The 80% and 90% columns show whether the ranking is an artefact of that threshold.

| Policy | Reached 80% | Trials to 80% | Reached 90% | Trials to 90% | Reached 95% | Trials to 95% |
|---|---:|---:|---:|---:|---:|---:|
| `twin_current` | 25.0% | 15.0 | 0.0% | not reached | 0.0% | not reached |
| `random` | 25.0% | 15.0 | 0.0% | not reached | 0.0% | not reached |
| `lhc` | 25.0% | 15.0 | 0.0% | not reached | 0.0% | not reached |
| `ofat` | 50.0% | 16.5 | 0.0% | not reached | 0.0% | not reached |
| `grid` | 25.0% | 15.0 | 0.0% | not reached | 0.0% | not reached |
| `oracle` | 100.0% | 16.0 | 100.0% | 16.0 | 100.0% | 16.0 |

## Lab-precision target — oracle best − 2.1 DH

2.1 DH is twice the real-replicate repeatability (1.07 DH, the internal noise-floor notes). This is the strictest target: a policy that reaches it is at the limit of what the real assay can distinguish. The synthetic assay noise is deliberately larger than the real repeatability, so low reach rates here are expected.

| Policy | Reached | Trials (median, reached) |
|---|---:|---:|
| `twin_current` | 0.0% | not reached |
| `random` | 0.0% | not reached |
| `lhc` | 0.0% | not reached |
| `ofat` | 0.0% | not reached |
| `grid` | 0.0% | not reached |
| `oracle` | 100.0% | 16.0 |

## Uncertainty

| Policy | Best true DH mean [95% CI] | True regret mean [95% CI] |
|---|---:|---:|
| `twin_current` | 36.2 [31.2, 40.2] | 13.1 [9.6, 18.2] |
| `random` | 36.2 [31.2, 40.2] | 13.1 [9.6, 18.2] |
| `lhc` | 36.2 [31.2, 40.2] | 13.1 [9.6, 18.2] |
| `ofat` | 38.4 [35.0, 41.9] | 10.9 [8.9, 13.6] |
| `grid` | 36.2 [31.2, 40.2] | 13.1 [9.6, 18.2] |
| `oracle` | 49.3 [46.4, 51.7] | 0.0 [0.0, 0.0] |

## Is EI informative?

| Policy | EI vs realised improvement (mean ρ) | Top-EI hit rate | Top-EI improved rate | EI vs true DH (pooled ρ) | Expected DH vs true DH (pooled ρ) |
|---|---:|---:|---:|---:|---:|
| `twin_current` | 0.12 | 0.2% | 0.0% | 0.12 | 0.12 |

Top-EI hit rate is the fraction of rounds where the highest-EI proposal had the highest true DH; chance with 3 proposals is 33%. A high EI that ranks low-quality runs is the 'EI rewards ignorance' pathology.

## Pairwise — all worlds 0–3 — no held-out split

| Comparison | Mean difference (DH) | 95% CI | A wins |
|---|---:|---|---:|
| twin_current vs random | 0.00 | [0.00, 0.00] | 0.0% |
| twin_current vs lhc | 0.00 | [0.00, 0.00] | 0.0% |
| twin_current vs ofat | -2.22 | [-4.32, -0.12] | 0.0% |
| twin_current vs grid | 0.00 | [0.00, 0.00] | 0.0% |

## What this means

- Primary metric (mean best true DH at 18 runs): `twin_current` 36.2, `random` 36.2, `lhc` 36.2, `ofat` 38.4, `grid` 36.2, `oracle` 49.3.
- At the 18-run budget, the current EBM loop averaged **36.2% true DH**, tied with random search (36.2%; difference +0.0 DH).
- It reached 95% of the oracle in **0%** of worlds vs **0%** for random and **0%** for LHC.
- The lab-facing selected run averaged **31.1%** true DH (random 31.1%), showing the cost of choosing on noisy measurements.
- EI rank vs realised improvement: mean ρ = **0.12**; the top-EI proposal was the best of its batch **0%** of the time (chance 33%).
- ORAC at the selected best-DH run averaged **353** vs an oracle ORAC upper bound of about **497**. The current acquisition does not target ORAC; this gap is expected.

**In this run, the current EBM did not beat random search** (difference +0.0 DH). If this holds on the held-out split, that is the finding. The next step is to fix the acquisition — global candidates, E/S as a feature, a distance/uncertainty penalty, and a robust loss — then rerun on development and report held-out. Do not relabel this as a win.

## Method

- **World:** `src/synthetic_lab.py`, model `two_pool_exposure_v1`. Two substrate pools, enzyme exposure with first-order deactivation, substrate inhibition, enzyme-specific asymmetric pH optima, Arrhenius catalysis, lot-to-lot activity, substrate-batch susceptibility, real material compositions bootstrapped from the 31 real batches.
- **Seed design:** 15 runs with the same arm structure as the real campaign (7 gap-fill, 5 process LHC, 3 dose sweep). Every policy sees the same measured seed data, including its gross errors.
- **Oracle:** true top runs from 2,000 space-filling candidates plus local refinement. It is a finite approximation of the true global optimum.
- **Primary metric:** mean best *true* DH at the run budget (18 runs, including the 15-run seed campaign). Secondary: trials to 95% of oracle, trials to the lab-precision band, true regret, and the lab-facing selected run.
- **Regret:** oracle best true DH minus the policy's best true DH. `regret_selected` uses the run the lab would pick by measured DH.
- **Held-out split:** worlds below 100 are development; worlds 100+ are held-out. Step-5 tuning must not use the held-out half.

## Caveats (read before quoting any number)

- **Synthetic ≠ real.** The generator is a stress test, not a validated model. Parameter ranges are literature-anchored and qualitatively matched to the real data, but not fitted. See the internal parameter-provenance notes.
- **The oracle is finite.** 2,000 candidates + refinement can miss the true optimum; regret is therefore a lower bound on the true regret.
- **Noise matters.** A 5% gross-error rate and 1.5–3.5 DH occasion noise mean the highest measured run is not always the best true run. The `selected_true` column is the honest lab-facing metric.
- **Reduced EBM fidelity.** This run used epochs=80, n_aug=4, n_cand=40, Langevin=40×2. Production (`run_ebm_loop.py`) uses 800 epochs and 500 candidates. The relative ranking is the claim; the 500-candidate sensitivity check is the guard against a budget artefact.
- **Conditional on the seed design.** A different 15-run campaign could change the ranking. The world sample varies world parameters, not campaign designs.
- **Chunked runs are resumable, not pooled.** Per-world files live under `data/synthetic/runs/<prefix>/`; the config hash refuses to mix settings or code versions.

## Reproduce

```powershell
python -m src.benchmark_policy --worlds 4 --world-start 0 --budget 18 --batch 3 --epochs 80 --n-aug 4 --n-cand 40 --langevin-steps 40 --chains 2 --ei-chunk 32 --oracle-candidates 2000 --workers 1 --policies twin_current,random,lhc,ofat,grid,oracle --resume
```
