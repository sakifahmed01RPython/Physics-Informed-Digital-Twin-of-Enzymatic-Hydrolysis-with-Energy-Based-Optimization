"""make_dashboard.py - embed the latest state.json snapshot into
reports/dashboard.html (self-contained; opens over file:// with no server).
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
TEMPLATE = BASE / "src" / "dashboard_template.html"
STATE = BASE / "data" / "dashboard" / "state.json"
OUT = BASE / "reports" / "dashboard.html"

PLACEHOLDER = "__STATE_JSON__"


def main():
    if not STATE.exists():
        print("state.json missing - run: python -m src.dashboard_state", file=sys.stderr)
        return 1
    state = json.loads(STATE.read_text(encoding="utf-8"))
    state.setdefault("regime", "snapshot")
    payload = json.dumps(state, separators=(",", ":"))
    html = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in html:
        print("template missing placeholder", PLACEHOLDER, file=sys.stderr)
        return 1
    html = html.replace(PLACEHOLDER, payload, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"[make_dashboard] {OUT}  ({OUT.stat().st_size / 1024:.1f} KB, "
          f"regime={state['regime']}, nodes={len(state['landscape']['nodes'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())