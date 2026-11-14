"""Morning KPI report for t37-m4 vs the team's other live versions, plus the learned-weight trajectory.

    python -m recsys.thompson.report [--minutes-per-window 15]

Writes data/thompson_report.csv (per-window leaderboard rows) and prints:
  1. per 15-min window since launch: leaderboard conversion / cold / revenue for t37-m4 and the best other t37 version
  2. realised buys & clicks per 100 on requests where *our* list was the one shown
  3. collision rate and fallback levels from the serve log
  4. named click weights across posterior versions (start, hourly, latest)
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd

from .features import CLICK_FEATURES
from .model import Posterior

ROOT = Path(__file__).resolve().parents[2]


def own_shown(log: pd.DataFrame, fb: pd.DataFrame) -> dict:
    sent = log[log.status.isin(["ok", "timeout_unknown"])]
    m = sent.merge(fb, on="request_id", how="inner")
    m = m[[list(a) == list(b) for a, b in zip(m["items"], m["shown"])]]
    n = len(m)
    return dict(sent=len(sent), with_feedback=int(sent.request_id.isin(fb.request_id).sum()), shown_ours=n,
                buys_per_100=100 * float((m.purchased.fillna("") != "").sum()) / n if n else float("nan"),
                clicks_per_100=100 * float((m.clicked.fillna("") != "").sum()) / n if n else float("nan"))


def weight_table(path: Path, every: int = 30) -> pd.DataFrame:
    files = sorted(Path(path).glob("posterior_v*.pkl"))
    if not files:
        return pd.DataFrame(index=CLICK_FEATURES)
    pick = sorted(set(files[::every]) | {files[0], files[-1]})
    cols = {}
    for f in pick:
        p = Posterior.load(f)
        cols[f"v{p.version}"] = p.click.m
    return pd.DataFrame(cols, index=CLICK_FEATURES)


def windows(version: str, team: str, start: float, step_min: int = 15) -> pd.DataFrame:
    from .guards import fetch_state
    rows = []
    end_all = int(time.time()) // 300 * 300
    t = int(start) // 300 * 300 + 300
    while t + 60 * step_min <= end_all:
        try:
            j = fetch_state(step_min, end=t + 60 * step_min)
        except Exception as e:
            print("window fetch failed:", str(e)[:100])
            t += 60 * step_min
            continue
        for tm in j.get("teams", []):
            if tm.get("team_id") != team:
                continue
            for v in tm.get("versions", []):
                rows.append(dict(window_end=pd.Timestamp(t + 60 * step_min, unit="s"), version=v["model_version"],
                                 requests=v.get("requests"), conversion=v.get("conversion"),
                                 cold=v.get("cold_conversion"), revenue=v.get("revenue_per_request"),
                                 team_on_time=tm.get("on_time")))
        t += 60 * step_min
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="t37-m4")
    ap.add_argument("--minutes-per-window", type=int, default=15)
    a = ap.parse_args()
    from .. import data as D
    from .learner import MODELS
    log_path = D.DATA / "thompson_serve.pkl"
    log = pd.read_pickle(log_path) if log_path.exists() else pd.DataFrame(columns=["request_id", "ts", "items", "status",
                                                                                    "fallback"])
    live = log[log.status.isin(["ok", "timeout_unknown"])]
    pd.set_option("display.width", 200)
    if len(live):
        start = pd.Timestamp(live.ts.min()).timestamp()
        print(f"live since {pd.Timestamp(live.ts.min())} UTC: {len(live)} answers sent")
        w = windows(a.version, D.TEAM, start, a.minutes_per_window)
        if len(w):
            w.to_csv(D.DATA / "thompson_report.csv", index=False)
            ours = w[w.version == a.version].set_index("window_end")
            best = (w[(w.version != a.version) & (w.requests >= 100)].sort_values("conversion")
                    .groupby("window_end").tail(1).set_index("window_end"))
            tab = ours[["requests", "conversion", "cold", "revenue", "team_on_time"]].join(
                best[["version", "requests", "conversion", "cold", "revenue"]], rsuffix="_other")
            print("\n## leaderboard per window (ours vs best other team version)\n", tab.round(3).to_string())
        ids = "','".join(live.request_id.tail(20000))
        fb = D.sql(f"SELECT request_id::String request_id, shown, clicked::String clicked, purchased::String purchased "
                   f"FROM {D.TEAM}.feedback WHERE request_id::String IN ('{ids}')", timeout=120)
        print("\n## realised on requests where our list was shown\n", own_shown(live.tail(20000), fb))
        try:
            from .guards import COLLISION_SQL, collision_rate
            print("collision rate (last 5 min):", round(collision_rate(D.sql(COLLISION_SQL.format(team=D.TEAM)),
                                                                       a.version), 3))
        except Exception as e:
            print("collision check failed:", str(e)[:100])
    else:
        print("no live answers in", log_path)
    if len(log):
        print("\nstatus:", log.status.value_counts().to_dict(), "| fallback levels:", log.fallback.value_counts().to_dict())
    print("\n## click weights over posterior versions\n", weight_table(MODELS).round(3).to_string())


if __name__ == "__main__":
    main()
