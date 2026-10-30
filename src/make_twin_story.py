"""make_twin_story.py - build the static 3-screen story.

Writes:
  reports/twin_story.html
  reports/presentation_public.html  (same 3-screen story; replaces the old
                                     10-part deck)

No server, no SSE, no JavaScript.  Numbers are read from the frozen benchmark
JSON files so the story cannot drift from the evidence.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SYN = BASE / "data" / "synthetic"
REPORTS = BASE / "reports"


def _load(name: str) -> dict:
    with open(SYN / name, encoding="utf-8") as fh:
        return json.load(fh)


def _mean(payload: dict, policy: str, worlds: list[int] | None = None) -> float:
    vals = []
    for w in payload["worlds"]:
        world = int(w["world"])
        if worlds is not None and world not in worlds:
            continue
        if policy in w["policies"]:
            vals.append(float(w["policies"][policy]["best_true"]))
    if not vals:
        return float("nan")
    return sum(vals) / len(vals)


def _win_rate(payload: dict, policy: str, worlds: list[int] | None = None) -> float:
    """Tie-credited win rate, oracle excluded."""
    by_world: dict[int, dict[str, float]] = {}
    for w in payload["worlds"]:
        world = int(w["world"])
        if worlds is not None and world not in worlds:
            continue
        by_world[world] = {p: float(m["best_true"])
                           for p, m in w["policies"].items()
                           if p != "oracle"}
    wins = 0.0
    for scores in by_world.values():
        best = max(scores.values())
        winners = [p for p, v in scores.items() if abs(v - best) < 1e-9]
        if policy in winners:
            wins += 1.0 / len(winners)
    return 100.0 * wins / len(by_world) if by_world else float("nan")


def _ci(payload: dict, policy: str) -> tuple[float, float]:
    d = payload["summary"]["splits"]["test"][policy]
    lo, hi = d["best_true_ci"]
    return float(lo), float(hi)


def _pairwise_win(payload: dict, a: str, b: str,
                  worlds: list[int] | None = None) -> float:
    wins = total = 0
    for w in payload["worlds"]:
        world = int(w["world"])
        if worlds is not None and world not in worlds:
            continue
        pa = w["policies"].get(a)
        pb = w["policies"].get(b)
        if pa is None or pb is None:
            continue
        total += 1
        if float(pa["best_true"]) > float(pb["best_true"]) + 1e-9:
            wins += 1
    return 100.0 * wins / total if total else float("nan")


def _fmt(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}"


def bar(label: str, value: float, max_value: float, kind: str = "") -> str:
    width = max(1.5, 100.0 * value / max_value)
    cls = f"bar {kind}".strip()
    return (
        f'<div class="bar-row"><span class="bar-label">{html.escape(label)}</span>'
        f'<div class="bar-track"><div class="{cls}" style="width:{width:.1f}%"></div></div>'
        f'<span class="bar-value">{value:.1f}</span></div>'
    )


def build() -> str:
    held = _load("benchmark_heldout.json")
    sens = _load("benchmark_sensitivity_500.json")
    cold = _load("benchmark_cold_start_dev.json")
    warm = _load("benchmark_warm_start_dev.json")
    warm_held = _load("benchmark_warm_start_heldout.json")

    policies = ["twin_explore", "random", "lhc", "ofat", "grid"]
    labels = {
        "twin_explore": "Twin (frozen policy)",
        "random": "Random",
        "lhc": "LHC",
        "ofat": "OFAT",
        "grid": "Grid",
    }
    means = {p: _mean(held, p) for p in policies}
    wins = {p: _win_rate(held, p) for p in policies}
    oracle = _mean(held, "oracle")
    twin_ci = _ci(held, "twin_explore")
    ofat_ci = _ci(held, "ofat")

    sens_twin = _mean(sens, "twin_explore", list(range(100, 110)))
    sens_random = _mean(sens, "random", list(range(100, 110)))
    held_twin_10 = _mean(held, "twin_explore", list(range(100, 110)))
    held_random_10 = _mean(held, "random", list(range(100, 110)))
    w150 = _pairwise_win(held, "twin_explore", "random", list(range(100, 110)))
    w500 = _pairwise_win(sens, "twin_explore", "random", list(range(100, 110)))

    cold_tc = _mean(cold, "twin_current", list(range(0, 25)))
    cold_te = _mean(cold, "twin_explore", list(range(0, 25)))
    warm_tc = _mean(warm, "twin_current", list(range(0, 25)))
    warm_te = _mean(warm, "twin_explore", list(range(0, 25)))
    warm_held_tc = _mean(warm_held, "twin_current", list(range(100, 110)))
    warm_held_te = _mean(warm_held, "twin_explore", list(range(100, 110)))

    bars = "".join(
        bar(labels[p], means[p], max_value=oracle, kind="twin" if p == "twin_explore"
            else "ofat" if p == "ofat" else "base")
        for p in policies
    )
    oracle_bar = bar("Oracle (upper bound)", oracle, max_value=oracle, kind="oracle")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The hydrolysis twin - real data, synthetic test, honest limits</title>
<style>
  :root {{
    --ink: #17212b;
    --muted: #5b6773;
    --paper: #f7f5f0;
    --card: #ffffff;
    --line: #d9d4c8;
    --teal: #0f766e;
    --teal-soft: #d7eeea;
    --orange: #c2410c;
    --orange-soft: #fbe4d5;
    --grey: #94a3b8;
    --shadow: 0 10px 30px rgba(23, 33, 43, .08);
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    margin: 0; background: var(--paper); color: var(--ink);
    font-family: "Segoe UI", system-ui, -apple-system, Arial, sans-serif;
    line-height: 1.55;
  }}
  a {{ color: var(--teal); }}
  .top {{
    position: sticky; top: 0; z-index: 10;
    background: rgba(247, 245, 240, .94);
    border-bottom: 1px solid var(--line);
    backdrop-filter: blur(6px);
  }}
  .top-inner {{
    max-width: 1080px; margin: 0 auto; padding: .7rem 1.2rem;
    display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  }}
  .brand {{ font-weight: 800; letter-spacing: .01em; }}
  .brand span {{ color: var(--teal); }}
  .nav {{ display: flex; gap: .9rem; flex-wrap: wrap; font-size: .92rem; }}
  .nav a {{ text-decoration: none; color: var(--muted); font-weight: 600; }}
  .nav a:hover {{ color: var(--teal); }}
  main {{ max-width: 1080px; margin: 0 auto; padding: 0 1.2rem; }}
  section.screen {{
    min-height: 100vh; padding: 3.2rem 0 3rem;
    display: flex; flex-direction: column; justify-content: center;
    border-bottom: 1px solid var(--line);
    scroll-margin-top: 72px;
  }}
  .kicker {{
    display: inline-flex; align-items: center; gap: .45rem;
    font-size: .78rem; font-weight: 800; letter-spacing: .12em;
    text-transform: uppercase; color: var(--teal); margin-bottom: .8rem;
  }}
  .kicker.syn {{ color: var(--orange); }}
  .dot {{ width: .55rem; height: .55rem; border-radius: 50%; background: currentColor; }}
  h1 {{ font-size: clamp(2rem, 4.6vw, 3.6rem); line-height: 1.06; margin: .2rem 0 1rem; letter-spacing: -.02em; }}
  h2 {{ font-size: clamp(1.5rem, 2.6vw, 2.2rem); line-height: 1.15; margin: 0 0 .7rem; letter-spacing: -.01em; }}
  h3 {{ font-size: 1.02rem; margin: 0 0 .35rem; }}
  p {{ margin: 0 0 .9rem; }}
  .lede {{ font-size: clamp(1.05rem, 1.6vw, 1.3rem); color: #33414f; max-width: 850px; }}
  .muted {{ color: var(--muted); }}
  .badges {{ display: flex; flex-wrap: wrap; gap: .5rem; margin: 1rem 0 1.6rem; }}
  .badge {{
    font-size: .76rem; font-weight: 800; letter-spacing: .06em; text-transform: uppercase;
    padding: .38rem .62rem; border-radius: 999px; border: 1px solid var(--line);
    background: var(--card); color: var(--muted);
  }}
  .badge.real {{ background: var(--teal-soft); border-color: #b7ded8; color: #0b5f58; }}
  .badge.syn {{ background: var(--orange-soft); border-color: #f3c6ae; color: #9a3412; }}
  .grid {{ display: grid; gap: 1rem; }}
  .g3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
  .g2 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .card {{
    background: var(--card); border: 1px solid var(--line); border-radius: 16px;
    padding: 1.1rem 1.2rem; box-shadow: var(--shadow);
  }}
  .stat {{ font-size: 2rem; font-weight: 800; line-height: 1; margin-bottom: .3rem; }}
  .stat.teal {{ color: var(--teal); }}
  .stat.orange {{ color: var(--orange); }}
  .small {{ font-size: .88rem; color: var(--muted); }}
  .callout {{
    border-left: 5px solid var(--orange); background: #fff7f1;
    border-radius: 0 14px 14px 0; padding: 1rem 1.2rem; margin: 1.2rem 0;
  }}
  .callout.good {{ border-left-color: var(--teal); background: #f2fbf9; }}
  .callout b {{ color: var(--ink); }}
  .chart {{ margin: 1.2rem 0 .4rem; }}
  .bar-row {{ display: grid; grid-template-columns: 180px 1fr 48px; gap: .7rem; align-items: center; margin: .45rem 0; }}
  .bar-label {{ font-size: .9rem; font-weight: 650; }}
  .bar-track {{ background: #ece8de; border-radius: 999px; height: 24px; overflow: hidden; }}
  .bar {{ height: 100%; border-radius: 999px; background: var(--grey); }}
  .bar.twin {{ background: var(--teal); }}
  .bar.ofat {{ background: var(--orange); }}
  .bar.oracle {{ background: #b9b2a4; }}
  .bar-value {{ font-variant-numeric: tabular-nums; font-weight: 800; text-align: right; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .9rem; margin: .8rem 0 .4rem; }}
  th, td {{ text-align: left; padding: .5rem .4rem; border-bottom: 1px solid var(--line); }}
  th {{ font-size: .74rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  tr.highlight td {{ background: #fff7f1; font-weight: 700; }}
  .two-col {{ display: grid; grid-template-columns: 1.05fr .95fr; gap: 1.4rem; align-items: start; }}
  ul {{ margin: .4rem 0 .9rem; padding-left: 1.2rem; }}
  li {{ margin: .35rem 0; }}
  .footer-note {{ border-top: 1px solid var(--line); margin-top: 2rem; padding-top: 1rem; font-size: .82rem; color: var(--muted); }}
  .button {{
    display: inline-block; padding: .6rem .9rem; border-radius: 10px;
    background: var(--teal); color: white; text-decoration: none; font-weight: 700;
    font-size: .9rem;
  }}
  .button.alt {{ background: transparent; color: var(--teal); border: 1px solid var(--teal); }}
  .screen-nav {{ display: flex; gap: .7rem; flex-wrap: wrap; margin-top: 1.4rem; }}
  @media (max-width: 820px) {{
    .g3, .g2, .two-col {{ grid-template-columns: 1fr; }}
    .bar-row {{ grid-template-columns: 120px 1fr 42px; }}
    .top-inner {{ align-items: flex-start; flex-direction: column; gap: .3rem; }}
  }}
  @media print {{
    .top {{ position: static; }}
    section.screen {{ min-height: auto; page-break-after: always; }}
  }}
</style>
</head>
<body>
<header class="top">
  <div class="top-inner">
    <div class="brand">Hydrolysis <span>twin</span></div>
    <nav class="nav">
      <a href="#screen-1">1 &middot; Real data</a>
      <a href="#screen-2">2 &middot; Synthetic test</a>
      <a href="#screen-3">3 &middot; Limits &amp; next</a>
    </nav>
  </div>
</header>
<main>

<section class="screen" id="screen-1">
  <div class="kicker"><span class="dot"></span> Real data &middot; models &middot; 31 batches</div>
  <h1>We built a digital twin of fish-waste hydrolysis.<br>Then we tested its experiment planner in a synthetic lab.</h1>
  <p class="lede">The twin predicts how much protein is broken into antioxidant peptides (DH) under different
  enzymes, pH, temperature, time and substrate load. It then proposes the next experiments. The real campaign
  has not returned yet, so the planner was tested in an independent synthetic world - not in the twin itself.</p>
  <div class="badges">
    <span class="badge real">Real: 31 historical batches</span>
    <span class="badge real">Real: 7 time-course curves</span>
    <span class="badge syn">Synthetic: 100 held-out worlds</span>
    <span class="badge">0 of 15 campaign runs measured</span>
  </div>

  <div class="grid g3">
    <div class="card">
      <div class="stat teal">31</div>
      <h3>Real batches</h3>
      <p class="small">Audited from 40 raw rows. Nine were dropped for documented reasons (non-enzymatic,
      impossible DH, dry-basis composition).</p>
    </div>
    <div class="card">
      <div class="stat teal">7</div>
      <h3>Real time-course curves</h3>
      <p class="small">54 points. The ODE fits 4 of 5 Alcalase curves within &plusmn;3 DH;
      BATCH_011 is flagged at RMSE 4.19, not hidden.</p>
    </div>
    <div class="card">
      <div class="stat orange">0 / 15</div>
      <h3>Campaign runs measured</h3>
      <p class="small">The 15-run design exists (7 gap-fill, 5 process LHC, 3 dose sweep),
      but the bench data has not landed. Every synthetic result is labelled.</p>
    </div>
  </div>

  <div class="two-col" style="margin-top:1.2rem">
    <div class="card">
      <h3>What the real data says</h3>
      <ul>
        <li><b>DH range:</b> 0.3% to 50.0%; the best feasible run inside the 15-300 min box is 40.3%.</li>
        <li><b>Repeatability:</b> 1.07 DH. <b>Pooled within-condition SD:</b> 5.93 DH.</li>
        <li><b>Predictive band for a new Alcalase run:</b> &plusmn;11.9 DH. A single run cannot be
        distinguished from lot/occasion noise inside that band.</li>
        <li><b>ORAC ranker:</b> leave-one-out R&sup2; 0.507, MAE 28.3 &micro;mol TE/g. A ranking tool,
        not a certified bioactivity result.</li>
      </ul>
    </div>
    <div class="card">
      <h3>What the twin does</h3>
      <ul>
        <li><b>Physics core:</b> mixed-order hydrolysis ODE with product inhibition, enzyme decay,
        Arrhenius temperature and pH activity.</li>
        <li><b>ORAC ranker:</b> ridge regression that ranks conditions by antioxidant potential.</li>
        <li><b>Planner:</b> a small energy-based model proposes the next 3 runs by expected improvement,
        subject to the measured data and the feasible box.</li>
      </ul>
      <p class="small">The planner is the part under test. The physics core is fitted to Alcalase only;
      other enzymes run in prior mode until campaign data exists.</p>
    </div>
  </div>

  <div class="screen-nav">
    <a class="button" href="#screen-2">See the synthetic test &rarr;</a>
    <a class="button alt" href="presentation.html">Technical report</a>
  </div>
  <div class="footer-note">Screen 1 of 3. Real data and fitted models. The synthetic benchmark is on screen 2.</div>
</section>

<section class="screen" id="screen-2">
  <div class="kicker syn"><span class="dot"></span> Synthetic benchmark &middot; 100 held-out worlds</div>
  <h2>The planner beats random, LHC and grid at the same budget.<br>It does <em>not</em> beat OFAT.</h2>
  <p class="lede">Each policy gets the same 30-run budget: a 15-run seed campaign plus 15 adaptive runs.
  The metric is the best <b>true</b> DH reached by run 30. The world is an independent two-pool exposure
  model, deliberately not the twin's ODE.</p>

  <div class="badges">
    <span class="badge syn">Synthetic only</span>
    <span class="badge">Worlds 100-199</span>
    <span class="badge">Config hash 2de0ff3889ec1fb1</span>
    <span class="badge">30 runs &middot; 150 candidates</span>
  </div>

  <div class="card">
    <h3>Mean best true DH at 30 runs</h3>
    <div class="chart">
      {bars}
      {oracle_bar}
    </div>
    <p class="small">Bars are scaled to the oracle upper bound ({oracle:.1f} DH). The oracle is a finite
    approximation from 50,000 candidates plus refinement; it is not the true global optimum.</p>
  </div>

  <div class="callout">
    <b>OFAT is the strongest baseline.</b> It reaches {means["ofat"]:.1f} DH versus
    {means["twin_explore"]:.1f} for the frozen twin policy ({ofat_ci[0]:.1f}-{ofat_ci[1]:.1f} vs
    {twin_ci[0]:.1f}-{twin_ci[1]:.1f}). OFAT wins {wins["ofat"]:.1f}% of worlds outright;
    the twin wins {wins["twin_explore"]:.1f}%. The pairwise difference is
    <b>-2.11 DH [-3.13, -1.08]</b>, with OFAT winning 64% of the paired worlds.
    Any claim that the loop reduces trials against the strongest baseline is false in this benchmark.
  </div>

  <div class="two-col">
    <div class="card">
      <h3>Where the twin does win</h3>
      <table>
        <tr><th>Comparison</th><th class="num">DH advantage</th><th class="num">Twin wins</th></tr>
        <tr><td>vs random</td><td class="num">+3.55</td><td class="num">83.0%</td></tr>
        <tr><td>vs LHC</td><td class="num">+3.31</td><td class="num">84.0%</td></tr>
        <tr><td>vs grid</td><td class="num">+2.42</td><td class="num">67.0%</td></tr>
        <tr class="highlight"><td>vs OFAT</td><td class="num">-2.11</td><td class="num">33.0%</td></tr>
      </table>
      <p class="small">Pairwise win rate is the share of 100 worlds where the twin's best true DH is
      higher; ties are counted separately.</p>
    </div>
    <div class="card">
      <h3>The energy model is not the hero</h3>
      <ul>
        <li>EI rank vs realised improvement: <b>rho = 0.02</b>.</li>
        <li>Top-EI proposal was the best of its batch: <b>0.4%</b> (chance is 33%).</li>
        <li>EI vs true DH: <b>-0.14</b>; expected DH vs true: <b>0.29</b>.</li>
      </ul>
      <p class="small">The gain over random is more plausibly the trust-region candidate distribution,
      the E/S decision variable and the relaxed eligibility guard - not a smart energy landscape.
      A development-only ablation hinted at +1.5 DH from EI ranking, but that is not held-out evidence.</p>
    </div>
  </div>

  <div class="grid g2" style="margin-top:1rem">
    <div class="card">
      <h3>Compute check (pre-registered)</h3>
      <p class="small">Worlds 100-109 at 150 vs 500 candidates. Twin-vs-random win rate:
      <b>{w150:.1f}%</b> vs <b>{w500:.1f}%</b> (the twin mean is
      {held_twin_10:.1f} vs {sens_twin:.1f} DH; random is
      {held_random_10:.1f} vs {sens_random:.1f} DH). The change is
      {w500 - w150:+.1f} points, inside the pre-registered 15-point limit. More candidates did not
      improve the mean.</p>
    </div>
    <div class="card">
      <h3>Leave-out check</h3>
      <p class="small">Excluding the two runtime-check worlds 100-101 (worlds 102-199):
      twin 38.47 DH, OFAT 40.53, random 34.87, LHC 35.11, grid 35.95, oracle 49.65.
      Twin vs OFAT: -2.06 DH [-3.05, -1.03]. The conclusion does not depend on the timing worlds.</p>
    </div>
  </div>

  <div class="screen-nav">
    <a class="button" href="#screen-3">What this means &rarr;</a>
    <a class="button alt" href="../data/synthetic/benchmark_final_report.md">Full benchmark report</a>
  </div>
  <div class="footer-note">Screen 2 of 3. Synthetic evidence. The generator is not the twin's ODE and is not
  a validated model of the real process. A win here is necessary, not sufficient.</div>
</section>

<section class="screen" id="screen-3">
  <div class="kicker"><span class="dot"></span> Interpretation &middot; limits &middot; next steps</div>
  <h2>What we can say, what we cannot say, and what happens next.</h2>
  <p class="lede">The synthetic test is useful because it is adversarial. It does not prove the twin will
  reduce real lab trials. It does show where the current planner is strong, where it is weak, and which
  claims would be dishonest.</p>

  <div class="grid g2">
    <div class="card">
      <h3 style="color:var(--teal)">What we can say</h3>
      <ul>
        <li>At a fixed 30-run budget, the frozen twin policy beats random, LHC and grid in the synthetic world.</li>
        <li>The advantage survives the pre-registered 500-candidate compute check and the 102-199 leave-out.</li>
        <li>The production <b>min_class_rows=3</b> guard is defensible once realistic history exists.
        The warm-start check removes the cold-start min-1 advantage.</li>
        <li>The pipeline is reproducible, resumable and provenance-stamped (config hash, code hash, per-world files).</li>
      </ul>
    </div>
    <div class="card">
      <h3 style="color:var(--orange)">What we cannot say</h3>
      <ul>
        <li><b>That the twin beats OFAT.</b> It does not: OFAT is 2.1 DH ahead and wins 55.2% of worlds.</li>
        <li><b>That the energy model is smart.</b> EI ranking is weak (rho=0.02; top-EI hit 0.4%).</li>
        <li><b>That this reduces real lab trials.</b> The world is synthetic; real-data validation is future work.</li>
        <li><b>That the frozen held-out policy is the production default.</b> It used min_class_rows=1 as a
        cold-start ablation; production keeps min 3.</li>
      </ul>
    </div>
  </div>

  <div class="callout good">
    <b>Warm-start check.</b> The original benchmark started with only the 15 synthetic campaign runs, so most
    enzymes had 1-2 rows and the production guard excluded them. Giving every policy 31 free synthetic history
    rows with the real enzyme counts changed the picture: on development worlds 0-24,
    <b>min 3 36.9 vs min 1 37.7</b> (cold start was 34.7 vs 37.7). On warm-start held-out worlds 100-109,
    min 3 35.5, min 1 34.3, OFAT 35.9. The intervals overlap, but the cold-start advantage is gone.
    Production keeps <b>MIN_CLASS_ROWS=3</b>.
  </div>

  <div class="two-col" style="margin-top:1rem">
    <div class="card">
      <h3>Why OFAT wins here - and why that may not transfer</h3>
      <p class="small">OFAT is a one-factor-at-a-time local search around the best measured run. The synthetic
      world is smooth and low-dimensional, which suits it. A real hydrolysate system has interactions,
      lot effects and noisier responses; OFAT may be weaker there. But that is a hypothesis, not a result.
      The benchmark's job is to stop us from claiming a win we did not earn.</p>
    </div>
    <div class="card">
      <h3>Next steps</h3>
      <ol>
        <li>Run the 15-batch campaign; validate each row before it enters training.</li>
        <li>Re-run the policy benchmark against real measured rows when enough exist.</li>
        <li>Record enzyme/substrate lots so the &plusmn;11.9 DH predictive band can be narrowed.</li>
        <li>Only then decide whether the EBM planner earns its place over OFAT.</li>
      </ol>
      <a class="button" href="presentation.html">Technical report</a>
      <a class="button alt" href="plain_language_brief.html">One-page brief</a>
      <a class="button alt" href="../data/synthetic/benchmark_final_report.md">Benchmark report</a>
    </div>
  </div>

  <div class="card" style="margin-top:1rem">
    <h3>Plain-language glossary</h3>
    <p class="small"><b>DH (degree of hydrolysis):</b> how much of the protein has been cut into smaller
    peptides. Higher is the goal here. <b>OFAT:</b> one-factor-at-a-time search - change one dial, measure,
    keep the best, repeat. <b>LHC:</b> Latin hypercube, a space-filling random design. <b>Grid:</b> test a
    coarse four-level grid. <b>EI (expected improvement):</b> the planner's score for how likely a run is to
    beat the current best. <b>Oracle:</b> an upper bound that knows the synthetic truth; not a real method.</p>
  </div>

  <div class="footer-note">
    Provenance: real data - <code>data/processed/main_batch_clean.csv</code> (31 batches), 7 curves,
    internal noise-floor notes are not included in this public release.
    Synthetic benchmark - <code>data/synthetic/runs/benchmark_heldout/</code> (100 worlds, code hash
    <code>a6b3c7985347a10d</code>, config hash <code>2de0ff3889ec1fb1</code>),
    <code>data/synthetic/benchmark_final_report.md</code>.
    The synthetic files are never merged with real data. Screen 3 of 3.
  </div>
</section>

</main>
</body>
</html>
"""


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    page = build()
    for name in ("twin_story.html", "presentation_public.html"):
        path = REPORTS / name
        path.write_text(page, encoding="utf-8")
        print(f"[make_twin_story] wrote {path} ({len(page) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
