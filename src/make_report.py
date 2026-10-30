import base64
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
FIG_DIR = BASE / "data" / "figures"
REPORT_DIR = BASE / "reports"
REPORT = REPORT_DIR / "presentation.html"

CSS = """
:root { --ink:#1d2733; --muted:#5c6b78; --accent:#1f6f8b; --warm:#d9402f; --line:#dbe4ea; --bg:#f7f9fb; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", Arial, sans-serif; color: var(--ink); background: var(--bg); margin: 0; line-height: 1.55; }
header { background: linear-gradient(120deg, #10233a, #1f6f8b 70%, #2ea8a0); color: #fff; padding: 40px 32px 32px; }
header h1 { margin: 0; font-size: 30px; font-weight: 600; letter-spacing: .3px; }
header p { margin: 8px 0 0; opacity: .92; max-width: 900px; }
section { max-width: 1080px; margin: 0 auto; padding: 26px 24px 8px; }
h2 { color: var(--accent); border-bottom: 2px solid var(--line); padding-bottom: 6px; margin-top: 34px; font-size: 21px; }
h3 { font-size: 16px; margin: 18px 0 6px; }
figure { margin: 14px 0 22px; text-align: center; }
figure img { max-width: 100%; border: 1px solid var(--line); border-radius: 8px; background: #fff; box-shadow: 0 2px 10px rgba(16,35,58,.08); }
figcaption { font-size: 12.5px; color: var(--muted); margin-top: 6px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 16px 0; }
.kpi { background: #fff; border: 1px solid var(--line); border-left: 4px solid var(--accent); border-radius: 8px; padding: 12px 14px; }
.kpi b { font-size: 22px; display: block; color: var(--ink); }
.kpi span { font-size: 12px; color: var(--muted); }
.flow { display: flex; flex-wrap: wrap; align-items: stretch; gap: 8px; margin: 18px 0; }
.box { background: #fff; border: 1.5px solid var(--accent); border-radius: 8px; padding: 10px 14px; min-width: 150px; font-size: 13px; }
.box.dim { border-color: var(--line); color: var(--muted); background: #eef2f6; }
.box.off { border-style: dashed; border-color: #c8a13a; color: #8a6d1a; }
.arrow { align-self: center; color: var(--accent); font-weight: 700; padding: 0 2px; }
.warn { background: #fdf3e7; border: 1px solid #e7c98f; border-left: 5px solid #d9972a; border-radius: 8px; padding: 12px 16px; font-size: 13.5px; margin: 14px 0; }
.note { background: #eef6fa; border: 1px solid #bfd9e6; border-left: 5px solid var(--accent); border-radius: 8px; padding: 12px 16px; font-size: 13.5px; margin: 14px 0; }
ul { padding-left: 22px; }
code { font-family: Consolas, monospace; background: #eef2f6; padding: 1px 6px; border-radius: 4px; font-size: 12.5px; }
footer { max-width: 1080px; margin: 26px auto 40px; padding: 16px 24px; color: var(--muted); font-size: 12px; border-top: 1px solid var(--line); }
.tag { display: inline-block; background: #1f6f8b; color: #fff; font-size: 11px; padding: 2px 10px; border-radius: 12px; margin-right: 6px; }
"""

ARCH = """
<div class="flow">
  <div class="box"><b>Raw lab data</b><br>40 rows raw \u2192 audited &amp; rescued<br><code>preprocess_data.py</code></div>
  <div class="arrow">\u2192</div>
  <div class="box"><b>Mechanistic core</b><br>mixed-order ODE twin<br>S\u2192P, inhibition, T/pH kinetics<br><code>ode_model.py</code></div>
  <div class="arrow">\u2192</div>
  <div class="box"><b>Energy-based model</b><br>learned energy landscape<br>interior-Langevin EI acquisition<br><code>ebm_optimizer.py</code></div>
  <div class="arrow">\u2192</div>
  <div class="box"><b>Acquisition loop</b><br>3 experiments / round<br>validated intake<br><code>run_ebm_loop.py</code></div>
  <div class="arrow">\u2192</div>
  <div class="box"><b>15-run physical campaign</b><br>gap-fill + LHC + dose sweep<br>25 lab sheets &amp; runbook</div>
  <div class="arrow">\u2192</div>
  <div class="box off"><b>Hybrid residual NN</b><br>deferred until ~30 curves<br><code>HYBRID_ENABLED=False</code></div>
</div>
<div class="flow">
  <div class="box dim"><b>ORAC bioactivity</b><br>ridge, LOO R\u00b2=0.507<br><code>bioactivity.py</code></div>
  <div class="arrow">\u2190</div>
  <div class="box dim"><b>Twin verdicts</b><br>prior vs fitted bands<br><code>twin_predict.py</code></div>
</div>
"""

