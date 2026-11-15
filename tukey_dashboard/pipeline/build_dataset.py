"""Derive every table the dashboard draws, from the raw API and DB extracts.

Inputs : data/raw/api/*.json (fetch_api.py), data/raw/db/{practice,final}/*.json (extract_db.py),
         data/manual/*.json (numbers transcribed from team docs / Notion, each with its source)
Output : data/dashboard_data.json   (single file embedded into the page by render.py)

Conventions
- Time: UNIX seconds UTC in the data; the page converts to CET (UTC+1) for display.
- Conversion = expected purchases per 100 requests (official simulator metric, API) unless a column says "realised".
- Score (0-100) = 100 * (conv - baseline) / (oracle - baseline), with the oracle implied by the API `progress`
  series for the same hour (verified identical for every team within an hour).
- Served-model conversion m of a team in a window with on-time share o and baseline b:
  team = o*m + (1-o)*b  =>  m = (team - (1-o)*b) / o   (fallback lists ARE the baseline list).
"""
from __future__ import annotations

import csv
import glob
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
TIDY = ROOT / "data" / "tidy"
MANUAL = ROOT / "data" / "manual"
TEAM = "team_37"
FINAL_START, FINAL_END = 1794733200, 1794740400


def fnum(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def load_db(period: str, name: str) -> list[dict]:
    p = RAW / "db" / period / f"{name}.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    return d.get("rows", []) if not d.get("err") else []


def db_meta(period: str) -> dict:
    p = RAW / "db" / period / "_meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


# ---------------------------------------------------------------- API derived
def api_tables():
    teams = list(csv.DictReader(open(TIDY / "api_teams.csv", encoding="utf-8")))
    versions = list(csv.DictReader(open(TIDY / "api_versions.csv", encoding="utf-8")))
    progress = list(csv.DictReader(open(TIDY / "api_progress.csv", encoding="utf-8")))
    return teams, versions, progress


def implied_oracle(teams, progress) -> dict[int, float]:
    """Hour start -> oracle conversion implied by progress = 100 (c - b) / (o - b)."""
    prog = {(r["team_id"], int(r["t0"])): float(r["score"]) for r in progress}
    hourly = [r for r in teams if r["span_s"] == "3600"]
    base = {int(r["t0"]): float(r["conversion"]) for r in hourly if r["team_id"] == "baseline"}
    out: dict[int, list[float]] = defaultdict(list)
    for r in hourly:
        k = (r["team_id"], int(r["t0"]))
        s = prog.get(k)
        if s is None or s < 10 or not r["team_id"].startswith("team"):
            continue
        b = base[int(r["t0"])]
        out[int(r["t0"])].append(b + 100 * (float(r["conversion"]) - b) / s)
    return {t: st.median(v) for t, v in out.items()}


def windows15(teams, versions, oracle):
    """team_37 per 15-min window with the reliability decomposition."""
    by_t = defaultdict(dict)
    for r in teams:
        if r["span_s"] == "900":
            by_t[int(r["t0"])][r["team_id"]] = r
    vreq = defaultdict(lambda: [0, 0.0])
    for v in versions:
        if v["span_s"] == "900":
            a = vreq[int(v["t0"])]
            a[0] += int(v["requests"])
            a[1] += int(v["requests"]) * float(v["conversion"])
    med_oracle = st.median(oracle.values()) if oracle else None
    rows = []
    for t in sorted(by_t):
        w = by_t[t]
        me, bl, rf = w.get(TEAM), w.get("baseline"), w.get("reference")
        if not me or not bl:
            continue
        field = sorted((x for k, x in w.items() if k.startswith("team")), key=lambda x: -float(x["conversion"]))
        b, c = float(bl["conversion"]), float(me["conversion"])
        o_hour = oracle.get(t - t % 3600, med_oracle)
        served_n, served_sum = vreq.get(t, [0, 0.0])
        served_share = served_n / float(me["requests"]) if float(me["requests"]) else None
        model = served_sum / served_n if served_n else None
        pred = served_share * model + (1 - served_share) * b if model is not None else None

        def score(x):
            return None if x is None or o_hour is None else max(0.0, min(100.0, 100 * (x - b) / (o_hour - b)))

        top6 = sorted(float(x["on_time"]) for x in field[:6])
        rows.append({
            "t": t, "requests": int(me["requests"]), "on_time": fnum(me["on_time"]),
            "top6_on_time_min": min(top6) if top6 else None, "top6_on_time_max": max(top6) if top6 else None,
            "top6_h1": st.median(top6[:3]) if top6 else None, "top6_med": st.median(top6) if top6 else None,
            "top6_h2": st.median(top6[3:]) if top6 else None,
            "cold_baseline": fnum(bl["cold_conversion"]), "cold_reference": fnum(rf["cold_conversion"]) if rf else None,
            "served_share": None if served_share is None else 100 * served_share,
            "team_conv": c, "model_conv": model, "pred_conv": pred,
            "cold_conv": fnum(me["cold_conversion"]), "revenue": fnum(me["revenue_per_request"]),
            "baseline": b, "reference": fnum(rf["conversion"]) if rf else None, "oracle": o_hour,
            "top_conv": float(field[0]["conversion"]) if field else None, "top_team": field[0]["team_id"] if field else None,
            "rank": int(me["rank"]) if me["rank"] else None, "n_teams": int(me["n_teams"]),
            "score_team": score(c), "score_model": score(model),
            "best_version": me["model_version"],
        })
    return rows


def hourly_field(teams, oracle):
    """All teams per hour: conversion, on-time, served-model conversion, score."""
    out = []
    hourly = [r for r in teams if r["span_s"] == "3600"]
    base = {int(r["t0"]): float(r["conversion"]) for r in hourly if r["team_id"] == "baseline"}
    ref = {int(r["t0"]): float(r["conversion"]) for r in hourly if r["team_id"] == "reference"}
    for r in hourly:
        t = int(r["t0"])
        if not r["team_id"].startswith("team") or t not in base:
            continue
        o = (fnum(r["on_time"]) or 0) / 100
        b, c = base[t], float(r["conversion"])
        m = (c - (1 - o) * b) / o if o >= 0.2 else None  # undefined when almost nothing was served
        orc = oracle.get(t)
        out.append({
            "t": t, "team": r["team_id"], "conv": c, "cold": fnum(r["cold_conversion"]), "on_time": 100 * o,
            "model_conv": m, "revenue": fnum(r["revenue_per_request"]), "rank": int(r["rank"]) if r["rank"] else None,
            "baseline": b, "reference": ref.get(t), "oracle": orc,
            "score": None if orc is None else max(0.0, min(100.0, 100 * (c - b) / (orc - b))),
            "model_version": r["model_version"],
        })
    return out


def arm_windows(versions, teams, oracle):
    """team_37 model versions per 15-min window, normalised by same-window baseline/reference/oracle."""
    by_t = defaultdict(dict)
    for r in teams:
        if r["span_s"] == "900":
            by_t[int(r["t0"])][r["team_id"]] = r
    med_oracle = st.median(oracle.values()) if oracle else None
    out = []
    for v in versions:
        if v["span_s"] != "900" or int(v["requests"]) < 100:
            continue
        t = int(v["t0"])
        b = float(by_t[t]["baseline"]["conversion"])
        rf = float(by_t[t]["reference"]["conversion"])
        orc = oracle.get(t - t % 3600, med_oracle)
        c = float(v["conversion"])
        out.append({
            "t": t, "version": v["model_version"], "requests": int(v["requests"]), "conv": c,
            "cold_requests": int(v["cold_requests"] or 0), "cold_conv": fnum(v["cold_conversion"]),
            "revenue": fnum(v["revenue_per_request"]), "baseline": b, "reference": rf,
            "score": 100 * (c - b) / (orc - b), "vs_reference": c - rf,
            "ref_score": 100 * (rf - b) / (orc - b), "oracle": orc,
            "cold_baseline": fnum(by_t[t]["baseline"]["cold_conversion"]),
            "cold_reference": fnum(by_t[t]["reference"]["cold_conversion"]),
        })
    return out


# ---------------------------------------------------------------- DB derived
REL_ORDER = ["session_earlier_view", "session_last_view", "carted_not_bought", "new_product_other", "other",
             "no_session_views", "bought_before"]


def relation_slot(period):
    rows = load_db(period, "relation_slot")
    return [{"sb": r["sb"], "slot": int(r["slot"]), "relation": r["relation"], "impressions": int(r["impressions"]),
             "clicks": int(r["clicks"]), "purchases": int(r["purchases"])} for r in rows]


def median_polish(table: dict[tuple[str, int], float], rows: list[str], cols: list, iters: int = 10):
    """Tukey's median polish on a two-way table (missing cells skipped). Returns overall, row, col effects, residuals."""
    resid = dict(table)
    overall, reff, ceff = 0.0, {r: 0.0 for r in rows}, {c: 0.0 for c in cols}
    for _ in range(iters):
        for r in rows:
            vals = [resid[(r, c)] for c in cols if (r, c) in resid]
            if vals:
                m = st.median(vals)
                reff[r] += m
                for c in cols:
                    if (r, c) in resid:
                        resid[(r, c)] -= m
        m = st.median(list(ceff.values()))
        overall += m
        for c in cols:
            ceff[c] -= m
        for c in cols:
            vals = [resid[(r, c)] for r in rows if (r, c) in resid]
            if vals:
                m = st.median(vals)
                ceff[c] += m
                for r in rows:
                    if (r, c) in resid:
                        resid[(r, c)] -= m
        m = st.median(list(reff.values()))
        overall += m
        for r in rows:
            reff[r] -= m
    return overall, reff, ceff, resid


def slot_band(slot: int) -> str:
    return "1" if slot == 1 else "2-3" if slot <= 3 else "4-6" if slot <= 6 else "7-10"


def relation_polish(rel_rows):
    """Median polish of log(buys per 1,000 + 0.5) with rows = relation, cols = slot band (team-served)."""
    agg = defaultdict(lambda: [0, 0])
    for r in rel_rows:
        if r["sb"] != "team":
            continue
        a = agg[(r["relation"], slot_band(r["slot"]))]
        a[0] += r["impressions"]
        a[1] += r["purchases"]
    bands = ["1", "2-3", "4-6", "7-10"]
    table = {k: math.log(1000 * v[1] / v[0] + 0.5) for k, v in agg.items() if v[0] >= 500}
    overall, reff, ceff, resid = median_polish(table, REL_ORDER, bands)
    cells = [{"relation": k[0], "band": k[1], "impressions": agg[k][0], "purchases": agg[k][1],
              "per1000": 1000 * agg[k][1] / agg[k][0], "log_rate": table.get(k), "fit": overall + reff[k[0]] + ceff[k[1]]
              if k in table else None, "residual": resid.get(k)} for k in agg]
    return {"overall": overall, "row": reff, "col": ceff, "cells": cells}


def history_slots():
    rows = load_db("practice", "history_slots")
    out = []
    for r in rows:
        s = int(r["slot"])
        if s >= 1:
            out.append({"slot": s, "clicks": int(r["rows_"]), "purchases": int(r["purchases"]), "impressions": 2_000_000})
    return out


def power_curve(arm_rows):
    """Requests per arm needed to detect a relative lift with a two-sided 5 % test and 80 % power,
    (a) with realised purchases (binomial noise) and (b) with the official expected metric
    (empirical between-window noise of the same arm, scaled to a per-request variance)."""
    p = 0.022  # fz-v9a realised ~2.2-2.3 purchases / 100
    z = 1.96 + 0.84
    # per-request SD of the expected metric, estimated from 15-min windows of long-running arms
    per_req_var = []
    groups = defaultdict(list)
    for r in arm_rows:
        groups[r["version"]].append(r)
    for v, rs in groups.items():
        rs = [r for r in rs if r["requests"] >= 300]
        if len(rs) >= 4:
            sd = st.stdev([r["conv"] / 100 for r in rs])
            n = st.mean([r["requests"] for r in rs])
            per_req_var.append(sd * sd * n)
    var_exp = st.median(per_req_var) if per_req_var else None
    out = []
    for lift in [0.05, 0.075, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]:
        d = p * lift
        n_bin = 2 * z * z * p * (1 - p) / (d * d)
        n_exp = 2 * z * z * var_exp / (d * d) if var_exp else None
        out.append({"lift": lift, "n_realised": n_bin, "n_expected": n_exp})
    return {"p": p, "per_request_var_expected": var_exp, "per_request_var_binomial": p * (1 - p), "curve": out,
            "final_requests": 21600}


def main() -> None:
    teams, versions, progress = api_tables()
    oracle = implied_oracle(teams, progress)
    w15 = windows15(teams, versions, oracle)
    field = hourly_field(teams, oracle)
    arms = arm_windows(versions, teams, oracle)
    data = {
        "meta": {
            "built_from": {"practice": db_meta("practice"), "final": db_meta("final")},
            "api_now": json.loads((RAW / "api" / "state_now.json").read_text()).get("updated_at"),
            "final_start": FINAL_START, "final_end": FINAL_END,
        },
        "oracle_hourly": [{"t": t, "oracle": o} for t, o in sorted(oracle.items())],
        "windows15": w15,
        "field_hourly": field,
        "arms15": arms,
        "progress": [{"team": r["team_id"], "t": int(r["t0"]), "score": float(r["score"])} for r in progress],
        "power": power_curve(arms),
        "versions_hourly": [{"t": int(v["t0"]), "version": v["model_version"], "requests": int(v["requests"]),
                             "conv": float(v["conversion"])} for v in versions if v["span_s"] == "3600"],
    }
    for period in ("practice", "final"):
        rel = relation_slot(period)
        if not rel:
            continue
        data[period] = {
            "buckets10m": load_db(period, "buckets10m"),
            "latency_hourly": load_db(period, "latency_hourly"),
            "latency_sample": load_db(period, "latency_sample"),
            "relation_slot": rel,
            "relation_polish": relation_polish(rel),
            "relation_hourly": load_db(period, "relation_hourly"),
            "segments": load_db(period, "segments"),
            "model_hourly": load_db(period, "model_hourly"),
            "writers_hourly": load_db(period, "writers_hourly"),
            "events_category_hourly": load_db(period, "events_category_hourly"),
            "price_changes_hourly": load_db(period, "price_changes_hourly"),
        }
    data["history_slots"] = history_slots()
    # official final aggregate (API mode "final": one window = the whole final, every team)
    fin = RAW / "api" / "state_final.json"
    if fin.exists():
        d = json.loads(fin.read_text())
        data["final_official"] = {"window": d.get("window"), "teams": d.get("teams", []), "baseline": d.get("baseline"),
                                  "reference": d.get("reference"), "updated_at": d.get("updated_at"),
                                  "progress": {k: [x for x in v if FINAL_START <= x[0] < FINAL_END]
                                               for k, v in d.get("progress", {}).items()}}
    for p in sorted(MANUAL.glob("*.json")) if MANUAL.exists() else []:
        data.setdefault("manual", {})[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    (ROOT / "data" / "dashboard_data.json").write_text(json.dumps(data, default=str))
    print("windows15", len(w15), "field", len(field), "arms", len(arms), "oracle hours", len(oracle))
    pw = data["power"]
    print("power var expected/binomial per request: %.5f / %.5f" % (pw["per_request_var_expected"], pw["per_request_var_binomial"]))
    pol = data["practice"]["relation_polish"]
    print("polish overall %.2f" % pol["overall"], {k: round(v, 2) for k, v in pol["row"].items()}, {k: round(v, 2) for k, v in pol["col"].items()})


if __name__ == "__main__":
    main()
