"""Turn the downloaded leaderboard API windows into tidy CSV tables.

Inputs : data/raw/api/state_model_{from}_{to}.json  (fetch_api.py)
Outputs: data/tidy/api_teams.csv     one row per (window, team) incl. baseline/reference
         data/tidy/api_versions.csv  one row per (window, team_37 model_version)
         data/tidy/api_progress.csv  hourly conversion score (0-100) per team, from state_now.json
All times are kept as UNIX epoch seconds (UTC); CET = UTC+1 is applied only for display.
"""
from __future__ import annotations

import csv
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "api"
OUT = ROOT / "data" / "tidy"
OUT.mkdir(parents=True, exist_ok=True)
TEAM = "team_37"


def windows() -> list[tuple[int, int, dict]]:
    out = []
    for f in glob.glob(str(RAW / "state_model_*.json")):
        stem = Path(f).stem.split("_")
        a, b = int(stem[-2]), int(stem[-1])
        out.append((a, b, json.loads(Path(f).read_text())))
    return sorted(out, key=lambda x: (x[1] - x[0], x[0]))


def main() -> None:
    teams_rows, version_rows = [], []
    for a, b, d in windows():
        span = b - a
        ranked = sorted(d.get("teams", []), key=lambda x: -x["conversion"])
        rank = {x["team_id"]: i + 1 for i, x in enumerate(ranked)}
        for x in d.get("teams", []) + [d.get("baseline", {}), d.get("reference", {})]:
            if not x:
                continue
            teams_rows.append({
                "t0": a, "t1": b, "span_s": span, "team_id": x["team_id"],
                "requests": x.get("requests"), "conversion": x.get("conversion"),
                "cold_conversion": x.get("cold_conversion"), "on_time": x.get("on_time"),
                "revenue_per_request": x.get("revenue_per_request"),
                "model_version": x.get("model_version") or "",
                "rank": rank.get(x["team_id"], ""), "n_teams": len(ranked),
            })
            if x["team_id"] == TEAM:
                for v in x.get("versions", []):
                    version_rows.append({
                        "t0": a, "t1": b, "span_s": span, "model_version": v["model_version"],
                        "requests": v["requests"], "conversion": v["conversion"],
                        "cold_requests": v.get("cold_requests"), "cold_conversion": v.get("cold_conversion"),
                        "revenue_per_request": v.get("revenue_per_request"),
                        "first": v.get("first"), "last": v.get("last"),
                        "team_requests": x.get("requests"),
                    })
    for name, rows in (("api_teams.csv", teams_rows), ("api_versions.csv", version_rows)):
        with open(OUT / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(name, len(rows))
    now = json.loads((RAW / "state_now.json").read_text())
    prog = [{"team_id": k, "t0": int(t), "score": s} for k, series in now.get("progress", {}).items() for t, s in series]
    with open(OUT / "api_progress.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["team_id", "t0", "score"])
        w.writeheader()
        w.writerows(prog)
    print("api_progress.csv", len(prog))


if __name__ == "__main__":
    main()