SECTIONS = [
    ("What this project is", """
<p>A <b>physics-informed digital twin of enzymatic hydrolysis</b>: a mechanistic ODE core drives a learned
energy-based model, which steers a physical experiment campaign through an active-learning loop. Every number
in this report is reproducible from <code>data/</code> and <code>models/</code> by running
<code>python -m src.make_figures</code>.</p>
""", ARCH),
    ("01 \u2014 Data rescue: 40 rows \u2192 31 usable", """
<p>The raw tables were hostile: Excel time-format cells, impossible DH values (up to 97.7%), non-enzymatic rows,
and dry-basis composition rows in a wet-basis file. The audit removed 9 rows with a written trail
(<code>data/audit_report.md</code>) and kept 0 NaNs. E/S was locked to a constant 0.02 \u2014 that fact drove the
dose-sweep arm of the campaign.</p>
""", "01_audit.png"),
    ("02 \u2014 The physics core: ODE twin calibrated", """
<p>The mixed-order hydrolysis ODE (S \u2192 P with competitive product inhibition, Arrhenius temperature
dependence, Gaussian pH activity, plus a substrate-heads activation term) was fitted to all five Alcalase time
courses. 4 of 5 curves land inside the &plusmn;3 DH-pt tolerance; BATCH_011 (RMSE 4.19) is flagged rather than
silently trusted.</p>
""", "02_ode_fit.png"),
    ("03 \u2014 Bioactivity: ORAC ridge baseline", """
<p>A composition+process ridge predicts antioxidant capacity in leave-one-out (R\u00b2 = 0.507, MAE 28.3). It is a
ranking tool, not a prophecy \u2014 the composite DH+ORAC objective is the next step, not this one.</p>
""", "03_orac.png"),
    ("04 \u2014 Active learning: energy-based acquisition", """
<p>The EBM learns an energy landscape over (process \u00d7 composition \u00d7 enzyme). Expected improvement is
computed by interior-anchored Langevin sampling over the energy. The star markers are the three acquired
experiments \u2014 physically sensible, high-EI points (e.g. E/S doses on Alcalase).</p>
""", "04_ebm_landscape.png"),
    ("05 \u2014 The campaign: 15 runs, 3 arms", """
<p><b>gap_fill</b> (7) brings rare enzymes to n\u22653 so the EBM may acquire over them; <b>process_lhc</b> (5)
explores the Alcalase process box and new materials; <b>dose_sweep</b> (3) restores the E/S identifiability that
the constant-0.02 history destroyed. Per-batch lab sheets and a runbook were generated from the design.</p>
""", "05_campaign_map.png"),
    ("06 \u2014 The loop so far", """
<p>Two acquisition rounds are logged (3 proposals each). Best observed DH is pinned at the historical 50.0% \u2014
it will move only when campaign measurements land. Each batch enters via a validated template, then the loop
retrains on all rows.</p>
""", "06_loop_history.png"),
    ("Honest status", """
<div class="warn"><b>What is done:</b> audit \u00b7 ODE calibration (4/5 in tolerance) \u00b7 ORAC baseline \u00b7 EBM \u00b7 campaign design + sheets \u00b7 intake validation \u00b7 100-world synthetic policy benchmark \u00b7 end-to-end verified.</div>
<div class="note"><b>What is NOT done (honestly):</b> the 15 physical batches are pending \u2014 the EBM has only 31
historical rows; the synthetic benchmark beats random/LHC/grid but <b>loses to OFAT</b>, and EI ranking is weak;
ORAC R\u00b2 0.507 is a baseline, not a conclusion; the hybrid residual NN is deferred by design
until enough curves exist; composite DH+ORAC acquisition is queued behind the DH-only loop. Tools finished,
real-data validation pending.</div>
""", None),
]


def b64(name):
    return "data:image/png;base64," + base64.b64encode((FIG_DIR / name).read_bytes()).decode()


def render():
    body = []
    for title, text, fig in SECTIONS:
        body.append(f"<h2>{title}</h2>")
        body.append(text)
        if fig and fig.lstrip().startswith("<div"):
            body.append(fig)
        elif fig:
            body.append(f"<figure><img src='{b64(fig)}'><figcaption>{fig}</figcaption></figure>")
    kpis = """
<div class="kpis">
  <div class="kpi"><b>31</b><span>usable batches (from 40)</span></div>
  <div class="kpi"><b>7</b><span>time-course curves, 54 points</span></div>
  <div class="kpi"><b>4/5</b><span>ODE curves in tolerance</span></div>
  <div class="kpi"><b>0.507</b><span>LOO R\u00b2 ORAC ridge</span></div>
  <div class="kpi"><b>15</b><span>campaign runs designed</span></div>
  <div class="kpi"><b>2</b><span>acquisition rounds logged</span></div>
</div>"""
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Physics-Informed Digital Twin of Enzymatic Hydrolysis \u2014 Presentation</title>
<style>{CSS}</style></head><body>
<header>
  <h1>Physics-Informed Digital Twin of Enzymatic Hydrolysis</h1>
  <p>with energy-based optimisation \u2014 pipeline build report &amp; visualisation
  <span class="tag">phase 0\u20135 tooling complete</span><span class="tag">campaign pending</span></p>
</header>
{kpis}
<section>{''.join(body)}</section>
<footer>Generated {__import__('datetime').date.today().isoformat()} by <code>src/make_report.py</code> \u00b7 data/figures/*.png embedded base64 \u00b7 fully self-contained, no external assets.</footer>
</body></html>"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(html, encoding="utf-8")
    print(f"Report: {REPORT} ({REPORT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    render()