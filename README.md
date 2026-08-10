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

A **15-run physical campaign** was designed from the model (3 arms) and is now running on the bench. Each measured batch feeds back into the loop: validate -> retrain -> propose the next 3 runs. A hybrid physics + neural-network model is scaffolded and will switch on once ~30 time-course curves exist.

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

**Tooling finished. Science pending.** Everything here runs end-to-end and is reproducible; the lab data has not landed yet.

| Item | State |
|---|---|
| Data audit & preprocessing | Done — 31 rows kept, 0 missing values |
| ODE physics core | Fitted (Alcalase), 4/5 curves within ±3 DH pts; BATCH_011 flagged (RMSE 4.19) |
| ORAC ranker | LOO R² ≈ 0.51, MAE ≈ 28.3 µmol TE/g |
| EBM optimizer | Trained; offline policy gate 21/9 vs nearest-neighbour baseline |
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
- **IC50 bioactivity columns excluded** (unit/protocol anomalies); ORAC kept.

### Models ([models/](models))

| Model | Result | Caveat |
|---|---|---|
| ODE kinetics (`ode_params_alcalase.json`) | MSE 5.240 (DH %²); 4/5 Alcalase curves within ±3 pts | BATCH_011 misses (RMSE 4.19) — flagged, not silently trusted |
| ORAC ridge (`orac_ridge.joblib`) | LOO R² 0.507, MAE 28.34 µmol TE/g at alpha=10 | Ranking tool, not a prophecy |
| EBM (`ebm_energy_net.pt`, `ebm_x_stats.npy`) | Top proposals EI ≈ 2.9; offline gate beats nearest-neighbour top-3 hit-rate 21/9 (3-fold × 3 seeds) | Proposals are starting points, not guarantees |

### Campaign ([design](data/campaign/campaign_design.csv))

15 runs in 3 arms, all setpoints inside declared bounds:

| Arm | Runs | Purpose |
|---|---|---|
| `gap_fill` (7) | CAMPAIGN_001–007 | Raise rare enzymes to ≥3 rows (Pepsin, Flavourzyme, Alcalase combos) |
| `process_lhc` (5) | CAMPAIGN_008–012 | Alcalase process space (pH, T, time, substrate) + new materials (cod heads, herring by-product) |
| `dose_sweep` (3) | CAMPAIGN_013–015 | **Weighed enzyme** E/S 0.01 / 0.04 / 0.06 — restores dose identifiability |

### Known limitation, by design

`EnzymeToSubstrateRatio` was recoded to a constant 0.02 across all historical rows (the recorded doses were inconsistent with measured kinetics — probe MSE dropped 21.99 → 0.044 after the recode). That burned dose as an acquisition dimension; the **dose-sweep arm with mandated weighed enzyme charges** exists precisely to restore it.

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
python src\validate_measured.py      # validate measured runs (exit 0 = OK)
python -m src.make_figures           # 6 PNG panels
python src\make_report.py            # technical HTML report
python -m src.make_dashboard         # Protein-7 console snapshot
python -m src.make_pitch              # public plain-language deck
```

### Reproduce the reads

- Public deck: open `reports/presentation_public.html` in any browser (self-contained, works on `file://`).
- Technical report: open `reports/presentation.html`.
- Protein-7 console (snapshot): open `reports/dashboard.html`.
- Live simulation regime: `python -m src.dashboard_server` then http://127.0.0.1:8000 (synthetic ODE-derived measurements; physical assay required before any merge).

### Bench loop (per batch)

1. Run the batch per its sheet (`data/campaign/lab_sheets/CAMPAIGN_XXX.md`); weigh enzyme every run.
2. Fill the row in `data/campaign/measured_runs.csv` (FinalDH as a number, %, wet basis — never Excel time format).
3. `python src\validate_measured.py` — must print `validation OK`.
4. `python -m src.run_ebm_loop` — retrains, proposes the next 3 runs, logs the round.

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
  dashboard/    Protein-7 console state
docs/
  session_log.md  full chronological journal + decision log (read this for the story)
