# Physics-Informed Digital Twin of Enzymatic Hydrolysis with Energy-Based Optimisation

A closed-loop digital twin for enzymatic hydrolysis of fishery processing residues: physics-based kinetics (ODE), a bioactivity ranker (ORAC), and an energy-based active-learning optimizer that proposes the next experiments while a physical lab campaign runs.

In plain words: **we model how enzymes cut fish-waste protein into antioxidant peptides, and use a physics + AI loop to decide which conditions to test next in the lab.**

---

## What this project is

Fish-processing scrap (frames, trimmings, heads) is mostly protein. Enzymes can hydrolyse that protein into small peptides, some of which act as antioxidants. Two quantities matter:

- **Degree of Hydrolysis (DH)** — how much of the protein was cut (the outcome the physics core predicts).
- **ORAC** — a lab measure of antioxidant activity (the outcome the AI ranker scores).

The project combines three pieces into one loop:

1. **Physics core** — a mixed-order hydrolysis ODE (substrate -> product, competitive product inhibition, enzyme decay, Arrhenius temperature dependence, Gaussian pH activity profile, and a "cod heads" activation term) fitted to real Alcalase time-course data.
2. **ORAC ranker** — a ridge regression that ranks candidate conditions by predicted antioxidant activity (framed honestly as a ranking tool, not a prophecy).
3. **Energy-based optimizer (EBM)** — a small neural network that learns an "energy landscape" over experiment conditions and proposes new runs by *expected improvement*: the experiments most likely to beat the best DH observed so far.

A **15-run physical campaign** was designed from the model (3 arms); **0 of 15 runs have returned**, so the loop is being stress-tested in an independent synthetic lab before real campaign data exists. Each measured batch will feed back into the loop: validate -> retrain -> propose the next 3 runs. A hybrid physics + neural-network model is scaffolded and will switch on once ~30 time-course curves exist.

### The loop

```
raw lab tables (Excel)
        |
        v
data audit & preprocessing          (40 -> 31 batches, 54 time-course points)
        |
        +-----> ODE physics core    (Alcalase kinetics, fitted, 4/5 curves in tolerance)
        |
        +-----> ORAC ranker         (ridge, LOO R2 ~ 0.51)
        |
        +-----> EBM optimizer       (energy-based, expected improvement)
        |
        v
15-run campaign design  ->  lab bench sheets  ->  measured runs
        |
        +---------------------<-----------------+
        |                    validate & merge    |
        v                                       |
run_ebm_loop (retrain, propose next 3) ---------+
        |
        +-----> twin_predict (confirm/triage future batches)

[deferred] hybrid NN residual on the ODE (HYBRID_ENABLED = False until ~30 curves)
```

---

## Status (honest)

**Tooling finished. Synthetic benchmark complete. Real campaign pending.** Everything here runs end-to-end and is reproducible; the lab data has not landed yet. The in-silico benchmark is evidence about the decision policy, not about the real process.

| Item | State |
|---|---|
| Data audit & preprocessing | Done — 31 rows kept, 0 missing values |
| ODE physics core | Fitted (Alcalase), 4/5 curves within ±3 DH pts (fit band); BATCH_011 flagged (RMSE 4.19); new-run predictive band ±11.9 (noise floor) |
| ORAC ranker | LOO R² ≈ 0.51, MAE ≈ 28.3 µmol TE/g |
| EBM optimizer | Trained; re-anchored to 40.3% feasible best. The held-out synthetic benchmark shows the loop beats random/LHC/grid but **loses to OFAT**; EI ranking is weak (rho≈0.02). Production keeps the conservative `MIN_CLASS_ROWS=3` guard |
| Synthetic policy benchmark | **100-world held-out run complete** (worlds 100–199). `twin_explore` 38.4 DH vs random 34.8, LHC 35.0, grid 35.9, **OFAT 40.5**; oracle 49.6. Synthetic evidence only — see `data/synthetic/benchmark_final_report.md` |
| Acquisition-compute check | 500-candidate recheck on worlds 100–109: twin-vs-random win rate 70% vs 80% at 150 candidates (-10 points, inside the pre-registered 15-point limit); no compute artefact |
| Warm-start check | 31 free synthetic history rows remove the cold-start `min_class_rows=1` advantage (warm-start dev: min 3 36.9 vs min 1 37.7; cold-start: 34.7 vs 37.7). Production default `MIN_CLASS_ROWS=3` is defensible |
| Campaign design | 15 runs, 3 arms, quota-checked |
| Lab bench sheets | 16 sheets + measurement template + validator |
| **Measured campaign runs** | **0 of 15 returned** |
| Acquisition rounds logged | 2 (history append-only) |
| Hybrid NN | Scaffold smoke-tested; **off** by design |

