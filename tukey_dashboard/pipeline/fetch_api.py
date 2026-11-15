"""Download the public leaderboard API (https://datathon.rawtree.dev/api/state) in fixed windows.

Writes data/raw/api/state_{by}_{from}_{to}.json. Public endpoint, no credentials.
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=3600)
    ap.add_argument("--by", default="model", choices=["model", "team"])
    args = ap.parse_args()
    now_state = get(BASE)
    (OUT / "state_now.json").write_text(json.dumps(now_state))
    start = int(now_state["practice_start"])
    final_end = int(now_state["final_end"])
    end = min(int(now_state["updated_at"]), final_end)
    t = start
    while t + args.step <= end + 1:
        f, to = t, t + args.step
        path = OUT / f"state_{args.by}_{f}_{to}.json"
        if not path.exists() or to > end - 600:
            url = f"{BASE}?from={f}&to={to}" + ("&by=model" if args.by == "model" else "")
            try:
                path.write_text(json.dumps(get(url)))
                print("ok", path.name)
            except Exception as e:  # report and continue; a missing window is shown as missing, not zero
                print("fail", f, to, e)
            time.sleep(0.5)
        t = to


if __name__ == "__main__":
    main()
