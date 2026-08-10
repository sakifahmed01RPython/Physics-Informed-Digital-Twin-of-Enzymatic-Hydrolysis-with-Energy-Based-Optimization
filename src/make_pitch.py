"""Public ("for the masses") presentation generator.

Writes reports/presentation_public.html — a self-contained, plain-language
story deck about the project for readers with no technical background.
Same base64-embedding pattern as make_report.py; the deck reuses the real
figures with simple captions and keeps the honesty framing intact.
"""

import base64
import subprocess
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
FIG_DIR = BASE / "data" / "figures"
REPORT_DIR = BASE / "reports"
REPORT = REPORT_DIR / "presentation_public.html"

JS_BEGIN = "/* ===== PITCH-JS-BEGIN ===== */"
JS_END = "/* ===== PITCH-JS-END ===== */"

CSS = """
:root{
  --teal:#0e7c86; --deep:#0d4f5c; --coral:#e07a54; --ink:#1f2d33;
  --muted:#5f7078; --line:#d7e4e4; --bg:#f6faf9; --card:#ffffff;
  --warnbg:#fdf1e8; --warnline:#f2c9a8;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;font-family:"Segoe UI",Arial,sans-serif;color:var(--ink);
  background:var(--bg);line-height:1.65;font-size:17px}
nav{position:sticky;top:0;z-index:50;background:rgba(246,250,249,.94);
  border-bottom:1px solid var(--line);padding:8px 20px;display:flex;
  flex-wrap:wrap;gap:4px 10px;backdrop-filter:blur(4px)}
nav a{color:var(--deep);text-decoration:none;font-size:13px;letter-spacing:.02em;
  padding:3px 6px;border-radius:6px}
nav a:hover{background:#e3f1f1}
.hero{background:linear-gradient(125deg,#0d4f5c 0%,#0e7c86 55%,#2aa5a0 100%);
  color:#fff;padding:64px 24px 56px;text-align:center}
.hero h1{margin:0 0 10px;font-size:42px;font-weight:700;letter-spacing:.3px}
.hero p{font-size:20px;margin:0 auto;max-width:820px;opacity:.95}
.hero .badges{margin-top:22px}
.badges span{display:inline-block;background:rgba(255,255,255,.16);
  border:1px solid rgba(255,255,255,.4);font-size:13px;padding:4px 14px;
  border-radius:20px;margin:4px}
.wrap{max-width:980px;margin:0 auto;padding:8px 24px}
section{padding:44px 0 8px;border-bottom:1px dashed var(--line)}
section:last-of-type{border-bottom:none}
h2{color:var(--deep);font-size:28px;margin:0 0 6px}
h2 .num{color:var(--coral);font-size:19px;display:block;font-weight:600;
  letter-spacing:.18em;margin-bottom:2px}
h3{color:var(--teal);font-size:19px;margin:26px 0 8px}
p{margin:10px 0}
.lead{font-size:19px;color:var(--deep)}
figure{margin:22px 0;text-align:center;background:var(--card);
  border:1px solid var(--line);border-radius:12px;padding:14px;
  box-shadow:0 3px 14px rgba(13,79,92,.07)}
figure img{max-width:100%;border-radius:8px}
figcaption{font-size:14px;color:var(--muted);margin-top:10px;line-height:1.5}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:12px;margin:24px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--teal);
  border-radius:10px;padding:14px 16px}
.kpi b{font-size:26px;color:var(--deep);display:block}
.kpi span{font-size:13.5px;color:var(--muted)}
.flow{display:flex;flex-wrap:wrap;gap:10px;align-items:stretch;margin:22px 0}
.step{background:var(--card);border:1.5px solid var(--teal);border-radius:12px;
  padding:14px 16px;flex:1;min-width:170px;font-size:15px}
.step b{color:var(--deep);display:block;margin-bottom:4px;font-size:16px}
.step .snum{color:var(--coral);font-weight:700;letter-spacing:.12em;font-size:13px}
.arrow{align-self:center;color:var(--teal);font-weight:700;font-size:20px;padding:0 2px}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:14px 18px;margin:12px 0}
.warn{background:var(--warnbg);border:1px solid var(--warnline);
  border-left:6px solid var(--coral);border-radius:10px;padding:14px 18px;margin:14px 0}
.warn b{color:#9c4a26}
.note{background:#eaf4f4;border:1px solid #bfdcdd;border-left:6px solid var(--teal);
  border-radius:10px;padding:14px 18px;margin:14px 0}
.timeline{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}
.tl{flex:1;min-width:130px;background:var(--card);border:1px solid var(--line);
  border-top:4px solid var(--teal);border-radius:8px;padding:10px 12px;font-size:14px}
.tl.now{border-top-color:var(--coral)}
.tl.later{border-top-color:#b9c8c8;color:var(--muted)}
.tl b{display:block;font-size:13px;color:var(--deep)}
.gloss{background:#eef3f3;border-radius:8px;padding:10px 14px;font-size:14.5px;
  color:var(--muted);margin:10px 0;border-left:3px solid #b9c8c8}
footer{max-width:980px;margin:30px auto;padding:20px 24px;color:var(--muted);
  font-size:13px;border-top:1px solid var(--line)}
.cta{background:linear-gradient(125deg,#0d4f5c,#0e7c86);color:#fff;border-radius:14px;
  padding:26px 28px;margin:24px 0;text-align:center}
.cta h3{margin:0 0 8px;color:#fff;font-size:22px}
.cta code{background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.35);
  border-radius:6px;padding:2px 10px;font-family:Consolas,monospace;font-size:14.5px}
.cta p{font-size:15.5px;opacity:.95;margin:8px 0 0}
.reveal{opacity:0;transform:translateY(14px);transition:opacity .7s ease,transform .7s ease}
.reveal.vis{opacity:1;transform:none}
@media (max-width:640px){.hero h1{font-size:30px}.hero p{font-size:17px}}
"""