Everything is regenerable with fixed seeds — reruns reproduce identical numbers.

---

## Results snapshot

### Data after audit ([full trail](data/audit_report.md))

- **31** main batch rows kept (9 dropped: 5 non-enzymatic, 2 physically impossible DH, 2 dry-basis composition in a wet-basis file).
- **7** time-course curves (54 points), truncated to declared batch duration; `FinalDH := curve @ Duration`.
- **0** missing values; FinalDH range 0.3% – 50.0%.
- **Noise floor (real replicates):** repeatability **1.07 DH**; pooled within-condition SD **5.93 DH**. Four Alcalase runs at one setpoint span 3.4–21.1% — a lot/occasion effect, not assay noise. (internal noise-floor notes are not included in this public release)
- **IC50 bioactivity columns excluded** (unit/protocol anomalies); ORAC kept.

### Models ([models/](models))

| Model | Result | Caveat |
|---|---|---|
| ODE kinetics (`ode_params_alcalase.json`) | MSE 5.240 (DH %²); 4/5 Alcalase curves within ±3 pts | BATCH_011 misses (RMSE 4.19) — flagged, not silently trusted |
| ORAC ridge (`orac_ridge.joblib`) | LOO R² 0.507, MAE 28.34 µmol TE/g at alpha=10 | Ranking tool, not a prophecy |
| EBM (`ebm_energy_net.pt`, `ebm_x_stats.npy`) | Re-anchored to 40.3% feasible best. Held-out synthetic benchmark: loop beats random/LHC/grid, loses to OFAT; EI rank vs improvement rho≈0.02. Warm-start check supports the production `MIN_CLASS_ROWS=3` guard | Proposals are starting points, not guarantees; synthetic evidence only |

### Campaign ([design](data/campaign/campaign_design.csv))

15 runs in 3 arms, all setpoints inside declared bounds:

| Arm | Runs | Purpose |
|---|---|---|
| `gap_fill` (7) | CAMPAIGN_001–007 | Raise rare enzymes to ≥3 rows (Pepsin, Flavourzyme, Alcalase combos) |
| `process_lhc` (5) | CAMPAIGN_008–012 | Alcalase process space (pH, T, time, substrate) + new materials (cod heads, herring by-product) |
| `dose_sweep` (3) | CAMPAIGN_013–015 | **Weighed enzyme** E/S 0.01 / 0.04 / 0.06 — restores dose identifiability |

### Synthetic policy benchmark ([final report](data/synthetic/benchmark_final_report.md))

100 held-out worlds (100–199), 30-run budget, synthetic `two_pool_exposure_v1`:

| Policy | Mean best true DH | Win rate |
|---|---:|---:|
| `twin_explore` (frozen) | 38.4 | 29.2% |
| `random` | 34.8 | 5.2% |
| `lhc` | 35.0 | 3.2% |
| **`ofat`** | **40.5** | **55.2%** |
| `grid` | 35.9 | 7.2% |
| `oracle` (upper bound) | 49.6 | — |

- The twin beats random (+3.55 DH, 83% of worlds), LHC (+3.31, 84%) and grid
  (+2.42, 67%). It **does not beat OFAT** (-2.11 DH; OFAT wins 55.2% of
  worlds). This is the honest headline.
- EI is weak: rank vs realised improvement rho=0.02; top-EI proposal is best
  0.4% of the time. The gain is more plausibly candidate distribution + E/S +
  eligibility than a smart energy landscape.
- 500-candidate sensitivity passes the pre-registered 15-point rule (-10
  points); more candidates did not improve the mean.
- The frozen held-out policy is a **cold-start** result. A post-hoc warm-start
  check with 31 synthetic history rows removes the `min_class_rows=1`
  advantage, so production keeps `MIN_CLASS_ROWS=3`.
- **No real-world trial-reduction claim.** Real-data validation is future work.

### Known limitation, by design

`EnzymeToSubstrateRatio` was recoded to a constant 0.02 across all historical rows (the recorded doses were inconsistent with measured kinetics — probe MSE dropped 21.99 → 0.044 after the recode). That made dose unidentifiable in the historical data; the **dose-sweep arm with mandated weighed enzyme charges** exists to restore it. Since step 5 the EBM models E/S as a decision variable, but the real dose effect is still unmeasured — any synthetic E/S advantage is a hypothesis.

---

## Quickstart

```bash
pip install -r requirements.txt
```