models/         ODE params, ORAC ridge, EBM weights + stats
reports/        dashboard.html, presentation.html, presentation_public.html
src/            all pipeline modules (see below)
requirements.txt
```

### Module map (`src/`)

| Module | Role |
|---|---|
| `preprocess_data.py` | Audit + clean raw tables; writes `data/audit_report.md` |
| `ode_model.py` | Library: mixed-order hydrolysis ODE, Arrhenius + pH profiles, `dh_curve()` |
| `calibrate_ode.py` | 8-restart L-BFGS-B fit of Alcalase kinetics (log-space, seed 42) |
| `bioactivity.py` | ORAC ridge ranker, alpha sweep, leave-one-out CV |
| `ebm_optimizer.py` | EnergyNet (grid-contrastive), Langevin EI acquisition, offline gate |
| `hybrid_model.py` | Hybrid ODE + residual NN (torchdiffeq); **disabled until ~30 curves** |
| `campaign_design.py` | 15-run design: gap-fill + process LHC + dose sweep |
| `run_ebm_loop.py` | Append measured runs, retrain, acquire 3, append round history |
| `twin_predict.py` | DH + ORAC predictions; twin confirmation report |
| `lab_sheets.py` | Bench sheets + measurement template (single source of truth: design CSV) |
| `validate_measured.py` | Validator (E/S whitelist, ranges, setpoint drift, time-format traps) |
| `simulate_campaign.py` | Dormant utility: synthetic ODE-derived campaign measurements (demo only) |
| `ingest_campaign.py` | Dormant utility: ingest measured runs into the clean dataset |
| `diagnose_activity.py` | Per-curve enzyme activity probe (the E/S recode evidence) |
| `make_figures.py` / `make_report.py` / `make_pitch.py` / `make_dashboard.py` | Visualizations & self-contained HTML outputs |
| `dashboard_state.py` / `dashboard_server.py` | Protein-7 console: state builder + optional live SSE server (stdlib only) |

---

## Key design decisions

The full decision log with evidence lives in [docs/session_log.md](docs/session_log.md). Highlights:

- **Enzymatic hydrolysis only** — scope lock; chemical/assisted-enzymatic processes excluded.
- **9 of 40 rows dropped** with documented reasons (never silently).
- **E/S recoded to 0.02** (evidence: activity probe MSE 21.99 → 0.044); dose restored via the campaign's weighed dose-sweep arm.
- **`MIN_CLASS_ROWS = 3`** — the EBM may only propose for enzymes with ≥3 rows (rare-enzyme data scarcity).
- **Prior vs fitted tolerance bands** — non-Alcalase enzymes get ±12 DH pts ("prior" mode), Alcalase gets ±3.
- **Validator reads raw strings** (`dtype=str`) — pandas silently coerces Excel-time cells like `"4:48"` to float/NaN, the exact historical corruption mechanism.
- **Determinism everywhere** — fixed seeds make every rerun identical and every number comparable.
- **Self-contained deliverables** — HTML reports embed all assets (base64), open from `file://`, zero network.

---

## Caveats

- ORAC predictions are rankings for triage; they are **not** certified bioactivity results.
- The twin is calibrated on Alcalase only; other enzymes run in prior mode until campaign data lands.
- BATCH_011's poor fit is flagged everywhere it appears (figures, dashboard) rather than hidden.
- The hybrid NN is a verified scaffold, intentionally off until ~30 time-course curves exist.
- Training and inference run on a laptop (CPU-only torch builds, 8 GB RAM) — this is a lab-scale tool, not a production system.

## Science roadmap

1. Run the 15-batch campaign (dose sweep first, same enzyme + material lots).
2. Per batch: fill → validate → loop (round 3+; `best_observed` will finally move off 50.0%).
3. Drop Alcalase time courses into the ODE recalibration whenever they exist.
4. At ~30 curves: flip `HYBRID_ENABLED = True`.
5. Triplicate the best conditions → `twin_predict` confirmation.
6. Later: composite DH + ORAC acquisition objective.

---

No license file is present; ask the maintainers before reusing the code or data. Data origin and audit decisions are documented in `data/audit_report.md`; the full session journal (including lessons learned) is in `docs/session_log.md`.