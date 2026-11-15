"""Download the public leaderboard API (https://datathon.rawtree.dev/api/state) in fixed windows.

Writes data/raw/api/state_{by}_{from}_{to}.json. Public endpoint, no credentials.
While the final runs (mode "final_running") the API hides every team and only shows green/red lights: an empty answer
is never written over a good file, and a window stored empty is fetched again on the next run.
After the final (mode "final") the API ignores from/to and always answers with the official final aggregate
(`window` = [final_start, final_end]): that answer is stored once as state_final.json and never as a practice window.
Usage: python fetch_api.py [--step 3600] [--by team|model]
"""
from __future__ import annotations

import argparse
import json
import time
import requests
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "raw" / "api"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "https://datathon.rawtree.dev/api/state"


def get(url: str) -> dict:
    r = requests.get(url, headers={"User-Agent": "tukey-dashboard/1.0"}, timeout=30)
    r.raise_for_status()
    return r.json()


def has_teams(d: dict) -> bool:
    return bool(d.get("teams"))


def window_ok(d: dict, f: int, to: int) -> bool:
    """The answer covers the window that was asked for (older answers carry no `window` field)."""
    w = d.get("window")
    return has_teams(d) and (not w or (abs(float(w[0]) - f) <= 1 and abs(float(w[1]) - to) <= 1))


def stored_ok(path: Path) -> bool:
    try:
        stem = path.stem.split("_")
        return window_ok(json.loads(path.read_text()), int(stem[-2]), int(stem[-1]))
    except (OSError, ValueError):
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=3600)
    ap.add_argument("--by", default="model", choices=["model", "team"])
    args = ap.parse_args()
    now_state = get(BASE)
    print("API mode:", now_state.get("mode"))
    (OUT / "state_live.json").write_text(json.dumps(now_state))
    if has_teams(now_state) and now_state.get("progress"):
        (OUT / "state_now.json").write_text(json.dumps(now_state))   # keeps the last published progress series
    else:
        print("API hides the leaderboard right now: kept the previous state_now.json")
    if now_state.get("mode") == "final" and has_teams(now_state):
        final = get(BASE + "?by=model") if args.by == "model" else now_state
        (OUT / "state_final.json").write_text(json.dumps(final))
        print("official final aggregate ->", "state_final.json", final.get("window"))
    start = int(now_state["practice_start"])
    final_end = int(now_state["final_end"])
    end = min(int(now_state["updated_at"]), final_end)
    t = start
    while t + args.step <= end + 1:
        f, to = t, t + args.step
        path = OUT / f"state_{args.by}_{f}_{to}.json"
        if not stored_ok(path) or to > end - 600:
            url = f"{BASE}?from={f}&to={to}" + ("&by=model" if args.by == "model" else "")
            try:
                d = get(url)
                if window_ok(d, f, to):
                    path.write_text(json.dumps(d))
                    print("ok", path.name)
                elif has_teams(d):
                    print("API answered another window", d.get("window"), "instead of", path.name, "(not stored)")
                else:
                    print("not published yet", path.name)
            except Exception as e:  # report and continue; a missing window is shown as missing, not zero
                print("fail", f, to, e)
            time.sleep(0.5)
        t = to


if __name__ == "__main__":
    main()