Run the pipeline in verification order (deterministic; `python -m` and `python src\` styles both work on Windows):

```bash
python src\preprocess_data.py        # 40 -> 31 rows, audit report, clean CSVs
python -m src.calibrate_ode          # fit Alcalase ODE kinetics
python -m src.bioactivity            # train ORAC ridge ranker
python -m src.ebm_optimizer          # train EBM + offline validation gate
python -m src.hybrid_model           # smoke test (hybrid stays off)
python -m src.campaign_design        # generate the 15-run campaign
python -m src.run_ebm_loop           # acquire next 3 + log round
python -m src.twin_predict           # DH + ORAC predictions; confirmation report
python src\lab_sheets.py             # 16 bench sheets + measured_runs.csv template
python src\validate_measured.py --allow-empty   # pre-flight (exit 0 = OK, 1 = problems, 2 = nothing measured yet)
python -m src.make_figures           # 6 PNG panels
python src\make_report.py            # technical HTML report
python src\make_twin_story.py        # static 3-screen story (real vs synthetic)
python src\make_plain_brief.py       # one-page plain-language brief (HTML + PDF + PNG)
python -m src.benchmark_policy --worlds 100 --world-start 100 --resume  # frozen held-out benchmark (long)
python src\benchmark_analysis.py     # post-hoc pairwise / sensitivity / warm-start tables
```

### Reproduce the reads

- One-page plain-language brief: `reports/plain_language_brief.html`, `.pdf`, `.png`.
- 3-screen story: open `reports/twin_story.html` in any browser (static, works on `file://`).
- Technical report: open `reports/presentation.html`.
- Benchmark evidence: [final report](data/synthetic/benchmark_final_report.md).
- Archived console/deck: `archive/` (historical; not part of the current deliverable).

### Bench loop (per batch)

1. Run the batch per its sheet (`data/campaign/lab_sheets/CAMPAIGN_XXX.md`); weigh enzyme every run.
2. Fill the row in `data/campaign/measured_runs.csv` (FinalDH as a number, %, wet basis — never Excel time format).
3. `python src\validate_measured.py` — must print `validation OK`.
4. `python -m src.run_ebm_loop` — retrains, proposes the next 3 runs, logs the round.

Intake guards (added after the step-1 audit):

- Only rows with `FinalDH_pct` filled enter training; the 14 pending template rows are ignored, never NaN-poisoned.
- Composition may be left blank: it is imputed from the material median and logged per batch.
- A half-recorded row (composition filled, FinalDH blank) fails validation — that is the corruption path.
- The validator reads raw strings, so `4:48` fails loudly instead of becoming NaN.
- Exit codes: `0` OK, `1` problems, `2` structurally valid but nothing measured yet (`--allow-empty` forces 0).

See [BENCH_START.md](data/campaign/BENCH_START.md) for run order and milestones.

---

## Repository layout

```
data/
  raw/          original Excel tables (main batch, time-course, bioactivity)
  processed/    clean CSVs after audit
  audit_report.md
  campaign/     design, bench sheets, measured runs, loop history, runbook
  figures/      6 reproducible PNGs
  synthetic/    independent benchmark worlds, frozen runs, final report (never merged with real data)
models/         ODE params, ORAC ridge, EBM weights + stats
reports/        twin_story.html, plain_language_brief.*, presentation.html (current); archive/ (historical)
archive/        archived dashboard stack and 10-part public deck
src/            all pipeline modules (see below)
requirements.txt
```

Internal `docs/` notes are not included in this public release.

### Module map (`src/`)

| Module | Role |
|---|---|
| `preprocess_data.py` | Audit + clean raw tables; writes `data/audit_report.md` |
| `ode_model.py` | Library: mixed-order hydrolysis ODE, Arrhenius + pH profiles, `dh_curve()` |
| `calibrate_ode.py` | 8-restart L-BFGS-B fit of Alcalase kinetics (log-space, seed 42) |
| `bioactivity.py` | ORAC ridge ranker, alpha sweep, leave-one-out CV |
| `ebm_optimizer.py` | EnergyNet (grid-contrastive), Langevin EI acquisition; benchmarked, EI ranking weak, production guard kept at 3 |
| `synthetic_lab.py` | Independent two-pool synthetic world (lot effects, substrate inhibition, noise, gross errors); never merged with real data |
| `benchmark_policy.py` | Seven-policy benchmark (twin, twin-explore, random, LHC, OFAT, grid, oracle); resumable held-out worlds 100–199; optional free pre-campaign history |
| `benchmark_analysis.py` | Post-hoc pairwise CIs, leave-out, 150-vs-500 sensitivity, cold-vs-warm-start tables |
| `hybrid_model.py` | Hybrid ODE + residual NN (torchdiffeq); **disabled until ~30 curves** |
| `campaign_design.py` | 15-run design: gap-fill + process LHC + dose sweep |
| `run_ebm_loop.py` | Append measured runs, retrain, acquire 3, append round history |
| `twin_predict.py` | DH + ORAC predictions; twin confirmation report |
| `lab_sheets.py` | Bench sheets + measurement template (single source of truth: design CSV) |
| `validate_measured.py` | Validator (E/S whitelist, ranges, setpoint drift, time-format traps) |
| `noise_floor.py` | Replicate variability + derived tolerance bands (real data only) |
| `simulate_campaign.py` | Dormant utility: synthetic ODE-derived campaign measurements (demo only) |
| `ingest_campaign.py` | Dormant utility: ingest measured runs into the clean dataset |
| `diagnose_activity.py` | Per-curve enzyme activity probe (the E/S recode evidence) |
| `make_figures.py` / `make_report.py` / `make_twin_story.py` / `make_plain_brief.py` | Visualizations and self-contained HTML outputs; the brief also exports PDF/PNG |
| `dashboard_state.py` / `dashboard_server.py` / `make_dashboard.py` | Archived Protein-7 console (moved to `archive/`; not part of the current deliverable) |

---

## Key design decisions

The full decision log with evidence lives in the internal session log (not included in this public release). Highlights:

- **Enzymatic hydrolysis only** — scope lock; chemical/assisted-enzymatic processes excluded.
- **9 of 40 rows dropped** with documented reasons (never silently).
- **E/S recoded to 0.02** (evidence: activity probe MSE 21.99 → 0.044); dose restored via the campaign's weighed dose-sweep arm.
- **`MIN_CLASS_ROWS = 3`** — the EBM may only propose for enzymes with ≥3 rows (rare-enzyme data scarcity). The benchmark's cold start made this guard look harmful because the synthetic seed omitted the historical rows. A post-hoc warm-start check with 31 synthetic history rows removes the `min_class_rows=1` advantage, so production keeps 3. The frozen held-out policy used 1; that is a cold-start result, not the production default.
- **Fit vs predictive tolerance bands** — ±3 DH is the interpolation band on the five calibrated curves (2.8× repeatability). A *new* Alcalase run is judged against **±11.9 DH** (2× pooled within-condition SD). Non-Alcalase runs get ±12 DH ("prior" mode). Bands are derived in the internal noise-floor notes (not included in this public release), not decreed.
- **Validator reads raw strings** (`dtype=str`) — pandas silently coerces Excel-time cells like `"4:48"` to float/NaN, the exact historical corruption mechanism.
- **Determinism everywhere** — fixed seeds make every rerun identical and every number comparable.
- **Self-contained deliverables** — HTML reports embed all assets (base64), open from `file://`, zero network.

---

## Caveats

- ORAC predictions are rankings for triage; they are **not** certified bioactivity results.
- The twin is calibrated on Alcalase only; other enzymes run in prior mode until campaign data lands.
- **The replicate spread is unexplained.** Four runs at identical Alcalase setpoints span 3.4–21.1% DH (SD 8.97) while repeatability is ~1.07 DH. Until enzyme/substrate lots are recorded, a single campaign run cannot be distinguished from lot noise; the honest predictive band is ±11.9 DH.
- BATCH_011's poor fit is flagged everywhere it appears (figures and reports) rather than hidden.
- **The benchmark is synthetic.** It does not validate the twin's ODE or predict a real campaign. The held-out result is a cold-start result; the warm-start check supports keeping the production guard, but the frozen `twin_explore` policy is not the production default. OFAT is the strongest baseline and the twin loses to it.
- The hybrid NN is a verified scaffold, intentionally off until ~30 time-course curves exist.
- Training and inference run on a laptop (CPU-only torch builds, 8 GB RAM) — this is a lab-scale tool, not a production system.

## Science roadmap

1. Run the 15-batch campaign (dose sweep first, same enzyme + material lots).
2. Per batch: fill → validate → loop (round 3+; `best_observed` will finally move off 50.0%).
3. Drop Alcalase time courses into the ODE recalibration whenever they exist.
4. At ~30 curves: flip `HYBRID_ENABLED = True`.
5. Triplicate the best conditions → `twin_predict` confirmation.
6. Re-run the policy benchmark against the real campaign once enough measured
   rows exist. The synthetic result is necessary, not sufficient: the loop
   beats random/LHC/grid but not OFAT in silico, and EI ranking is weak.
7. Later: composite DH + ORAC acquisition objective.

---

No license file is present; ask the maintainers before reusing the code or data. Data origin and audit decisions are documented in `data/audit_report.md`; the full session journal (including lessons learned) is in the internal session log (not included in this public release).