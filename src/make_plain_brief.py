"""make_plain_brief.py - one-page plain-language brief (HTML, PDF, PNG).

The brief is designed for A4 landscape and for readers outside the field.
It uses the frozen benchmark JSON so the numbers cannot drift.

Run:
    python src/make_plain_brief.py
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
SYN = BASE / "data" / "synthetic"
REPORTS = BASE / "reports"
HTML_PATH = REPORTS / "plain_language_brief.html"
PDF_PATH = REPORTS / "plain_language_brief.pdf"
PNG_PATH = REPORTS / "plain_language_brief.png"


def _load(name: str) -> dict:
    with open(SYN / name, encoding="utf-8") as fh:
        return json.load(fh)


def _mean(payload: dict, policy: str) -> float:
    vals = [float(w["policies"][policy]["best_true"])
            for w in payload["worlds"] if policy in w["policies"]]
    return sum(vals) / len(vals)


def _win_rate(payload: dict, policy: str) -> float:
    wins = 0.0
    n = 0
    for w in payload["worlds"]:
        scores = {p: float(m["best_true"]) for p, m in w["policies"].items()
                  if p != "oracle"}
        best = max(scores.values())
        winners = [p for p, v in scores.items() if abs(v - best) < 1e-9]
        if policy in winners:
            wins += 1.0 / len(winners)
        n += 1
    return 100.0 * wins / n if n else float("nan")


def _pair(payload: dict, a: str, b: str) -> float:
    diffs = []
    for w in payload["worlds"]:
        if a in w["policies"] and b in w["policies"]:
            diffs.append(float(w["policies"][a]["best_true"])
                         - float(w["policies"][b]["best_true"]))
    return sum(diffs) / len(diffs) if diffs else float("nan")


def _bar(label: str, value: float, max_value: float, kind: str = "") -> str:
    width = max(1.0, 100.0 * value / max_value)
    return (
        f'<div class="bar-row"><span class="bar-label">{label}</span>'
        f'<div class="bar-track"><div class="bar {kind}" style="width:{width:.1f}%"></div></div>'
        f'<span class="bar-value">{value:.1f}</span></div>'
    )


CSS = """
@page { size: A4 landscape; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #f7f4ee; color: #1d2833; }
body {
  width: 297mm; height: 210mm; overflow: hidden;
  font-family: "Segoe UI", system-ui, -apple-system, Arial, sans-serif;
  font-size: 9pt; line-height: 1.32;
}
.page {
  width: 100%; height: 100%; padding: 6mm 9mm 4.5mm;
  display: flex; flex-direction: column; gap: 2.6mm;
}
.top { display: flex; justify-content: space-between; gap: 6mm; align-items: flex-start; }
.kicker { font-size: 7pt; font-weight: 800; letter-spacing: .14em; color: #0f766e; text-transform: uppercase; }
h1 { font-size: 21pt; line-height: 1.02; margin: 1mm 0 1.4mm; letter-spacing: -.02em; }
.sub { font-size: 9.8pt; color: #3f4c58; max-width: 164mm; margin: 0; }
.badges { display: flex; flex-direction: column; gap: 1.2mm; min-width: 62mm; }
.badge { border: 1px solid #d8d2c6; background: #fff; border-radius: 2.2mm; padding: 1.3mm 2mm; font-size: 7.1pt; }
.badge b { display: block; font-size: 8pt; color: #1d2833; }
.badge.real { background: #e5f4f0; border-color: #b9ddd6; }
.badge.syn { background: #fbe9dc; border-color: #f1c6ac; }

.why { border: 1px solid #d8d2c6; background: #fff; border-radius: 2.5mm; padding: 2mm 3mm 2.2mm; }
.why h2 { font-size: 9.8pt; margin: 0 0 1.3mm; }
.why-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2.2mm; }
.why-item { border-left: 2.2px solid #0f766e; padding-left: 2mm; }
.why-item b { display: block; font-size: 8.4pt; margin-bottom: .4mm; }
.why-item span { color: #53616e; font-size: 7.6pt; }

.mid { display: grid; grid-template-columns: 1.12fr .88fr; gap: 3mm; flex: 1; min-height: 0; }
.card { border: 1px solid #d8d2c6; background: #fff; border-radius: 2.5mm; padding: 2.2mm 2.8mm; }
.card h2 { font-size: 9.8pt; margin: 0 0 1.2mm; }
.card p { margin: 0 0 .8mm; }

.flow { display: flex; align-items: stretch; gap: 1.5mm; margin-top: 1.2mm; }
.step { flex: 1; border: 1px solid #d8d2c6; background: #fbfaf7; border-radius: 2mm; padding: 1.5mm; position: relative; }
.step .num { width: 5mm; height: 5mm; border-radius: 50%; background: #0f766e; color: #fff; font-size: 7pt; font-weight: 800; display: flex; align-items: center; justify-content: center; margin-bottom: .8mm; }
.step b { display: block; font-size: 8.1pt; margin-bottom: .4mm; }
.step span { display: block; color: #53616e; font-size: 7.3pt; }
.arrow { align-self: center; color: #0f766e; font-size: 12pt; font-weight: 800; }
.flow-note { color: #53616e; font-size: 7.5pt; margin-top: 1.3mm; }
.mini { background: #f7f6f2; border: 1px solid #e4dfd4; border-radius: 2mm; padding: 1.5mm 2mm; margin-top: 1.6mm; }
.mini b { display: block; font-size: 7.9pt; margin-bottom: .4mm; }
.mini span { display: block; color: #53616e; font-size: 7.3pt; }
.mini ul { margin: .2mm 0 0; padding-left: 3.2mm; }
.mini li { color: #53616e; font-size: 7.3pt; margin: .25mm 0; }
.mini-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2mm; margin-top: 1.6mm; }
.mini-grid .mini { margin-top: 0; }
.budget { border-top: 1px solid #e4dfd4; margin-top: 2mm; padding-top: 1.6mm; }
.budget b { display: block; font-size: 7.9pt; margin-bottom: .8mm; }
.squares { display: flex; gap: .7mm; flex-wrap: nowrap; margin-bottom: .8mm; }
.sq { width: 3.2mm; height: 3.2mm; border-radius: .6mm; display: inline-block; }
.sq.seed { background: #c9d2da; }
.sq.adapt { background: #0f766e; }
.budget-note { color: #53616e; font-size: 7.1pt; }
.budget-note .key { display: inline-block; width: 2.4mm; height: 2.4mm; border-radius: .5mm; margin: 0 .6mm 0 0; vertical-align: -0.2mm; }

.meaning { background: #f2fbf9; border: 1px solid #b9ddd6; border-radius: 2mm; padding: 1.4mm 2mm; margin-top: 1.6mm; }
.meaning b { display: block; font-size: 7.9pt; margin-bottom: .4mm; color: #0b5f58; }
.meaning span { display: block; color: #3f5f5a; font-size: 7.3pt; margin-top: .3mm; }

.chart { margin-top: .8mm; }
.bar-row { display: grid; grid-template-columns: 26mm 1fr 11mm; gap: 1.5mm; align-items: center; margin: .95mm 0; }
.bar-label { font-size: 7.7pt; }
.bar-track { height: 4.1mm; border-radius: 999px; background: #ece7dd; overflow: hidden; }
.bar { height: 100%; border-radius: 999px; background: #9aa7b4; }
.bar.planner { background: #0f766e; }
.bar.simple { background: #c2410c; }
.bar.cheat { background: #b7aea0; }
.bar-value { text-align: right; font-weight: 800; font-size: 7.7pt; font-variant-numeric: tabular-nums; }
.chart-note { color: #64717d; font-size: 7pt; margin-top: 1mm; }

.callout { border-left: 3.2px solid #c2410c; background: #fff5ee; border-radius: 0 2mm 2mm 0; padding: 1.5mm 2.2mm; margin-top: 1.6mm; font-size: 7.9pt; }
.callout b { color: #9a3412; }

.limits { display: grid; grid-template-columns: repeat(5, 1fr); gap: 2mm; }
.limit { background: #fff; border: 1px solid #d8d2c6; border-radius: 2mm; padding: 1.5mm 1.8mm; }
.limit b { display: block; font-size: 7.9pt; margin-bottom: .4mm; }
.limit span { display: block; color: #53616e; font-size: 7.1pt; }
.limit.warn { background: #fff5ee; border-color: #f1c6ac; }

.footer { display: flex; justify-content: space-between; gap: 5mm; align-items: flex-end; border-top: 1px solid #d8d2c6; padding-top: 1.5mm; }
.footer p { margin: 0; color: #64717d; font-size: 6.8pt; max-width: 190mm; }
.footer .links { text-align: right; font-size: 6.8pt; color: #53616e; white-space: nowrap; }
code { font-family: Consolas, monospace; font-size: .95em; }
"""


def build_html() -> str:
    held = _load("benchmark_heldout.json")
    mean = {p: _mean(held, p) for p in
            ["twin_explore", "random", "lhc", "grid", "ofat", "oracle"]}
    win = {p: _win_rate(held, p) for p in ["twin_explore", "random", "lhc", "grid", "ofat"]}
    d_random = _pair(held, "twin_explore", "random")
    d_lhc = _pair(held, "twin_explore", "lhc")
    d_grid = _pair(held, "twin_explore", "grid")
    d_ofat = _pair(held, "twin_explore", "ofat")

    bars = "".join([
        _bar("Planner", mean["twin_explore"], mean["oracle"], "planner"),
        _bar("Random", mean["random"], mean["oracle"]),
        _bar("Space-filling", mean["lhc"], mean["oracle"]),
        _bar("Grid", mean["grid"], mean["oracle"]),
        _bar("One-at-a-time", mean["ofat"], mean["oracle"], "simple"),
        _bar("Best possible *", mean["oracle"], mean["oracle"], "cheat"),
    ])
    squares = ("".join('<span class="sq seed"></span>' for _ in range(15))
               + "".join('<span class="sq adapt"></span>' for _ in range(15)))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Plain-language brief - planning lab experiments</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">

  <header class="top">
    <div>
      <div class="kicker">Plain-language brief &middot; October 2026</div>
      <h1>A smarter way to plan lab experiments</h1>
      <p class="sub">Turning fish waste into antioxidant peptides - and using every experiment
      to choose the next one. This page explains what the project does, what the test found,
      and what it still cannot claim.</p>
    </div>
    <div class="badges">
      <div class="badge real"><b>Real data</b>31 batches &middot; 7 time-course curves</div>
      <div class="badge syn"><b>Synthetic test</b>100 unseen computer-generated worlds</div>
      <div class="badge"><b>Real campaign</b>0 of 15 runs measured so far</div>
    </div>
  </header>

  <section class="why">
    <h2>Why this project can be useful</h2>
    <div class="why-grid">
      <div class="why-item"><b>Less wasted bench time</b><span>Each run is chosen to teach the most, instead of guessing.</span></div>
      <div class="why-item"><b>Covers more ground</b><span>It explores enzyme, pH, temperature, time and dose combinations a person might miss.</span></div>
      <div class="why-item"><b>Learns as it goes</b><span>Every measured batch updates the next three suggestions.</span></div>
      <div class="why-item"><b>Keeps a paper trail</b><span>Every suggestion has a reason and a record, so the lab stays in control.</span></div>
    </div>
  </section>

  <div class="mid">
    <section class="card">
      <h2>How the loop works</h2>
      <div class="flow">
        <div class="step"><div class="num">1</div><b>Start with data</b><span>31 historical batches and 7 time curves.</span></div>
        <div class="arrow">&rarr;</div>
        <div class="step"><div class="num">2</div><b>Predict</b><span>A physics model estimates DH; a ranker scores antioxidant potential.</span></div>
        <div class="arrow">&rarr;</div>
        <div class="step"><div class="num">3</div><b>Choose</b><span>The planner proposes the next 3 runs.</span></div>
        <div class="arrow">&rarr;</div>
        <div class="step"><div class="num">4</div><b>Test</b><span>The lab measures the real result.</span></div>
        <div class="arrow">&rarr;</div>
        <div class="step"><div class="num">5</div><b>Learn</b><span>Update the model and repeat.</span></div>
      </div>
      <p class="flow-note"><b>DH</b> = how much protein is broken into small peptides (the main score).
      <b>Planner</b> = the model that chooses the next experiments.
      The planner is the part under test; the physics model is fitted to Alcalase only.</p>
      <div class="mini-grid">
        <div class="mini"><b>What the lab gets</b>
          <ul><li>3 suggested runs per round</li><li>A reason for each suggestion</li>
          <li>A record of every update</li><li>A model that improves with data</li></ul>
        </div>
        <div class="mini"><b>What it does not do</b>
          <ul><li>Replace lab judgment</li><li>Guarantee a better run</li>
          <li>Yet optimise antioxidant score or cost</li></ul>
        </div>
      </div>
      <div class="budget"><b>What the 30-run budget means</b>
        <div class="squares">{squares}</div>
        <span class="budget-note">
          <span class="key" style="background:#c9d2da"></span>15 shared seed runs
          &nbsp; <span class="key" style="background:#0f766e"></span>15 adaptive runs chosen by each method
        </span>
      </div>
    </section>

    <section class="card">
      <h2>What the synthetic test found</h2>
      <p>100 unseen computer-generated worlds. Same 30-run budget for every method.
      Higher is better.</p>
      <div class="chart">{bars}</div>
      <p class="chart-note">* Best possible is a cheat sheet that knows the synthetic truth.
      It is not a real method. Values are the best true DH reached by run 30.</p>
      <div class="callout"><b>The planner beat random, space-filling and grid search.</b>
      A simple one-setting-at-a-time search did better: {mean['ofat']:.1f} vs
      {mean['twin_explore']:.1f}. So this is promising, not proven.</div>
      <div class="meaning"><b>What this means</b>
        <span><b>Promising:</b> it beat three common designs at the same 30-run budget.</span>
        <span><b>Not proven:</b> the simplest strong baseline still won.</span>
        <span><b>Next:</b> test on the real campaign, not more synthetic worlds.</span>
      </div>
    </section>
  </div>

  <section class="limits">
    <div class="limit warn"><b>Computer-generated lab only</b><span>Not real lab proof. The test world is not the real process.</span></div>
    <div class="limit warn"><b>Not the best baseline</b><span>One-setting-at-a-time won {win['ofat']:.1f}% of worlds; the planner won {win['twin_explore']:.1f}%.</span></div>
    <div class="limit"><b>Planner ranking is weak</b><span>It wins mostly by where it looks, not by a smart prediction.</span></div>
    <div class="limit"><b>Real campaign missing</b><span>0 of 15 runs have returned. Real-data validation is future work.</span></div>
    <div class="limit"><b>Cold-start caveat</b><span>The tested variant was a cold-start version. Production keeps the safer rule; realistic history removes the advantage.</span></div>
  </section>

  <footer class="footer">
    <p><b>What would make it useful:</b> run the 15-batch campaign and compare with one-setting-at-a-time
    on real data. If it holds, the lab can spend fewer runs finding good conditions. The planner is a
    decision aid, not a replacement for lab judgment. <b>Plain-English glossary:</b> DH = degree of
    hydrolysis; ORAC = antioxidant score; planner = experiment chooser; one-at-a-time = change one
    setting, measure, repeat.</p>
    <div class="links">Full report: <code>data/synthetic/benchmark_final_report.md</code><br>
    Deeper story: <code>reports/twin_story.html</code><br>
    No real-world trial-reduction claim.</div>
  </footer>

</div>
</body>
</html>
"""


def export(html_path: Path = HTML_PATH) -> None:
    """Render the HTML to a one-page A4 landscape PDF and a high-resolution PNG."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1123, "height": 794},
            device_scale_factor=2,
        )
        page.goto(html_path.resolve().as_uri(), wait_until="load")
        page.screenshot(path=str(PNG_PATH), full_page=True)
        page.emulate_media(media="print")
        page.pdf(
            path=str(PDF_PATH),
            format="A4",
            landscape=True,
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        browser.close()


def main() -> None:
    REPORTS.mkdir(exist_ok=True)
    HTML_PATH.write_text(build_html(), encoding="utf-8")
    print(f"[make_plain_brief] wrote {HTML_PATH} ({HTML_PATH.stat().st_size / 1024:.1f} KB)")
    export()
    print(f"[make_plain_brief] wrote {PDF_PATH} ({PDF_PATH.stat().st_size / 1024:.1f} KB)")
    print(f"[make_plain_brief] wrote {PNG_PATH} ({PNG_PATH.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
