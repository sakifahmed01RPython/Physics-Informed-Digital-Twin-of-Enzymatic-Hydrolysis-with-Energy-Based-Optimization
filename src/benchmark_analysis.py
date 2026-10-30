"""Post-hoc analysis of frozen benchmark runs.

Reads the aggregate JSON (which contains per-world policy metrics) and prints:
  * per-world best true DH for selected worlds
  * mean best true DH and tie-credited win rates
  * pairwise mean differences with bootstrap CIs
  * the pre-registered sensitivity comparison (150 vs 500 candidates)

This does not re-run any world and does not alter the frozen run files.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SYN = ROOT / "data" / "synthetic"


def load(prefix: str) -> dict:
    with open(SYN / f"{prefix}.json", encoding="utf-8") as fh:
        return json.load(fh)


def best_true(payload: dict, policy: str) -> dict[int, float]:
    out = {}
    for w in payload["worlds"]:
        if policy in w["policies"]:
            out[int(w["world"])] = float(w["policies"][policy]["best_true"])
    return out


def boot_ci(vals, n_boot=4000, seed=7):
    vals = np.asarray(vals, dtype=float)
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return [float("nan"), float("nan")]
    rng = np.random.default_rng(seed)
    means = np.array([rng.choice(vals, len(vals), replace=True).mean()
                      for _ in range(n_boot)])
    lo, hi = np.percentile(means, [2.5, 97.5])
    return [float(lo), float(hi)]


def table(payload: dict, worlds: list[int], policies: list[str]) -> dict:
    series = {p: best_true(payload, p) for p in policies}
    common = sorted(set(worlds) & set.intersection(*(set(s) for s in series.values())))
    mat = np.array([[series[p][w] for w in common] for p in policies])
    # Tie-credited win rate: each world's best value splits credit equally.
    # The oracle is an upper bound, not a competitor, so it is excluded.
    scored = [i for i, p in enumerate(policies) if p != "oracle"]
    wins = {p: 0.0 for p in policies}
    for j in range(len(common)):
        col = mat[scored, j]
        best = np.nanmax(col)
        winners = np.where(np.isclose(col, best, atol=1e-9))[0]
        for i in winners:
            wins[policies[scored[i]]] += 1.0 / len(winners)
    out = {"worlds": common, "n": len(common)}
    for i, p in enumerate(policies):
        out[p] = {
            "mean": float(np.nanmean(mat[i])),
            "ci": boot_ci(mat[i]),
            "win_pct": 100.0 * wins[p] / len(common),
        }
    out["mat"] = mat
    return out


def pairwise(payload: dict, worlds: list[int], a: str, b: str) -> dict:
    sa, sb = best_true(payload, a), best_true(payload, b)
    common = sorted(set(worlds) & set(sa) & set(sb))
    diff = np.array([sa[w] - sb[w] for w in common], dtype=float)
    return {
        "n": len(common),
        "mean_diff": float(diff.mean()),
        "ci": boot_ci(diff),
        "a_wins_pct": float(100.0 * (diff > 0).mean()),
        "ties_pct": float(100.0 * (diff == 0).mean()),
        "b_wins_pct": float(100.0 * (diff < 0).mean()),
    }


def paired_runs(payload_a: dict, payload_b: dict, policy: str,
                worlds: list[int]) -> dict:
    """Compare the same policy across two run settings (e.g. cold vs warm)."""
    sa, sb = best_true(payload_a, policy), best_true(payload_b, policy)
    common = sorted(set(worlds) & set(sa) & set(sb))
    diff = np.array([sa[w] - sb[w] for w in common], dtype=float)
    return {
        "n": len(common),
        "mean_diff": float(diff.mean()),
        "ci": boot_ci(diff),
        "a_wins_pct": float(100.0 * (diff > 0).mean()),
        "ties_pct": float(100.0 * (diff == 0).mean()),
        "b_wins_pct": float(100.0 * (diff < 0).mean()),
    }


def show(title: str, t: dict, policies: list[str]) -> None:
    print(f"\n=== {title} (n={t['n']}) ===")
    for p in policies:
        lo, hi = t[p]["ci"]
        print(f"  {p:16s} mean={t[p]['mean']:6.2f}  CI=[{lo:6.2f},{hi:6.2f}]  "
              f"win={t[p]['win_pct']:5.1f}%")


def main() -> None:
    held = load("benchmark_heldout")
    sens = load("benchmark_sensitivity_500")
    cold_dev = load("benchmark_cold_start_dev")
    warm_dev = load("benchmark_warm_start_dev")
    warm_held = load("benchmark_warm_start_heldout")
    policies = ["twin_explore", "random", "lhc", "ofat", "grid", "oracle"]
    all_policies = ["twin_current"] + policies

    show("held-out 100-199", table(held, list(range(100, 200)), policies), policies)
    show("held-out leave-out 102-199", table(held, list(range(102, 200)), policies), policies)
    show("sensitivity worlds 100-109 @ 150 candidates",
         table(held, list(range(100, 110)), policies), policies)
    show("sensitivity worlds 100-109 @ 500 candidates",
         table(sens, list(range(100, 110)), policies), policies)
    show("cold-start development 0-24",
         table(cold_dev, list(range(0, 25)), all_policies), all_policies)
    show("warm-start development 0-24",
         table(warm_dev, list(range(0, 25)), all_policies), all_policies)
    show("warm-start held-out 100-109",
         table(warm_held, list(range(100, 110)), all_policies), all_policies)

    print("\n=== pairwise ===")
    for label, payload, worlds in [
        ("held-out 100-199", held, list(range(100, 200))),
        ("leave-out 102-199", held, list(range(102, 200))),
        ("100-109 @150", held, list(range(100, 110))),
        ("100-109 @500", sens, list(range(100, 110))),
        ("cold-start dev 0-24", cold_dev, list(range(0, 25))),
        ("warm-start dev 0-24", warm_dev, list(range(0, 25))),
        ("warm-start held-out 100-109", warm_held, list(range(100, 110))),
    ]:
        print(f"\n-- {label} --")
        for a, b in [("twin_explore", "random"), ("twin_explore", "lhc"),
                     ("twin_explore", "ofat"), ("twin_explore", "grid"),
                     ("twin_current", "twin_explore"),
                     ("twin_current", "ofat"),
                     ("ofat", "random"), ("ofat", "grid")]:
            if a not in payload["worlds"][0]["policies"] or \
                    b not in payload["worlds"][0]["policies"]:
                continue
            r = pairwise(payload, worlds, a, b)
            print(f"  {a} vs {b}: {r['mean_diff']:+.2f} "
                  f"[{r['ci'][0]:+.2f},{r['ci'][1]:+.2f}]  "
                  f"A wins {r['a_wins_pct']:.1f}%  ties {r['ties_pct']:.1f}%  "
                  f"B wins {r['b_wins_pct']:.1f}%")

    print("\n=== history effect (cold minus warm, same policy) ===")
    for label, cold, warm, worlds in [
        ("dev 0-24", cold_dev, warm_dev, list(range(0, 25))),
        ("held-out 100-109", held, warm_held, list(range(100, 110))),
    ]:
        for policy in ("twin_explore", "twin_current", "ofat", "random"):
            if policy not in cold["worlds"][0]["policies"] or \
                    policy not in warm["worlds"][0]["policies"]:
                continue
            r = paired_runs(cold, warm, policy, worlds)
            print(f"  {label} {policy}: cold-warm {r['mean_diff']:+.2f} "
                  f"[{r['ci'][0]:+.2f},{r['ci'][1]:+.2f}]  "
                  f"cold wins {r['a_wins_pct']:.1f}%  ties {r['ties_pct']:.1f}%  "
                  f"warm wins {r['b_wins_pct']:.1f}%")

    # The pre-registered rule: compare twin-vs-random win rates on the same 10
    # worlds at 150 and 500 candidates. A >15 point change invalidates the
    # headline.
    d150 = pairwise(held, list(range(100, 110)), "twin_explore", "random")
    d500 = pairwise(sens, list(range(100, 110)), "twin_explore", "random")
    print("\n=== pre-registered sensitivity rule ===")
    print(f"  twin-vs-random A-win rate @150: {d150['a_wins_pct']:.1f}%")
    print(f"  twin-vs-random A-win rate @500: {d500['a_wins_pct']:.1f}%")
    print(f"  change: {d500['a_wins_pct'] - d150['a_wins_pct']:+.1f} points")
    print(f"  mean advantage @150: {d150['mean_diff']:+.2f} DH; "
          f"@500: {d500['mean_diff']:+.2f} DH")


if __name__ == "__main__":
    main()