JS = r"""
"use strict";
(function () {
  const io = new IntersectionObserver(function (entries) {
    entries.forEach(function (en) {
      if (en.isIntersecting) { en.target.classList.add("vis"); io.unobserve(en.target); }
    });
  }, { threshold: 0.12 });
  document.querySelectorAll(".reveal").forEach(function (el) { io.observe(el); });
})();
"""

SECTIONS = [
    ("problem", "The problem", """
<p class="lead">Every day, seafood processing leaves behind frames, heads and trimmings —
parts that often end up as low-value waste. But these scraps are full of a precious ingredient:
<b>protein</b>.</p>
<p>Nature gives us a tool to unlock it: <b>enzymes</b>. Enzymes are protein "scissors" that cut
large proteins into small pieces called <b>peptides</b>. Some of these peptides are
<b>antioxidants</b> — the same kind of protective compounds we look for in healthy foods.</p>
<div class="gloss"><b>In plain words:</b> if we cut fish-waste protein with the right enzyme at
the right temperature, pH and time, we can turn scraps into a valuable, health-giving
ingredient.</div>
<p>The catch: the <b>recipe matters enormously</b>. Change the enzyme, the temperature, the
acidity or the time, and the result changes completely. Finding the best recipe by trying
combinations at random in a lab is slow, expensive and wasteful in itself.</p>
<p>So we built something smarter: a <b>computer twin</b> of the process that suggests which
experiments are worth doing — and why.</p>
""", None),

    ("twin", "Core idea 1 — a digital twin", """
<p class="lead">Imagine having a perfect copy of your experiment that runs on a computer in
a split second — before you touch a single beaker.</p>
<p>That is a <b>digital twin</b>. We built one for the enzymatic reaction, using the real
chemistry: how fast the enzyme cuts protein, how temperature helps or hurts it, how acidity
changes its activity, and how the products slow the reaction down as they build up.</p>
<div class="gloss"><b>In plain words:</b> a physics-based math model that simulates the reaction
inside a computer first. The laboratory only confirms what the twin predicts.</div>
<p>When the twin is asked to simulate a historical experiment, we can compare its answer to
what actually happened in the lab. That is how we test it — and how we know it can be trusted
to predict new recipes.</p>
""", None),

    ("hybrid", "Core idea 2 — physics and data, together", """
<p class="lead">Pure chemistry rules can't capture everything about a messy real-world process.
Pure guesswork-learned statistics can't be trusted outside what it has seen. We combine both.</p>
<div class="flow">
  <div class="step"><span class="snum">PART A</span><b>Rules of chemistry</b>
  The twin always starts from how enzymes actually behave — temperature, pH, inhibition.</div>
  <div class="arrow">+</div>
  <div class="step"><span class="snum">PART B</span><b>Learning from data</b>
  Every new measurement teaches the system a little more, correcting what the rules miss.</div>
</div>
<p>This "physics-informed learning" gives us predictions that are both grounded in science and
continuously improved by evidence. A future upgrade adds a deeper learning layer — we designed
it, and it will activate once enough lab data exists (more on that in Limitations).</p>
""", None),

    ("planner", "Core idea 3 — a smart experiment planner", """
<p class="lead">The most valuable tool is the one that decides <b>which experiment to run next</b>.</p>
<p>Our planner holds a mental "map" of the whole process, built from the physics twin and every
measurement so far. On that map, promising recipes look like <b>hilltops</b> and dead ends look
like <b>valleys</b>. For each candidate experiment it asks: "How much would this teach us?"
— scientists call this <b>expected improvement</b>.</p>
<p>Then it proposes the <b>three experiments</b> most likely to move us forward: physically
sensible, never reckless, always informative.</p>
<div class="gloss"><b>In plain words:</b> like a chess player thinking several moves ahead — but
for laboratory recipes. Every result makes the next suggestion smarter. This is called
<b>active learning</b>: not more experiments, but the <b>right</b> experiments.</div>
""", None),

    ("done", "What we actually did", """
<p class="lead">The tooling is finished, tested and reproducible. Here is the honest rundown of
what exists today.</p>
<h3>1. Rescued the data</h3>
<p>We started with 40 historical laboratory records that were messy: some were impossible
values, some were non-enzyme processes, some had inconsistent units. An open audit removed
9 records we could not trust and kept <b>31 solid ones</b> — with every removal explained in
writing, no silent deletions.</p>
<figure class="reveal"><img src="__FIG_01__"><figcaption><b>Cleaning the record:</b> 40 messy
lab entries in, 31 trustworthy ones out. Nothing is hidden — each removed row is documented.</figcaption></figure>
<h3>2. Built and tested the twin</h3>
<p>The digital twin was calibrated against real reaction curves, then checked on experiments it
had never seen during training.</p>
<figure class="reveal"><img src="__FIG_02__"><figcaption><b>The twin vs. reality:</b> four of five
test runs agree within the accepted band. The one that doesn't is flagged loudly — and shown —
instead of being quietly ignored.</figcaption></figure>
<h3>3. Built an antioxidant predictor</h3>
<p>A second model estimates <b>antioxidant strength</b> (measured on the "ORAC" scale) from the
recipe and the raw material — useful for ranking candidate recipes from most to least promising.</p>
<figure class="reveal"><img src="__FIG_03__"><figcaption><b>Ranking tool, not prophecy:</b> the
predictor orders recipes well; exact numbers will improve as more data arrives.</figcaption></figure>
<h3>4. Designed 15 precise experiments</h3>
<p>We planned 15 laboratory runs in three families, each with a reason:</p>
<div class="flow">
  <div class="step"><b>Fill the gaps</b><br>Rarely-used enzymes need enough examples before the
  planner may suggest them — the plan brings them in.</div>
  <div class="arrow">·</div>
  <div class="step"><b>Explore</b><br>New process settings and new fish materials widen the map.</div>
  <div class="arrow">·</div>
  <div class="step"><b>Dose comparisons</b><br>Past records left the enzyme dose question
  unanswered — these runs answer it properly, with weighed charges.</div>
</div>
<figure class="reveal"><img src="__FIG_05__"><figcaption><b>The 15-run plan</b> spread across
enzymes, materials and process settings — every point has a reason and its own recipe sheet.</figcaption></figure>
<h3>5. Prepared the full lab kit</h3>
<p>Each of the 15 runs has its own detailed recipe sheet (weigh-outs, sampling times, checks),
plus a bench guidebook and a validated intake form so data enters cleanly. Everything derives
from one design file — drift between documents is impossible by construction.</p>
""", None),

    ("results", "Results so far", """
<div class="kpis">
  <div class="kpi"><b>31</b><span>trustworthy lab records (from 40)</span></div>
  <div class="kpi"><b>4/5</b><span>twin test runs within agreement band</span></div>
  <div class="kpi"><b>≈0.51</b><span>antioxidant ranking quality (R² — direction is right)</span></div>
  <div class="kpi"><b>15</b><span>physical experiments designed and ready</span></div>
  <div class="kpi"><b>2</b><span>AI planning rounds already logged</span></div>
</div>
<p>The AI planner's "map" and its three chosen experiments for the next round, plotted on the
real process space, look like this — peaks are spots worth trying:</p>
<figure class="reveal"><img src="__FIG_04__"><figcaption><b>The AI's map of the process.</b>
Stars are the three experiments it picked — sensible, physically sound points, including adjusted
enzyme doses.</figcaption></figure>
<figure class="reveal"><img src="__FIG_06__"><figcaption><b>Two rounds of smart planning</b> are
already recorded — each round proposes three experiments and re-learns from what came before.</figcaption></figure>
<div class="warn"><b>Honest status:</b> tools finished, science in progress. The twin, the
predictor, the planner and the campaign plan are built and verified — but the best observed
result (50% hydrolysis) is still the historical record. It will only move when the 15 physical
runs are executed.</div>
""", None),

    ("outcomes", "Why it matters", """
<div class="flow">
  <div class="step"><b>Waste becomes value</b><br>Turning seafood side-streams into antioxidant
  peptides instead of discarding them.</div>
  <div class="step"><b>Fewer experiments</b><br>Guided search replaces blind trial-and-error —
  less time, less cost, less reagent.</div>
  <div class="step"><b>Faster product development</b><br>Score recipes on-screen before touching
  a beaker.</div>
  <div class="step"><b>Portable method</b><br>The same twin approach can move to other fish, other
  enzymes, other bio-processes.</div>
  <div class="step"><b>Transparent science</b><br>Every number, every drop and every decision is
  documented and reproducible.</div>
</div>
""", None),

    ("limits", "What we honestly can't claim yet", """
<div class="warn"><b>The 15 physical runs haven't happened yet.</b> Everything here — the twin,
the predictor, the planner — is verified on historical data and design quality, but the final
proof requires the bench campaign. "Tools finished, science pending" is the motto.</div>
<div class="box"><b>The antioxidant model is a baseline.</b> It ranks recipes correctly on
average, but its exact numbers are still imprecise; we present it as a compass, not a prophecy.
Only antioxidant strength and peptide yield were measured historically — other potential health
benefits remain untested.</div>
<div class="box"><b>The historical data is lopsided.</b> One main enzyme dominates the records;
the rarer enzymes are only thinly covered, which is exactly why the campaign allocates runs to
them.</div>
<div class="box"><b>A past inconsistency forced a reset.</b> Old records had an uncontrolled
enzyme-dose variable; the new campaign's dose comparisons restore that knowledge properly.</div>
<div class="box"><b>The deep-learning upgrade is deliberately deferred.</b> It needs roughly
thirty detailed reaction curves; we have seven today, and the campaign will collect them.</div>
<div class="box"><b>This ran on a modest laptop.</b> Perfectly fine for design and proof of
concept; industrial-scale simulation would need more powerful computing.</div>
""", None),

    ("next", "What happens next", """
<div class="timeline">
  <div class="tl"><b>NOW</b>Run the 15 designed experiments at the bench, one batch at a time.</div>
  <div class="tl"><b>EACH BATCH</b>Validate the measurement, feed it to the AI, and re-plan the
  next suggestions (rounds 3, 4, 5…).</div>
  <div class="tl"><b>BIG GOAL</b>Aim for <b>value</b> — hydrolysis and antioxidant strength
  together — not just one number.</div>
  <div class="tl now"><b>~30 CURVES</b>Switch on the deep-learning hybrid layer.</div>
  <div class="tl later"><b>LATER</b>Confirmation trials, then scale the method to new materials
  and partners.</div>
</div>
<div class="cta reveal">
  <h3>Follow the campaign</h3>
  <p>Every measured batch goes into the campaign files (<code>data/campaign/</code>) and the
  pipeline re-plans the next suggestion: ODE calibration, bioactivity ranking and the
  energy-based acquisition model re-run on real numbers — no simulation, no theatre.</p>
  <p style="margin-top:14px">Refresh the analysis with <code>python -m src.make_report</code> and
  <code>python -m src.make_figures</code>; rebuild the console snapshot with
  <code>python -m src.dashboard_state</code> and <code>python -m src.make_dashboard</code>; the loop
  history lives in <code>data/campaign/active_loop_history.csv</code>.</p>
</div>
""", None),

    ("watch", "Watch the twin live", """
<p class="lead">The whole operation — the twin's belief map, the variable-correlation web, the
kinetics, model confidence and the alert queue — runs as one self-contained console. Two modes,
both honest:</p>
<div class="flow">
  <div class="step"><b>Snapshot</b><br>Just open <code>reports/dashboard.html</code> — offline,
  no server, works in any browser.</div>
  <div class="arrow">·</div>
  <div class="step"><b>Live simulation regime</b><br>Run <code>python -m src.dashboard_server</code>
  and open <code>http://127.0.0.1:8000/dashboard.html</code> — deployments arrive every few
  seconds, scouts redeploy, the alert queue fills.</div>
</div>
<div class="warn"><b>What "live" honestly means:</b> in simulation regime every arriving measurement
is synthetic — computed from the real fitted twin, not taken from a bench. The console prints the
regime on screen, nothing is ever merged into the real campaign files, and physical assay is still
required before any number counts as truth. No theatre.</div>
""", None),
]


