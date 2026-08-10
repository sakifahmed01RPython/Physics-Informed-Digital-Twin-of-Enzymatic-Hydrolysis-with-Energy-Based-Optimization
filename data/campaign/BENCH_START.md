# BENCH START — Campaign Runbook

State: **STARTED** — all tooling verified 2026-08-09. 15 batches, 3 arms.

## Where everything lives
| What | Where |
|---|---|
| Per-batch sheets (setpoints, weigh-outs, sampling) | `data/campaign/lab_sheets/CAMPAIGN_XXX.md` |
| Overview & run order | `data/campaign/lab_sheets/00_OVERVIEW.md` |
| Design (single source of truth) | `data/campaign/campaign_design.csv` |
| Measurement record (fill this) | `data/campaign/measured_runs.csv` |
| Acquisition history | `data/campaign/active_loop_history.csv` |

## Run order
1. **Dose sweep first, grouped, same enzyme+material lot**: CAMPAIGN_013 → 014 → 015 (E/S 0.01 / 0.04 / 0.06, MANDATORY enzyme weigh-outs).
2. Then any order: gap_fill 001–007, process_lhc 008–012.

## Per-batch loop (every batch)
1. Run the batch per its sheet (weigh enzyme EVERY run, record actual charge).
2. Final sample at t = Duration = the **FinalDH** value. Earlier Alcalase samples = optional but high-value time course.
3. Fill the row in `data/campaign/measured_runs.csv` (FinalDH as a NUMBER, %, wet basis — never "4:48").
4. `python src\validate_measured.py` — must print `validation OK`.
5. `python -m src.run_ebm_loop` — retrains, proposes next 3, logs round.

## Milestones
- **3 batches** (dose sweep): first real E/S variation in the model — first genuine dose-response signals.
- **10 batches**: EBM has campaign data; proposals start shifting off the 31-row priors.
- **15 batches + triplicate** of best conditions: final `python -m src.twin_predict` for confirmation.
- **Any Alcalase time courses**: drop them in for ODE recalibration when present (import from `time_course_clean.csv` pattern).

## If something looks wrong
- Validator flags something → fix the cell, rerun validator. Do NOT bypass.
- Proposal lands outside sane windows → check the round log, sanity-check lab notes, then re-run the loop.
- Anything unexplained → stop and bring it back here; do not silently merge.