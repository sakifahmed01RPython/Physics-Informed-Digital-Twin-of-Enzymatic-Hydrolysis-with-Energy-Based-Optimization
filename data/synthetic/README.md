# `data/synthetic/` — synthetic-only artifacts

> **Everything in this directory is synthetic.**
> None of it is real lab data. None of it may be merged into
> `data/processed/`, `data/campaign/measured_runs.csv`, a golden file, or a
> report that claims real-process evidence. The only real inputs are the 31
> batches and 7 curves under `data/processed/`, used here only to bootstrap
> material compositions and to anchor a few ranges.

This directory is the sandbox for `src/synthetic_lab.py` and
`src/benchmark_policy.py`. The generator is deliberately **not** the twin's ODE:
it is a separate two-pool hydrolysis world with lot effects, substrate
inhibition, enzyme-specific pH/temperature optima, deactivation, assay noise,
5% gross errors, drift, and a hypothetical non-monotonic ORAC response. See
the internal parameter-provenance notes for every parameter's status (anchored / plausible /
arbitrary / hypothetical) and the update rules.

---

## What is here

| Path | What it is | How to read it |
|---|---|---|
| `world_000/` | One exemplar world (seed 0), generated for inspection and tests. | Not a benchmark result. It shows the schema and the qualitative checks. |
| `world_000/world.json` | Latent truth: material compositions, enzyme parameters, lot activities, noise settings, ORAC shape. | Never feed this to a policy. Only the oracle may read it. |
| `world_000/design.csv` | The 15-run seed campaign (same arm structure as the real campaign). | Conditions only; no outcomes. |
| `world_000/measured.csv` | Seed campaign with measured values **and** latent truth columns. | `FinalDH_pct` / `ORAC` are what the lab sees; `true_*` and `gross_error` are for scoring only. |
| `world_000/oracle.json` | Top true-DH conditions and oracle maxima from a finite candidate search. | An upper bound approximation, not the true global optimum. |
| `world_000/diagnostics.json` | Qualitative checks: substrate interior, temperature shift, lot gap, ORAC shape, gross-error fraction. | A generator sanity check, not evidence about the real process. |
| `benchmark_smoke.*` | 4-world, 18-run harness smoke test (tiny EBM settings). | **Not a benchmark result.** The Markdown says so. |
| `benchmark_heldout.*` | Frozen 100-world held-out run (worlds 100–199), 30-run budget. | The headline synthetic evidence. Read `benchmark_final_report.md` and the caveats. |
| `benchmark_sensitivity_500.*` | Pre-registered 10-world, 500-candidate acquisition-compute check (worlds 100–109). | A sensitivity guard, not a headline. |
| `benchmark_cold_start_dev.*` | 25-world cold-start control (worlds 0–24) for the warm-start check. | Development-only, paired control. |
| `benchmark_warm_start_dev.*` | 25-world warm-start check with 31 free synthetic history rows. | Development-only, post-hoc. |
| `benchmark_warm_start_heldout.*` | 10-world warm-start sensitivity (worlds 100–109). | Post-hoc, not the pre-registered headline. |
| `benchmark_final_report.md` | Full result tables, CIs, OFAT caveat, warm-start finding, threats to validity. | Start here. |

### `measured.csv` column contract

| Column group | Examples | Who may see it |
|---|---|---|
| Design | `BatchID`, `Enzyme`, `RawMaterial`, `pH`, `Temp_C`, `Duration_min`, `SubstrateConc_gL`, `EnzymeToSubstrateRatio`, composition | Policy and lab |
| Measured | `FinalDH_pct`, `ORAC`, `PeptideYield_pct`, `ProteinRecovery_pct`, `S0_gL`, `E0_gL` | Policy and lab |
| Campaign bookkeeping | `trial`, `arm`, `note` | Policy and lab |
| **Latent truth** | `true_DH_pct`, `true_ORAC`, `true_PeptideYield_pct`, `occasion_DH_pts`, `drift_DH_pts`, `drift_ORAC_units`, `gross_error_DH_pts`, `gross_error_ORAC_units`, `gross_error` | **Scoring only.** Never a model input. |

