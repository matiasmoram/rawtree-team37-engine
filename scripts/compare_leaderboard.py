"""Read-only same-window team comparison, live-writer audit and cached feedback diagnostics.

python scripts/compare_leaderboard.py [--teams team_06,team_37] [--dataset PATH]
Saves aggregate evidence under logs/competitor_audit.json, without request/user IDs.
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.config import CACHE, LOGS, TEAM
from engine.features import FEATURES
from engine.learn.dataset import relation
from engine.rt import RawTree
from engine.types import parse_ts, sql_ts
from scripts.check_emitters import audit_window


FIELDS = ("team_id", "requests", "conversion", "cold_conversion", "on_time", "revenue_per_request",
          "model_version", "best", "more_versions")


def team_summary(team):
    result = {key: team.get(key) for key in FIELDS}
    result["versions"] = [dict(v, display_support_at_least_300=v["requests"] >= 300)
                          for v in team.get("versions", [])]
    return result


def compare_windows(session, teams, minutes=(15, 30, 60)):
    response = session.get("https://datathon.rawtree.dev/api/state", params={"by": "model"}, timeout=20)
    response.raise_for_status()
    latest = response.json()
    end = int(latest["updated_at"]) // 300 * 300
    result = {}
    for span in minutes:
        response = session.get("https://datathon.rawtree.dev/api/state",
                               params={"by": "model", "from": end - span * 60, "to": end}, timeout=20)
        response.raise_for_status()
        state = response.json()
        rows = {t["team_id"]: team_summary(t) for t in state.get("teams", []) if t["team_id"] in teams}
        difference = {}
        if len(teams) == 2 and all(t in rows for t in teams):
            for metric in ("conversion", "cold_conversion", "on_time", "revenue_per_request"):
                difference[metric] = rows[teams[0]][metric] - rows[teams[1]][metric]
        result[str(span)] = {"window": state.get("window"), "custom": state.get("custom"),
                             "updated_at": state.get("updated_at"), "teams": rows,
                             "first_team_minus_second": difference,
                             "baseline": state.get("baseline"), "reference": state.get("reference")}
    return result


def dataset_diagnostics(path):
    with path.open("rb") as f:
        dataset = pickle.load(f)
    df = dataset["df"].copy()
    df["relation_group"] = relation(df[FEATURES].to_numpy())
    df["bought_before"] = (df["user_bought_n"] > 0) | (df["bought_in_event"] > 0)

    def summarize(frame, column):
        agg = frame.groupby(column, observed=True).agg(
            exposures=("purchase", "size"), requests=("request_id", "nunique"),
            clicks=("click", "sum"), purchases=("purchase", "sum"),
            bought_before_share=("bought_before", "mean"))
        agg["clicks_per_100_exposures"] = agg["clicks"] / agg["exposures"] * 100
        agg["purchases_per_100_exposures"] = agg["purchases"] / agg["exposures"] * 100
        return [{"group": str(key), **row} for key, row in agg.to_dict(orient="index").items()]

    out = {"dataset": path.name, "metadata": dataset["meta"], "feature_state": "PIT dataset cache",
           "warning": "Observed logged exposures; position and selection bias remain. Not counterfactual policy value."}
    for label, frame in (("full", df), ("latest30m", df[df.ts >= df.ts.max() - pd.Timedelta(minutes=30)])):
        frame = frame.copy()
        frame["slot_1based"] = frame["slot"].astype(int) + 1
        frame["slot_band"] = frame["slot"].astype(int).map(lambda s: "1-3" if s < 3 else ("4-6" if s < 6 else "7-10"))
        req = frame.groupby("request_id").agg(
            is_new_user=("is_new_user", "first"), views=("n_session_views", "first"),
            purchase=("purchase", "sum"), click=("click", "sum"))
        req["segment"] = req.apply(lambda r: "home/no_views" if r.views == 0 else
                                   ("new_user_with_views" if r.is_new_user else "known_user_with_views"), axis=1)
        segments = req.groupby("segment").agg(requests=("purchase", "size"), purchases=("purchase", "sum"),
                                                clicks=("click", "sum"))
        segments["realized_purchases_per_100_requests"] = segments.purchases / segments.requests * 100
        out[label] = {"from": str(frame.ts.min()), "to": str(frame.ts.max()),
                      "requests": int(frame.request_id.nunique()), "purchases": int(frame.purchase.sum()),
                      "relation": summarize(frame, "relation_group"), "slot": summarize(frame, "slot_1based"),
                      "relation_by_slot_band": summarize(frame, ["slot_band", "relation_group"]),
                      "request_segments": segments.to_dict(orient="index"),
                      "cold_request": summarize(frame, "cold_request"),
                      "platform_new_user": summarize(frame, "is_new_user"),
                      "bought_before": summarize(frame, "bought_before")}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--teams", default="team_06,team_37")
    ap.add_argument("--dataset", default=None)
    ap.add_argument("--out", default=str(LOGS / "competitor_audit.json"))
    args = ap.parse_args()
    teams = args.teams.split(",")
    rt = RawTree(timeout=30)
    end = parse_ts(rt.query("SELECT toString(now64(3)) AS ts", retries=0)[0]["ts"]) - timedelta(seconds=10)
    report = {"as_of": end.isoformat(), "same_window_comparisons": compare_windows(requests.Session(), teams),
              "emitters": {str(sec): audit_window(rt, end - timedelta(seconds=sec), end)
                           for sec in (60, 300)}}
    since = end - timedelta(minutes=30)
    last_seen = rt.query(f"""
        SELECT s.model_version::String AS model, count() AS submissions,
               toString(max(r.request_ts)) AS latest_request_ts
        FROM {TEAM}.submissions AS s INNER JOIN (
            SELECT request_id::String AS rid, ts::DateTime64(3) AS request_ts FROM shop.requests
            WHERE ts::DateTime64(3) >= '{sql_ts(since)}' AND ts::DateTime64(3) < '{sql_ts(end)}'
        ) AS r ON r.rid = s.request_id::String
        GROUP BY model ORDER BY latest_request_ts DESC
        SETTINGS max_execution_time = 25""", timeout=30, retries=0)
    for row in last_seen:
        row["latest_request_cet"] = parse_ts(row["latest_request_ts"]).astimezone(ZoneInfo("Europe/Paris")).isoformat()
    report["model_last_seen"] = last_seen
    report["last_seen_definition"] = "Timestamp of latest request joined to a submission, not its unknown submission send timestamp."
    dataset = Path(args.dataset) if args.dataset else max(CACHE.glob("live_ds_v3_recent_*.pkl"), key=lambda p: p.stat().st_mtime)
    report["feedback_diagnostics"] = dataset_diagnostics(dataset)
    report["comparison_limit"] = ("Same windows remove time mismatch but version-level traffic contexts and sample counts differ. "
                                  "No paired randomization or statistical superiority is established by this report.")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str, allow_nan=False), encoding="utf-8")
    compact = {"as_of": report["as_of"],
               "windows": {k: {"window": v["window"], "difference": v["first_team_minus_second"],
                                "teams": {t: {f: r[f] for f in FIELDS} for t, r in v["teams"].items()}}
                           for k, v in report["same_window_comparisons"].items()},
               "emitters": {k: v["counts"] for k, v in report["emitters"].items()},
               "model_last_seen": last_seen, "dataset": dataset.name,
               "latest30m_relations": report["feedback_diagnostics"]["latest30m"]["relation"]}
    print(json.dumps(compact, indent=2, default=str))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
