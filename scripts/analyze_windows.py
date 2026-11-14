"""Read fixed leaderboard windows; save raw evidence and a compact model table.

Usage: python scripts/analyze_windows.py
No submissions or serving settings are changed.
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.config import LOGS, TEAM

URL = "https://datathon.rawtree.dev/api/state"


def main():
    session = requests.Session()
    response = session.get(URL, params={"by": "model"}, timeout=20)
    response.raise_for_status()
    latest = response.json()
    end = int(latest["updated_at"]) // 300 * 300
    windows = [(f"last_{minutes}m", end - minutes * 60, end) for minutes in (15, 30, 60, 120, 180)]
    # Non-overlapping windows expose changes hidden by a rolling-hour average.
    windows += [(f"previous_{i}x15m", end - (i + 1) * 900, end - i * 900) for i in (1, 2, 3)]
    evidence = {"latest": latest, "windows": {}}
    records = []
    for label, start, stop in windows:
        response = session.get(URL, params={"by": "model", "from": start, "to": stop}, timeout=20)
        response.raise_for_status()
        state = response.json()
        evidence["windows"][label] = state
        ours = next((t for t in state.get("teams", []) if t["team_id"] == TEAM), {})
        actual_start, actual_stop = state.get("window", [start, stop])
        local = lambda t: datetime.fromtimestamp(t, ZoneInfo("Europe/Paris")).strftime("%H:%M")
        print(f"\n{label} {local(actual_start)}-{local(actual_stop)} custom={state.get('custom')} "
              f"team_conv={ours.get('conversion', 0):.4f} on_time={ours.get('on_time', 0):.2f}%")
        base = state.get("baseline", {}).get("conversion", 0)
        for v in ours.get("versions", []):
            row = dict(window=label, start=actual_start, end=actual_stop,
                       model=v["model_version"], requests=v["requests"], conversion=v["conversion"],
                       cold_requests=v.get("cold_requests", 0), cold_conversion=v.get("cold_conversion"),
                       revenue_per_request=v.get("revenue_per_request"), baseline=base)
            records.append(row)
            print(f"  {row['model']:24s} n={row['requests']:5d} conv={row['conversion']:.4f} "
                  f"cold={row['cold_conversion'] or 0:.4f} cold_n={row['cold_requests']}")
    stem = LOGS / f"window_audit_{end}"
    stem.with_suffix(".json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    if records:
        with stem.with_suffix(".csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    print(f"\nEvidence: {stem}")


if __name__ == "__main__":
    main()