If a policy reads a `true_*` column, the benchmark is invalid. The only
exception is the explicit `oracle` baseline, which is an upper bound and is
labelled as such.

---

## Regenerate

From the repository root:

```powershell
# One exemplar world
python -m src.synthetic_lab --seed 0 --out data/synthetic/world_000 --n-oracle 50000

# Harness smoke test (4 worlds, 18 runs, tiny EBM settings)
python -m src.benchmark_policy --quick --prefix benchmark_smoke

# Frozen held-out run: 100 worlds, 30-run budget, 2 workers (resume chunks)
python -m src.benchmark_policy --worlds 100 --world-start 100 --workers 2 `
  --policies twin_explore,random,lhc,ofat,grid,oracle --prefix benchmark_heldout --resume

# Warm-start sensitivity: 31 free synthetic history rows
python -m src.benchmark_policy --worlds 25 --world-start 0 --workers 2 `
  --history-rows 31 --prefix benchmark_warm_start_dev
```

The full run writes `<prefix>.json`, `<prefix>_summary.md`, and
`<prefix>_histories.csv` here, plus per-world files under `runs/<prefix>/`.
It never writes outside `data/synthetic/`.

The 200 worlds are split **0–99 development** and **100–199 held-out**. Step-5
tuning must use only the development half; the headline table is the held-out
half. A development run (`--worlds 40 --world-start 0`) has no held-out worlds
and its summary is labelled as such.

---

## What a benchmark result does and does not mean

**It does mean:** the acquisition policy was compared with random search, LHC,
OFAT, a coarse grid, and an oracle inside a world that is deliberately richer
than the twin, with noise, gross errors, lot effects, and a 30-run budget. If
the loop reaches a higher best true DH across 100 held-out worlds, that is
evidence the decision policy can work under those assumptions - not proof that
it beats every baseline.

**It does not mean:** the real process will behave the same way. In particular:

- The E/S effect is **unmeasured** in the real data. Every real batch is 0.02;
  the 0.01/0.04/0.06 arms have not returned. A synthetic win that depends on
  E/S exploitation is a hypothesis, not a result.
- The ORAC-vs-DH shape is **hypothetical**. Real ORAC is weakly correlated with
  DH (Pearson 0.39) and is highest at both low and high DH, not at a clean
  intermediate peak. ORAC is a secondary diagnostic, not the primary metric.
- The synthetic kinetic parameters are not fitted to the 31 real batches. This
  is deliberate (independence), but it means the world is a stress test, not a
  calibrated replica.
- The oracle is a finite 50k-candidate search plus local refinement; true
  regret is at least as large as reported.
- The frozen twin policies see only the 15-run seed campaign, not the 31
  historical batches. The production loop sees more data. This is a cold-start
  regime; the post-hoc warm-start check adds 31 free synthetic history rows and
  shows the `min_class_rows=1` advantage disappears. Quote the cold-start
  result only with that caveat.
- **The current held-out result is not a win over the strongest baseline.**
  OFAT averages 40.5 DH vs 38.4 for the frozen twin, and wins 55.2% of worlds.
  The twin beats random/LHC/grid but loses to OFAT. Do not describe this as a
  general trial-reduction result.
- A smoke or development run is not a benchmark result. Quote only a run with a
  held-out split and the caveats attached.

If the fixed EBM loses to random search, **ship that finding**. Do not relabel
a synthetic loss as a win, and do not tune on the held-out half.

---

## Provenance

- Generator: `src/synthetic_lab.py`, model string `two_pool_exposure_v1`.
- Benchmark: `src/benchmark_policy.py`.
- Parameter status and citations: the internal parameter-provenance notes.
- Real noise floor: the internal noise-floor notes.
- The generator reads `data/processed/main_batch_clean.csv` only to bootstrap
  material compositions; it does not read real outcomes.
- Any change to the truth model must bump the model string, archive the old
  benchmark outputs, and rerun both development and held-out worlds.