def b64(name):
    return "data:image/png;base64," + base64.b64encode((FIG_DIR / name).read_bytes()).decode()


FIGURE_NAMES = {"__FIG_01__": "01_audit.png", "__FIG_02__": "02_ode_fit.png",
                "__FIG_03__": "03_orac.png", "__FIG_04__": "04_ebm_landscape.png",
                "__FIG_05__": "05_campaign_map.png", "__FIG_06__": "06_loop_history.png"}


def render():
    body = []
    for i, (sid, title, html, _) in enumerate(SECTIONS, 1):
        for ph, fname in FIGURE_NAMES.items():
            html = html.replace(ph, b64(fname))
        body.append(f'<section class="reveal" id="{sid}"><div class="wrap">'
                    f'<h2><span class="num">PART {i:02d}</span>{title}</h2>{html}</div></section>')
    nav_links = "".join(
        f'<a href="#{sid}">{title}</a>' for sid, title, _, _ in SECTIONS)
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>From Fish Scraps to Functional Food — explained for everyone</title>
<style>{CSS}</style></head><body>
<nav>{nav_links}</nav>
<header class="hero">
  <h1>From Fish Scraps to Functional Food</h1>
  <p>A computer "twin" of an enzyme reaction that helps food scientists rescue hidden nutrition
  from seafood waste — with fewer experiments and faster answers.</p>
  <div class="badges"><span>explained for everyone</span><span>real science, honest limits</span>
  <span>physics + machine learning</span><span>live demo inside</span></div>
</header>
{''.join(body)}
<footer>Generated {date.today().isoformat()} by <code>src/make_pitch.py</code> ·
figures embedded base64 from the real results · fully self-contained, no external assets ·
presented without jargon because understanding should not require a degree.</footer>
<script>
{JS_BEGIN}
{JS}
{JS_END}
</script>
</body></html>"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(html, encoding="utf-8")

    check = BASE / "data" / "_build_tmp" / "_pitch_check.js"
    check.parent.mkdir(parents=True, exist_ok=True)
    check.write_text(JS, encoding="utf-8")
    try:
        r = subprocess.run(["node", "--check", str(check)],
                           capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("node not available; syntax check skipped")
        return
    check.unlink(missing_ok=True)
    if r.returncode != 0:
        raise SystemExit(f"node --check failed:\n{r.stderr}")
    print(f"Public deck -> {REPORT} ({REPORT.stat().st_size // 1024} KB) · node --check OK")


if __name__ == "__main__":
    render()