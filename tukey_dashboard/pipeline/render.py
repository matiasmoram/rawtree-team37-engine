"""Render the Tukey dashboard (dist/index.html, offline; dist/artifact.html with --cdn) from data/dashboard_data.json.

Every number in the text comes from one `N` dict per period, computed here from the same tables the charts draw
(coherence by construction; checks at the end of build_period). UI language: Catalan (ca-ES numbers).
Predictions for the final are frozen in data/manual/predictions.json (written once, hashed, never rewritten).
Review rounds that shaped this file: docs/review_r1_jury.md, docs/review_r1_audit.md.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import views  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
VENDOR = Path(__file__).resolve().parent / "vendor"
PRED = ROOT / "data" / "manual" / "predictions.json"
TEAM = "team_37"
FINAL_START, FINAL_END = 1794733200, 1794740400
BAN_T = 1794667800  # Sat 15:50 CET: hard ban of already-bought products (Notion page 8)
CANDIDATES = ("fz-v10-nocorr", "t37-lgbm-recent", "t37-cf-rot")  # alternatives discussed for the final (brief D2)
REL_LABEL = {
    "carted_not_bought": "Al carret, no comprat", "session_earlier_view": "Vist abans a la sessió",
    "new_product_other": "Producte nou", "session_last_view": "Últim vist a la sessió", "other": "Altres",
    "no_session_views": "Sense vistes (home)", "bought_before": "Ja comprat",
}
BANDS = [("1", 1, 1), ("2-3", 2, 3), ("4-6", 4, 6), ("7-10", 7, 10)]
DOW = ["dl", "dt", "dc", "dj", "dv", "ds", "dg"]


# ----------------------------------------------------------------------------- formatting
def f(x, d=2, sign=False) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    s = f"{x:+,.{d}f}" if sign else f"{x:,.{d}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".").replace("-", "−")


def pct(x, d=1) -> str:
    return "–" if x is None else f(x, d) + " %"


def cet(t: float) -> datetime:
    return datetime.fromtimestamp(float(t), tz=timezone.utc) + timedelta(hours=1)


def hm(t: float) -> str:
    return cet(t).strftime("%H:%M")


def dhm(t: float) -> str:
    c = cet(t)
    return f"{DOW[c.weekday()]} {c.strftime('%H:%M')}"


def hh(t: float) -> str:
    c = cet(t)
    return f"{DOW[c.weekday()]} {c.strftime('%H')}h"


def esc(s) -> str:
    return html.escape(str(s), quote=False)


def poisson_cdf(k: int, lam: float) -> float:
    term = total = math.exp(-lam)
    for i in range(1, k + 1):
        term *= lam / i
        total += term
    return total


def garwood(k: int, alpha: float = 0.05):
    """Exact Poisson 95 % interval for a count k (bisection on the Poisson CDF). For k >= 100 exp(-lambda) underflows,
    so the Wilson-Hilferty cube-root approximation is used (error < 0.1 % at that size)."""
    if k >= 100:
        z = 1.959964
        lo = k * (1 - 1 / (9 * k) - z / (3 * math.sqrt(k))) ** 3
        hi = (k + 1) * (1 - 1 / (9 * (k + 1)) + z / (3 * math.sqrt(k + 1))) ** 3
        return lo, hi
    def solve(target, kk, lo, hi):
        for _ in range(80):
            mid = (lo + hi) / 2
            if poisson_cdf(kk, mid) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    return (0.0 if k == 0 else solve(1 - alpha / 2, k - 1, 0, k + 50)), solve(alpha / 2, k, 0, k * 3 + 50)


def wmean(vals, weights):
    pairs = [(v, w) for v, w in zip(vals, weights) if v is not None and w]
    tw = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / tw if tw else None


def in_period(t: float, period: str) -> bool:
    return FINAL_START <= t < FINAL_END if period == "final" else t < FINAL_START


def safe_median(v):
    v = [x for x in v if x is not None]
    return st.median(v) if v else None


# ----------------------------------------------------------------------------- period builder
def build_period(D: dict, period: str, sizes: dict | None = None, with_specs: bool = True) -> dict | None:
    """Every number of one period (N) and, unless with_specs=False (Shiny app), the five Vega-Lite specs."""
    N: dict = {"period": period}
    oracle = {r["t"]: r["oracle"] for r in D["oracle_hourly"]}
    o_med = st.median(oracle.values())
    fh = [r for r in D["field_hourly"] if in_period(r["t"], period)]
    if not any(r["team"] == TEAM for r in fh):
        return None
    span = [st.median([1 / (o - b) for t, o in oracle.items() for b in
                       [next(r["baseline"] for r in D["field_hourly"] if r["t"] == t)]])]
    N["pts_per_conv"] = 100 * span[0]                      # conversion-score points per 1 purchase/100
    N["o_med"] = o_med
    N["oracle_imputed"] = any(r["t"] not in oracle for r in fh)

    # ---------------- hourly field, served-model q (rivals: on-time; zeros with conv > baseline = not reported)
    by_hour = defaultdict(list)
    for r in fh:
        r = dict(r)
        o = r["oracle"] or o_med
        r["o"] = o
        if r["on_time"] == 0 and r["conv"] > r["baseline"] + 0.02:
            r["on_time"] = None                            # not reported, not 0 %
        r["q"] = None if r["model_conv"] is None or r["on_time"] is None else 100 * (r["model_conv"] - r["baseline"]) / (o - r["baseline"])
        by_hour[r["t"]].append(r)
    hours = sorted(by_hour)
    ours = {t: next((r for r in rs if r["team"] == TEAM), None) for t, rs in by_hour.items()}
    hours_us = [t for t in hours if ours.get(t) and ours[t]["q"] is not None and ours[t]["on_time"] >= 20]
    if not hours_us:
        return None
    vh = defaultdict(list)
    for v in D.get("versions_hourly", []):
        if in_period(v["t"], period):
            vh[v["t"]].append(v)
    main_version = {t: max(vs, key=lambda v: v["requests"])["version"] for t, vs in vh.items()}
    # live version = most requests over the last 2 hours of the period (data-driven, not hard-coded)
    last_t = max(vh) if vh else hours_us[-1]
    recent = defaultdict(int)
    for t, vs in vh.items():
        if t >= last_t - 3600:
            for v in vs:
                recent[v["version"]] += v["requests"]
    live = max(recent, key=recent.get) if recent else ours[hours_us[-1]]["model_version"]
    N["live"] = live
    # share of answered requests served by the live version (API per-version counts), last 2 h of the period
    tot_recent = sum(recent.values())
    N["live_share"] = 100 * recent[live] / tot_recent if tot_recent else None

    def model_rank(t):
        pl = sorted([r for r in by_hour[t] if r["q"] is not None and (r["on_time"] or 0) >= 20], key=lambda r: -r["q"])
        return next((i + 1 for i, r in enumerate(pl) if r["team"] == TEAM), None), len(pl)

    sel_t = hours_us[-1]
    me = ours[sel_t]
    rank_m, n_pl = model_rank(sel_t)
    b_h, o_h = me["baseline"], me["o"]
    s = me["on_time"] / 100
    vers = vh.get(sel_t, [])
    q_meas = (100 * (wmean([v["conv"] for v in vers], [v["requests"] for v in vers]) - b_h) / (o_h - b_h)) if vers else None
    bound = 100 * 0.05 / (s * (o_h - b_h))
    ref_q = 100 * (me["reference"] - b_h) / (o_h - b_h)
    rows_h = by_hour[sel_t]
    rivals_rank = sorted([r for r in rows_h if r["team"] != TEAM], key=lambda r: r["rank"] or 99)
    top_names = {r["team"] for r in rivals_rank[:1]}
    field_rows = [{"team": r["team"], "s": r["on_time"], "q": r["q"], "conv": r["conv"], "m": r["model_conv"], "score": r["score"],
                   "rank": r["rank"], "label_detail": f"#{r['rank']} {r['team']}" if r["team"] in top_names else ""}
                  for r in rows_h if r["team"] != TEAM and r["q"] is not None and r["on_time"] >= 20]
    N.update(sel_label=f"{dhm(sel_t)}–{hm(sel_t + 3600)}", sel_s=me["on_time"], sel_conv=me["conv"], sel_rank=me["rank"],
             sel_m=me["model_conv"], sel_q=me["q"], sel_score=me["score"], rank_m=rank_m, n_plotted=n_pl, b_h=b_h, o_h=o_h,
             sel_qmeas=q_meas, ref_q=ref_q,
             dropped=len([r for r in rows_h if r["on_time"] is not None and r["on_time"] < 20]),
             not_reported=len([r for r in rows_h if r["on_time"] is None]))
    # check against the organisers' published progress score for that hour (conversion component)
    prog = {(p["team"], p["t"]): p["score"] for p in D["progress"]}
    pub = prog.get((TEAM, sel_t))
    if pub is not None and me["oracle"]:
        assert abs(pub - 100 * (me["conv"] - b_h) / (o_h - b_h)) < 0.6, "score formula does not reproduce API progress"
    # path: hours since the live family started serving
    fam = live.split("-x")[0][:5]
    start = min([t for t in hours_us if main_version.get(t, "").startswith(fam)] or [hours_us[0]])
    path_rows = []
    for t in hours_us:
        if t < start:
            continue
        r = ours[t]
        path_rows.append({"t": t, "tc": views.cet_ms(t), "s": r["on_time"], "q": r["q"], "conv": r["conv"], "m": r["model_conv"],
                          "rank": r["rank"], "model_version": main_version.get(t, r["model_version"]),
                          "label": f"{dhm(t)}–{hm(t + 3600)}", "end": f"{hh(t)} · {f(r['on_time'], 0)} % · #{r['rank']}",
                          "show_d": t == sel_t})
    best = max((ours[t] for t in hours_us if t >= start), key=lambda r: r["score"] or -1)
    worst = min((ours[t] for t in hours_us if t >= start), key=lambda r: r["on_time"])
    br, bn = model_rank(best["t"])
    wr, wn = model_rank(worst["t"])
    N.update(best_label=f"{hh(best['t'])}", best_s=best["on_time"], best_rank=best["rank"], best_q=best["q"], best_rank_m=br,
             worst_label=f"{hh(worst['t'])}", worst_s=worst["on_time"], worst_rank=worst["rank"], worst_conv=worst["conv"],
             worst_m=worst["model_conv"], worst_q=worst["q"], worst_rank_m=wr, worst_n=wn, path_start=hh(start))
    sel = {"s": me["on_time"], "q": me["q"], "q_lo": me["q"] - bound, "q_hi": me["q"] + bound, "q_meas": q_meas}
    if s > 0.95:  # the identity bound carries no information near full service
        sel["q_lo"] = sel["q_hi"] = me["q"]
    gain_w = max(0.0, (0.98 - worst["on_time"] / 100) * (0.5 * worst["q"] + 10))
    proj = {"s0": worst["on_time"], "s": 98, "q": worst["q"],
            "label": f"mateix model a 98 %|→ +{f(gain_w, 1)} punts finals" if worst["on_time"] < 90 else ""}
    N["gain_worst"] = gain_w
    N["y_min"] = min(-10, math.floor(min([r["q"] for r in field_rows] + [0]) / 10) * 10)

    # ---------------- 15-min windows (team_37): on-time, measured served model, points lost (lower bound)
    W = [dict(r) for r in D["windows15"] if in_period(r["t"], period)]
    last_q = None
    for r in W:
        o = r["oracle"] or o_med
        b = r["baseline"]
        s_w = (r["on_time"] or 0) / 100
        if r["model_conv"] is not None and (r["served_share"] or 0) >= 5:
            r["q"] = 100 * (r["model_conv"] - b) / (o - b)
            r["imputed"] = False
            last_q = r["q"]
        else:
            r["q"], r["imputed"] = last_q, True
        q = max(r["q"] or 0, 0)
        gap = max(0.0, 0.98 - s_w)                       # shortfall against the D1 target (98 %)
        r["lost_conv"] = 0.5 * gap * q
        r["lost_rel"] = 10 * gap
        r["lost"] = r["lost_conv"] + r["lost_rel"]
        r["resid"] = None if r["pred_conv"] is None else r["team_conv"] - r["pred_conv"]
        r["informative"] = r["resid"] is not None and (r["served_share"] or 100) < 99
        r["tc"] = views.cet_ms(r["t"])
        r["label"] = f"{dhm(r['t'])}–{hm(r['t'] + 900)}"
    N["loss_mean"] = wmean([r["lost"] for r in W], [r["requests"] for r in W])
    inf = [r for r in W if r["informative"]]
    N["resid_ok"] = len([r for r in inf if abs(r["resid"]) <= 0.05])
    N["resid_k"] = len(inf)
    N["n_windows"], N["n_requests"] = len(W), sum(r["requests"] for r in W)
    N["w_min"] = min((r["on_time"] for r in W if r["on_time"] is not None), default=None)
    N["worst_loss"] = N["gain_worst"]
    events = []
    for e in D.get("manual", {}).get("events", {}).get("items", []):
        if in_period(e["t"], period):
            events.append({"tc": views.cet_ms(e["t"]), "t": e["label"]})
    runs, cur = [], []
    for r in W:
        if (r["on_time"] or 0) < 50 and (r["served_share"] or 0) < 50:
            cur.append(r)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    if runs:
        big = max(runs, key=lambda rs: sum(x["requests"] * (1 - (x["on_time"] or 0) / 100) for x in rs))
        if big[0]["t"] >= start - 3600:
            events.append({"tc": big[0]["tc"], "t": f"{hm(big[0]['t'])} writer caigut"})
    events.sort(key=lambda e: e["tc"])
    for i, e in enumerate(events):
        e["yy"] = 146 - 13 * (i % 2)
    # Tukey box: hourly on-time of team_37 vs top-6 rivals by API rank (one definition everywhere)
    box_pts, groups = [], {"team_37": [], "top-6": []}
    for t in hours:
        if ours.get(t) and ours[t]["on_time"] is not None:
            groups["team_37"].append(ours[t]["on_time"])
            box_pts.append({"who": "team_37", "v": ours[t]["on_time"], "label": hh(t)})
        for r in sorted([r for r in by_hour[t] if r["team"] != TEAM], key=lambda r: r["rank"] or 99)[:6]:
            if r["on_time"] is not None:
                groups["top-6"].append(r["on_time"])
                box_pts.append({"who": "top-6", "v": r["on_time"], "label": f"{r['team']} {hh(t)}"})
    box_rows, box_text = [], []
    for who, vals in groups.items():
        tk = views.tukey(vals)
        if tk:
            box_rows.append({"who": who, **{k: v for k, v in tk.items() if k != "outliers"}})
            N[f"box_{who}"] = tk
            box_text.append({"who": who, "t": f"{f(tk['min'], 0)}|{f(tk['h1'], 0)}|{f(tk['med'], 0)}|{f(tk['h2'], 0)}|{f(tk['max'], 0)}"})
    for p in box_pts:
        tk = N.get(f"box_{p['who']}")
        p["outlier"] = bool(tk and p["who"] == "team_37" and (p["v"] < tk["lo_fence"] or p["v"] > tk["hi_fence"]))
        p["olabel"] = f"{f(p['v'], 0)} % ({p['label']})|fora de la tanca {f(tk['lo_fence'], 1)}" if p["outlier"] else ""

    # ---------------- arms: versions per 15-min window, normalised; paired comparisons where versions co-ran
    A = [dict(r) for r in D["arms15"] if in_period(r["t"], period)]
    for r in A:
        r["q"], r["ref_q"] = r["score"], r["ref_score"]
        r["dq"] = r["q"] - r["ref_q"]
        r["tc"] = views.cet_ms(r["t"])
        r["label"] = f"{dhm(r['t'])}–{hm(r['t'] + 900)}"
    by_v, by_t = defaultdict(list), defaultdict(dict)
    for r in A:
        by_v[r["version"]].append(r)
        by_t[r["t"]][r["version"]] = r
    last_w = max(by_t) if by_t else 0
    active = {v for v, rs in by_v.items() if max(r["t"] for r in rs) >= last_w - 6 * 3600}
    keep = {v: rs for v, rs in by_v.items() if len(rs) >= 2 and (sum(r["requests"] for r in rs) >= 2500 or v in active or v in CANDIDATES or v == live)}
    if live not in keep and live in by_v:
        keep[live] = by_v[live]
    if live not in keep:
        return None
    med = {v: st.median([r["q"] for r in rs]) for v, rs in keep.items()}
    N["hinges"] = {v: (views.tukey([r["q"] for r in rs])["h1"], views.tukey([r["q"] for r in rs])["h2"]) for v, rs in keep.items()}
    order_active = sorted([v for v in keep if v in active], key=lambda v: -med[v])
    order_retired = sorted([v for v in keep if v not in active], key=lambda v: -med[v])
    REF = "referència (org.)"
    order_all = order_active + [REF] + order_retired
    ticks, boxes, texts, cold = [], [], [], []
    ref_windows = {}
    for v in order_active + order_retired:
        rs = keep[v]
        ret = v not in active
        for r in rs:
            ticks.append({**{k: r[k] for k in ("tc", "label", "requests", "conv", "q", "ref_q", "dq")}, "version": v,
                          "is_ref": False, "retired": ret})
            ref_windows[r["t"]] = r
            if r["cold_requests"] and r["cold_conv"] is not None and r["cold_baseline"]:
                cold.append({"version": v, "label": r["label"], "cold_requests": r["cold_requests"], "retired": ret,
                             "ratio": max(0.5, min(8, r["cold_conv"] / r["cold_baseline"])), "is_ref": False})
        tk = views.tukey([r["q"] for r in rs])
        if tk["n"] >= 5:
            boxes.append({"version": v, **{k: x for k, x in tk.items() if k != "outliers"}})
        texts.append({"version": v, "t": f"{f(st.median([r['dq'] for r in rs]), 0, sign=True)} · {len(rs)}"})
    for t, r in sorted(ref_windows.items()):
        ticks.append({"tc": r["tc"], "label": r["label"], "requests": 2700, "conv": r["reference"], "q": r["ref_q"],
                      "ref_q": r["ref_q"], "dq": 0.0, "version": REF, "is_ref": True, "retired": False})
        if r["cold_reference"] and r["cold_baseline"]:
            cold.append({"version": REF, "label": r["label"], "cold_requests": 999, "retired": False,
                         "ratio": max(0.5, min(8, r["cold_reference"] / r["cold_baseline"])), "is_ref": True})
    tk = views.tukey([r["ref_q"] for r in ref_windows.values()])
    if tk and tk["n"] >= 5:
        boxes.append({"version": REF, **{k: x for k, x in tk.items() if k != "outliers"}})
    texts.append({"version": REF, "t": f"· {len(ref_windows)}"})
    lv = keep[live]
    tkl = views.tukey([r["q"] for r in lv])
    N.update(live_med=tkl["med"], live_h1=tkl["h1"], live_h2=tkl["h2"], live_k=len(lv), live_n=sum(r["requests"] for r in lv),
             live_dq=st.median([r["dq"] for r in lv]), live_conv=wmean([r["conv"] for r in lv], [r["requests"] for r in lv]))
    cl = [r["cold_conv"] / r["cold_baseline"] for r in lv if r["cold_requests"] and r["cold_conv"] is not None and r["cold_baseline"]]
    N["live_cold_ratio"] = safe_median(cl)
    N["ref_cold_ratio"] = safe_median([r["cold_reference"] / r["cold_baseline"] for r in ref_windows.values()
                                       if r["cold_reference"] and r["cold_baseline"]])
    # comparisons with candidates: paired within-window if they co-ran in ≥ 4 windows, else unpaired medians
    width = st.median([(r["oracle"] or o_med) - r["baseline"] for r in A]) / 100   # purchases/100 per q point
    comp = {}
    for c in CANDIDATES:
        if c == live or c not in by_v:
            continue
        shared = [(w[live], w[c]) for w in by_t.values() if live in w and c in w]
        if len(shared) >= 4:
            dconv = [a["conv"] - b["conv"] for a, b in shared]
            d = st.mean(dconv)
            se = st.stdev(dconv) / math.sqrt(len(dconv))
            comp[c] = {"paired": True, "k": len(shared), "dconv": d, "lo": d - 1.96 * se, "hi": d + 1.96 * se,
                       "dq": d / width}
        else:
            dq = med[live] - st.median([r["q"] for r in by_v[c]])
            comp[c] = {"paired": False, "k": len(by_v[c]), "dconv": dq * width, "dq": dq}
    N["comp"] = comp
    N["width"] = width
    # re-buy ban effect (before/after; different hours, so exploratory)
    ev1, ev2 = by_v.get("t37-ev-v1"), by_v.get("t37-ev-v2")
    N["d3_gain"] = 0.5 * (st.median([r["q"] for r in ev2]) - st.median([r["q"] for r in ev1])) if ev1 and ev2 else None
    N["ev1_conv"] = wmean([r["conv"] for r in ev1], [r["requests"] for r in ev1]) if ev1 else None
    N["ev2_conv"] = wmean([r["conv"] for r in ev2], [r["requests"] for r in ev2]) if ev2 else None

    # ---------------- relations x slot (median polish), DB block (optional)
    block = D.get(period) or {}
    rel = [r for r in block.get("relation_slot", []) if r["sb"] == "team"]
    pol = block.get("relation_polish")
    cells, rel_order, labels = [], [], {}
    sb, si = defaultdict(int), defaultdict(int)
    for r in rel:
        sb[r["slot"]] += r["purchases"]
        si[r["slot"]] += r["impressions"]
    tot_buys = sum(sb.values())
    N["slot1_share"] = 100 * sb[1] / tot_buys if tot_buys else None
    N["slot910_share"] = 100 * (sb[9] + sb[10]) / tot_buys if tot_buys else None
    r1 = 1000 * sb[1] / si[1] if si[1] else None
    r710 = 1000 * sum(sb[k] for k in range(7, 11)) / sum(si[k] for k in range(7, 11)) if si[7] else None
    N["slot1_vs_710"] = r1 / r710 if r1 and r710 else None
    N["slot10_rate"] = 1000 * sb[10] / si[10] if si[10] else None
    share = defaultdict(int)
    for r in rel:
        share[r["relation"]] += r["impressions"]
    tot_imp = sum(share.values())
    if pol and rel:
        rel_order = sorted(pol["row"], key=lambda k: -pol["row"][k])
        for rname in rel_order:
            rs1 = [r for r in rel if r["relation"] == rname and r["slot"] == 1]
            imp1 = sum(r["impressions"] for r in rs1)
            k1 = sum(r["purchases"] for r in rs1)
            labels[rname] = (f"{REL_LABEL[rname]}|slot 1: {f(1000 * k1 / imp1, 1) if imp1 else '–'} per 1.000|"
                             f"{f(100 * share[rname] / tot_imp, 1)} % dels slots")
            for band, a, b in BANDS:
                rs = [r for r in rel if r["relation"] == rname and a <= r["slot"] <= b]
                imp = sum(r["impressions"] for r in rs)
                k = sum(r["purchases"] for r in rs)
                if imp < 500:
                    continue
                lo, hi = garwood(k)
                rate = 1000 * k / imp
                fit_r = math.exp(pol["overall"] + pol["row"][rname] + pol["col"][band]) - 0.5
                res = (rate + 0.5) / (fit_r + 0.5)
                cells.append({"relation": rname, "rel_name": REL_LABEL[rname], "rel_label": labels[rname], "band": band,
                              "x": (a + b) / 2, "x0": a - 0.4, "x1": b + 0.4, "impressions": imp, "buys": k, "rate": rate,
                              "lo_r": 1000 * lo / imp, "hi_r": 1000 * hi / imp, "fit_r": fit_r, "res": res,
                              "obs_y": rate + 0.5, "lo_y": 1000 * lo / imp + 0.5, "hi_y": 1000 * hi / imp + 0.5,
                              "fit_y": max(fit_r, 0) + 0.5, "res_label": ("×" + f(res, 1)) if abs(math.log(res)) >= 0.4 else ""})
        c_ev = next((c for c in cells if c["relation"] == "session_earlier_view" and c["band"] == "1"), None)
        c_bb = next((c for c in cells if c["relation"] == "bought_before" and c["band"] == "1"), None)
        N.update(ev1=c_ev and c_ev["rate"], ev1_res=c_ev and c_ev["res"], bb1=c_bb and c_bb["rate"],
                 bb_total=sum(r["purchases"] for r in rel if r["relation"] == "bought_before"), bb_imp=share["bought_before"])
    rh = [r for r in block.get("relation_hourly", []) if r["sb"] == "team"]

    def bb_share(cond):
        tot = sum(int(r["impressions"]) for r in rh if cond(int(r["h"])))
        bb = sum(int(r["impressions"]) for r in rh if cond(int(r["h"])) and r["relation"] == "bought_before")
        return 100 * bb / tot if tot else None
    N["bb_pre"] = bb_share(lambda h: h < BAN_T - 1800)
    N["bb_post"] = bb_share(lambda h: h >= BAN_T - 1800)
    N["bb_all"] = bb_share(lambda h: True)
    hist = D.get("manual", {}).get("history_vs_live", {}).get("rows", [])
    N["hist_rebuy_pct"] = next((r["history"] for r in hist if r["signal"].startswith("Already-bought")), None)
    # exploration of fz-v9a: ≈ 30 % of requests put an exploratory item in slot 10 (Notion) — upper-bound cost
    if N["slot10_rate"] is not None:
        conv_loss = 0.30 * N["slot10_rate"] / 1000 * 100
        N["explore_cost"] = 0.5 * N["pts_per_conv"] * conv_loss
    else:
        N["explore_cost"] = None
    # latency and writers (DB) for subtitles, not typed by hand
    lat = block.get("latency_hourly", [])
    p95 = [row["q"][5] for row in lat if row.get("q")]
    N["p95_lo"], N["p95_hi"] = (min(p95) / 1000, max(p95) / 1000) if p95 else (None, None)
    wr_ = block.get("writers_hourly", [])
    mv = [100 * int(r["multi_version"]) / int(r["requests"]) for r in wr_ if int(r["requests"])]
    N["multi_max"] = max(mv) if mv else None

    # ---------------- power (G4); p from the live version
    pw = D["power"]
    var_e = pw["per_request_var_expected"]
    p = (N["live_conv"] or 2.2) / 100
    var_r = p * (1 - p)
    n_final = round((FINAL_END - FINAL_START) * 3)
    curve = []
    grid = [round(10 ** (math.log10(500) + i * (math.log10(3e6) - math.log10(500)) / 60)) for i in range(61)]
    for n in grid:
        for metric, var in (("esperada", var_e), ("real", var_r)):
            curve.append({"n": n, "metric": metric, "mde": 2.80 * math.sqrt(4 * var / n) * 100, "minutes": n / 180, "label": ""})
    for c in curve:
        if c["n"] == grid[44]:
            c["label"] = "mètrica oficial (esperada)" if c["metric"] == "esperada" else "compres reals"
    N["mde_e"] = 2.80 * math.sqrt(4 * var_e / n_final) * 100
    N["mde_r"] = 2.80 * math.sqrt(4 * var_r / n_final) * 100
    N["var_ratio"] = var_r / var_e
    N["n_final"] = n_final
    gaps = []
    for c, cmp_ in sorted(comp.items(), key=lambda kv: kv[1]["dconv"]):
        d = abs(cmp_["dconv"])
        if c == "t37-lgbm-recent":
            continue  # shown in V3; keeps V5 labels legible
        if d < 0.005:
            continue
        n_star = 31.36 * var_e / (d / 100) ** 2
        cmp_["n_star"] = n_star
        dur = (f"{f(n_star / 180 / 60 / 24, 0)} dies" if n_star > 180 * 60 * 24 else
               f"{f(n_star / 180 / 60, 1)} h" if n_star > 180 * 60 else f"{f(n_star / 180, 0)} min")
        tag = c.replace("t37-", "")
        gaps.append({"mde": d, "n_star": n_star, "kind": "model",
                     "t": f"{tag}{' (aparellat)' if cmp_['paired'] else ''}: Δ {f(d, 2)} → {f(n_star / 1000, 0) if n_star < 1e6 else f(n_star / 1e6, 1)} {'k' if n_star < 1e6 else 'M'} pet. ({dur})"})
    drop = best["conv"] - worst["conv"]
    if drop > 0.05:
        gaps.append({"mde": drop, "n_star": None, "kind": "lost", "t": f"efecte d'una caiguda ({N['worst_label']}): Δ {f(drop, 2)}"})
    gaps.sort(key=lambda g: g["mde"])
    prev = None
    for g in gaps:
        g["dy"] = -2
        if prev is not None and g["mde"] / prev["mde"] < 1.35:
            g["dy"] = prev["dy"] - 13 if prev["dy"] <= -2 else -2
        prev = g
    N["drop"] = drop

    # ---------------- decision stakes, in final points out of 100 (lower bounds: cold component not included)
    q_live = N["live_med"]
    s_med = N["box_team_37"]["med"] / 100
    N["per_pp"] = 0.01 * (0.5 * q_live + 10)
    N["d1_lo"] = max(0.0, (0.98 - s_med) * (0.5 * worst["q"] + 10))
    N["d1_hi"] = N["gain_worst"]
    N["d2"] = {c.replace("t37-", ""): 0.5 * v["dq"] for c, v in comp.items()}
    N["d6"] = {c.replace("t37-", ""): 0.25 * v["dq"] for c, v in comp.items()}

    # ---------------- status (DB, last 30 min of the period) for the "during the final" block
    bk = block.get("buckets10m", [])
    if bk:
        last3 = bk[-4:-1] if len(bk) >= 4 else bk
        req = sum(int(b["requests"]) for b in last3)
        N["status_served"] = 100 * sum(int(b["served_team"]) for b in last3) / req if req else None
        N["status_t"] = f"{hm(int(last3[0]['t']))}–{hm(int(last3[-1]['t']) + 600)}"
        N["status_p95"] = safe_median([b["p95_ms"] for b in last3 if b.get("p95_ms")])
    mh = [r for r in block.get("model_hourly", []) if not r["model_version"].startswith("(")]
    if mh:
        lt = max(int(r["t"]) for r in mh)
        rows = [r for r in mh if int(r["t"]) == lt]
        tot = sum(int(r["requests"]) for r in rows)
        top = max(rows, key=lambda r: int(r["requests"]))
        N["status_version"], N["status_version_share"] = top["model_version"], 100 * int(top["requests"]) / tot if tot else None

    assert abs(N["per_pp"] * 100 - (0.5 * q_live + 10)) < 1e-9
    N["d1_lo"] = min(N["d1_lo"], N["d1_hi"])
    if not with_specs:   # building the specs is ~95 % of the cost; the Shiny app draws its own charts
        return {"N": N, "specs": {}}
    sz = sizes or {}
    specs = {
        "v1": views.v1_field(field_rows, path_rows, sel, [20, 40, 60, 80], ref_q, proj, y_min=N["y_min"], **sz.get("v1", {})).to_dict(),
        "v2": views.v2_reliability([{k: r.get(k) for k in ("tc", "label", "requests", "on_time", "model_conv", "team_conv", "q",
                                                         "lost_conv", "lost_rel", "lost", "resid", "top6_h1", "top6_med", "top6_h2")}
                                    for r in W], events, box_rows, box_pts, box_text, **sz.get("v2", {})).to_dict(),
        "v3": views.v3_models(ticks, boxes, texts, order_all, cold, **sz.get("v3", {})).to_dict(),
        "v4": views.v4_relations(cells, rel_order, labels, **sz.get("v4", {})).to_dict() if cells else None,
        "v5": views.v5_power(curve, gaps, n_final, **sz.get("v5", {})).to_dict(),
    }
    return {"N": N, "specs": specs}


# ----------------------------------------------------------------------------- final from the DB only
def real_rate(k: int, n: int):
    """Realised purchases per 100 requests with an exact Poisson 95 % interval."""
    if not n:
        return None
    lo, hi = garwood(int(k))
    return {"k": int(k), "n": int(n), "rate": 100 * k / n, "lo": 100 * lo / n, "hi": 100 * hi / n}


def realised_by_version(D: dict, period: str) -> dict:
    agg = defaultdict(lambda: [0, 0])
    for r in (D.get(period) or {}).get("model_hourly", []):
        a = agg[r["model_version"]]
        a[0] += int(r["purchases"])
        a[1] += int(r["requests"])
    return {v: real_rate(k, n) for v, (k, n) in agg.items()}


def segment_rate(D: dict, period: str, dim: str, val: str, sb: str):
    rows = [r for r in (D.get(period) or {}).get("segments", []) if r["dim"] == dim and r["val"] == val and r["sb"] == sb]
    return real_rate(sum(int(r["purchases"]) for r in rows), sum(int(r["requests"]) for r in rows))


def final_official(D: dict) -> dict:
    """Official final numbers from the API aggregate: conversion, rank, cold ratio and q (score) of every team.
    The API publishes the conversion component of the score per hour (progress); with on-time ~100 % the conversion score
    equals q, and the final oracle is implied by o = b + 100·(c − b)/score."""
    fo = D.get("final_official")
    if not fo or not fo.get("teams"):
        return {}
    b, ref = fo["baseline"], fo["reference"]
    score = {k: st.mean([x[1] for x in v]) for k, v in fo.get("progress", {}).items() if v}
    teams = []
    for t in fo["teams"]:
        teams.append({"team": t["team_id"], "conv": t["conversion"], "on_time": t.get("on_time"),
                      "cold": t.get("cold_conversion"), "revenue": t.get("revenue_per_request"),
                      "version": t.get("model_version"), "score": score.get(t["team_id"])})
    teams.sort(key=lambda r: -r["conv"])
    for i, r in enumerate(teams):
        r["rank"] = i + 1
    me = next((r for r in teams if r["team"] == TEAM), None)
    if not me:
        return {}
    o = b["conversion"] + 100 * (me["conv"] - b["conversion"]) / me["score"] if me.get("score") else None
    q = (lambda c: 100 * (c - b["conversion"]) / (o - b["conversion"])) if o else (lambda c: None)
    return {"has_api": True, "official": True, "sel_rank": me["rank"], "n_teams": len(teams), "sel_conv": me["conv"],
            "official_on_time": me["on_time"], "official_score": me.get("score"), "o_final": o,
            "live_med": q(me["conv"]), "live_cold_ratio": me["cold"] / b["cold_conversion"] if me["cold"] else None,
            "ref_conv": ref["conversion"], "ref_q_final": q(ref["conversion"]), "base_conv": b["conversion"],
            "ref_cold_ratio_final": ref["cold_conversion"] / b["cold_conversion"], "field_final": teams,
            "top_conv": teams[0]["conv"], "top_team": teams[0]["team"]}


def build_final_db(D: dict, P: dict, sizes: dict | None = None, with_specs: bool = True) -> dict | None:
    """Fallback when the public API does not (yet) publish the final windows: reliability, relations and version
    shares straight from RawTree (team_37.feedback / submissions). Model quality (D2, D5) stays 'pendent (API)'."""
    block = D.get("final") or {}
    bk = [b for b in block.get("buckets10m", []) if int(b["requests"]) > 0]
    if not bk:
        return None
    PN = P["N"]
    N = {"period": "final", "source": "db", "live_med": None, "live_cold_ratio": None}
    q = PN["live_med"]
    rows = []
    for b in bk:
        req = int(b["requests"])
        s_w = int(b["served_team"]) / req
        gap = max(0.0, 0.98 - s_w)
        rows.append({"tc": views.cet_ms(int(b["t"])), "label": f"{dhm(int(b['t']))}–{hm(int(b['t']) + 600)}", "requests": req,
                     "on_time": 100 * s_w, "model_conv": None, "q": q,
                     "team_conv": 100 * int(b["purchases"]) / req, "lost_conv": 0.5 * gap * q, "lost_rel": 10 * gap,
                     "lost": gap * (0.5 * q + 10), "resid": None, "top6_h1": None, "top6_med": None, "top6_h2": None})
    N["w_min"] = min(r["on_time"] for r in rows)
    N["loss_mean"] = wmean([r["lost"] for r in rows], [r["requests"] for r in rows])
    N["served_total"] = 100 * sum(int(b["served_team"]) for b in bk) / sum(int(b["requests"]) for b in bk)
    N["n_requests"] = sum(r["requests"] for r in rows)
    N["realised"] = 100 * sum(int(b["purchases"]) for b in bk) / N["n_requests"]
    N["window"] = f"{dhm(int(bk[0]['t']))}–{hm(int(bk[-1]['t']) + 600)}"
    hourly = defaultdict(lambda: [0, 0])
    for b in bk:
        h = int(b["t"]) - int(b["t"]) % 3600
        hourly[h][0] += int(b["served_team"])
        hourly[h][1] += int(b["requests"])
    hv = [100 * a / t for a, t in hourly.values() if t]
    tk = views.tukey(hv)
    box_rows = [{"who": "team_37", **{k: v for k, v in tk.items() if k != "outliers"}}]
    box_pts = [{"who": "team_37", "v": 100 * a / t, "label": hh(h), "outlier": False, "olabel": ""} for h, (a, t) in sorted(hourly.items())]
    mh = [r for r in block.get("model_hourly", []) if not r["model_version"].startswith("(")]
    agg = defaultdict(int)
    for r in mh:
        agg[r["model_version"]] += int(r["requests"])
    tot = sum(agg.values())
    if tot:
        N["live"] = max(agg, key=agg.get)
        N["live_share"] = 100 * agg[N["live"]] / tot
    rel = [r for r in block.get("relation_slot", []) if r["sb"] == "team"]
    sb, share = defaultdict(int), defaultdict(int)
    for r in rel:
        sb[r["slot"]] += r["purchases"]
        share[r["relation"]] += r["impressions"]
    tb, ti = sum(sb.values()), sum(share.values())
    N["slot1_share"] = 100 * sb[1] / tb if tb else None
    N["bb_all"] = 100 * share["bought_before"] / ti if ti else None
    N["n_windows"] = len(rows)
    N["windows"] = rows
    N["t_first"], N["t_last"] = int(bk[0]["t"]), int(bk[-1]["t"]) + 600
    t1 = (D.get("meta", {}).get("built_from", {}).get("final") or {}).get("t1_utc")
    if t1:   # the last bucket is partial while the final runs: report the extraction time, not the bucket end
        N["t_last"] = min(N["t_last"], int(datetime.strptime(t1, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()))
    N["complete"] = N["t_last"] >= FINAL_END - 60
    # realised purchases (noisy but available before the API publishes the official expected metric)
    N["real"] = real_rate(sum(int(b["purchases"]) for b in bk), N["n_requests"])
    N["real_prac"] = realised_by_version(D, "practice")
    N["real_prac_live"] = N["real_prac"].get(N.get("live"))
    N["real_prac_prev"] = N["real_prac"].get(PN.get("live")) if PN.get("live") != N.get("live") else None
    N["prev_live"] = PN.get("live")
    cold_f = real_rate(sum(int(b["cold_purchases"]) for b in bk), sum(int(b["cold_requests"]) for b in bk))
    cold_b = segment_rate(D, "practice", "cold", "true", "fallback")   # the baseline list, served as fallback
    N["cold_real"], N["cold_base_real"] = cold_f, cold_b
    N["cold_ratio_real"] = cold_f["rate"] / cold_b["rate"] if cold_f and cold_b and cold_b["rate"] else None
    lat = block.get("latency_hourly", [])
    p95f = [row["q"][5] for row in lat if row.get("q")]
    N["p95_final"] = max(p95f) / 1000 if p95f else None
    N["over_3000"] = sum(int(row.get("over_3000") or 0) for row in lat)
    N["p95_lo"], N["p95_hi"] = PN.get("p95_lo"), PN.get("p95_hi")
    wr_ = block.get("writers_hourly", [])
    N["multi_submission"] = sum(int(r["multi_submission"]) for r in wr_)
    N["multi_version"] = sum(int(r["multi_version"]) for r in wr_)
    N["missing"] = sum(int(b["missing"]) + int(b["invalid"]) for b in bk)
    N["late_or_missing"] = N["n_requests"] - sum(int(b["served_team"]) for b in bk)
    # practice reliability on the same 10-min grid, for the before/after comparison
    pb = [b for b in (D.get("practice") or {}).get("buckets10m", []) if int(b["requests"]) >= 300]
    N["prac_w"] = [100 * int(b["served_team"]) / int(b["requests"]) for b in pb]
    N["prac_box"], N["final_box"] = views.tukey(N["prac_w"]), views.tukey([r["on_time"] for r in rows])
    N["prac_served"] = 100 * sum(int(b["served_team"]) for b in pb) / sum(int(b["requests"]) for b in pb) if pb else None
    N["prac_below95"] = 100 * sum(1 for v in N["prac_w"] if v < 95) / len(N["prac_w"]) if N["prac_w"] else None
    N["final_below98"] = sum(1 for r in rows if r["on_time"] < 98)
    N.update(final_official(D))
    if not with_specs:
        return {"N": N, "specs": {}}
    events = []
    specs = {"v2": views.v2_reliability(rows, events, box_rows, box_pts, [], **(sizes or {}).get("v2", {})).to_dict()}
    return {"N": N, "specs": specs}


def page_body_db(F: dict, rows: list[dict], pred: dict) -> str:
    N = F["N"]
    stakes = [v for r in rows for _, v in r.get("ticks", []) if v is not None]
    scale_max = max(5.0, math.ceil(max(stakes + [1]) / 5) * 5)
    axis, ledger = ledger_html(rows, scale_max)
    reg = f"PRE-REGISTRAT {pred['registered_at_cet']} · sha {pred['sha256'][:8]}"
    h2 = (f"Final ({N['window']} CET): {pct(N['served_total'], 1)} de les peticions respostes a temps; "
          f"pitjor finestra de 10 min {pct(N['w_min'], 0)}; versió principal {N.get('live', '–')} "
          f"({pct(N.get('live_share'), 0)} de les respostes).")
    v2t = (f"Fiabilitat a la final: {pct(N['served_total'], 1)} servit a temps; quedar per sota del 98 % ens ha costat "
           f"≥ {f(N['loss_mean'], 1)} punts finals (q de pràctica)")
    v2s = (f"Font: base de dades RawTree (team_37.feedback), finestres de 10 min; les respostes tardanes compten com a no "
           f"respostes, igual que a l'on-time oficial. La qualitat del model i la comparació amb els rivals (V1, V3) "
           f"s'afegiran quan l'API publiqui les finestres de la final. n = {f(N['n_requests'], 0)} peticions; compres "
           f"reals {f(N['realised'], 2)} per 100.")
    return f"""
<div class="period" data-period="final">
  <section class="verdict" aria-label="Resultat de la final"><h2>{esc(h2)}</h2>
    <p class="ruler">Comprovació de les prediccions registrades abans de la final ({esc(reg)}). D2 i D5 necessiten la mètrica
    oficial per versió de l'API: queden pendents fins que es publiqui.</p></section>
  <div class="row">
    <section class="view ledger" id="final-v6" aria-labelledby="final-v6-t">
      <header><span class="vid">V6</span><span class="badge b-confirmatori">CONFIRMATORI</span>
      <h3 id="final-v6-t">Prediccions de la final contrastades</h3></header>
      <table><thead><tr><th>Decisió</th><th>Punts en joc<div class="axis">{axis}</div></th><th>Predicció registrada</th><th>Final</th></tr></thead>
      <tbody>{ledger}</tbody></table>
    </section>
  </div>
  <div class="row">{section("v2", v2t, v2s, "CONFIRMATORI", "wide", "final")}</div>
</div>"""


# ----------------------------------------------------------------------------- frozen predictions
def predictions(P: dict) -> dict:
    """Write predictions once (before the final) and never rewrite them; verify the hash on every build."""
    if PRED.exists():
        doc = json.loads(PRED.read_text(encoding="utf-8"))
        body = json.dumps(doc["items"], sort_keys=True, ensure_ascii=False)
        assert hashlib.sha256(body.encode()).hexdigest() == doc["sha256"], "predictions.json was modified after registration"
        return doc
    N = P["N"]
    items = {
        "D1": {"text": "on-time ≥ 98 % a cada finestra de 15 min de la final", "metric": "w_min", "op": ">=", "value": 98.0},
        "D2": {"text": f"q de {N['live']} dins {f(N['live_h1'], 0)}–{f(N['live_h2'], 0)} (frontisses de pràctica)",
               "metric": "live_med", "op": "between", "value": [round(N["live_h1"], 2), round(N["live_h2"], 2)], "version": N["live"]},
        "D3": {"text": "slot 1 ≥ 35 % de les compres; ja comprat ≤ 1,5 % dels slots", "metric": "slot1_share,bb_all",
               "op": "custom", "value": [35.0, 1.5]},
        "D4": {"text": "no mesurable a la final (no hi ha marca d'exploració a les dades)", "metric": None, "op": "none"},
        "D5": {"text": "conversió freda ≥ ×2,0 la baseline freda", "metric": "live_cold_ratio", "op": ">=", "value": 2.0},
        "D6": {"text": "una sola versió serveix ≥ 95 % de les peticions respostes", "metric": "live_share", "op": ">=", "value": 95.0},
    }
    reg = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%d/%m %H:%M")
    body = json.dumps(items, sort_keys=True, ensure_ascii=False)
    doc = {"registered_at_cet": reg, "sha256": hashlib.sha256(body.encode()).hexdigest(), "items": items,
           "note": "Written once before the final by pipeline/render.py; render refuses to run if this file changes."}
    PRED.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def outcomes(pred: dict, F: dict | None, P: dict | None = None) -> dict:
    if not F:
        return {}
    FN, out = F["N"], {}
    hinges = (P or {}).get("N", {}).get("hinges", {})
    for k, it in pred["items"].items():
        if it["op"] == "none":
            out[k] = ("~", "no mesurable")
            continue
        if k == "D3":
            s1, bb = FN.get("slot1_share"), FN.get("bb_all")
            if s1 is None or bb is None:
                out[k] = ("…", "pendent (dades de la base de dades)")
            else:
                out[k] = ("✓" if s1 >= it["value"][0] and bb <= it["value"][1] else "✗", f"slot 1 {pct(s1, 0)} · ja comprat {pct(bb, 1)}")
            continue
        v = FN.get(it["metric"])
        if k == "D2" and FN.get("live") and FN.get("live") != it.get("version"):
            served = FN["live"]
            h = hinges.get(served)
            q = FN.get("live_med")
            if q is None or not h:
                rf, rp = FN.get("real"), FN.get("real_prac_live")
                if rf and rp:
                    inside = rp["lo"] <= rf["rate"] <= rp["hi"] or rf["lo"] <= rp["rate"] <= rf["hi"]
                    out[k] = ("~", f"es va servir {served} (decisió de les 09:43; empat a la pràctica): {f(rf['rate'], 2)} "
                                   f"compres reals/100 a la final (IC95 {f(rf['lo'], 2)}–{f(rf['hi'], 2)}) vs {f(rp['rate'], 2)} "
                                   f"a la pràctica: {'compatible' if inside else 'diferent'}; q oficial pendent de l'API")
                else:
                    out[k] = ("~", f"decisió canviada a les 09:43: es va servir {served} (empat a la pràctica)")
            else:
                inside = h[0] <= q <= h[1]
                ctx = ""
                if FN.get("ref_q_final") is not None:
                    ctx = (f"; la referència de l'organització també va baixar (q {f(FN['ref_q_final'], 0)}): la final "
                           f"era més difícil, i quedem a {f(FN['sel_conv'] - FN['ref_conv'], 2, sign=True)} compres/100 de la referència")
                out[k] = ("✗" if not inside else "✓", f"es va servir {served} (decisió de les 09:43; empat a la pràctica): q oficial "
                               f"{f(q, 0)} {'dins' if inside else 'fora de'} les seves frontisses de pràctica {f(h[0], 0)}–{f(h[1], 0)}{ctx}")
            continue
        if v is None and k == "D5" and FN.get("cold_ratio_real") is not None:
            r = FN["cold_ratio_real"]
            out[k] = ("✓" if r >= it["value"] else "✗",
                      f"×{f(r, 1)} amb compres reals ({f(FN['cold_real']['rate'], 2)} vs {f(FN['cold_base_real']['rate'], 2)} "
                      f"per 100 de la llista baseline a la pràctica); mètrica oficial pendent de l'API")
            continue
        if v is None:
            out[k] = ("…", "pendent de l'API")
            continue
        ok = (it["value"][0] <= v <= it["value"][1]) if it["op"] == "between" else v >= it["value"]
        unit = {"w_min": " %", "live_share": " %"}.get(it["metric"], "")
        note = {"D1": (" a la pitjor finestra de 10 min" if FN.get("source") == "db" else " a la pitjor finestra de 15 min"),
                "D6": f" de les respostes ({FN.get('live', '')})"}.get(k, "")
        out[k] = ("✓" if ok else "✗", f"{'×' if k == 'D5' else ''}{f(v, 1 if k != 'D2' else 0)}{unit}{note}")
    return out


# ----------------------------------------------------------------------------- text (Catalan)
def texts(P: dict, pred: dict, final_mode: bool) -> dict:
    N = P["N"]
    t = {}
    cnd = {k.replace("t37-", ""): v for k, v in N["comp"].items()}
    tie = cnd.get("fz-v10-nocorr")
    if N["worst_rank"] - N["best_rank"] >= 3:
        t["h1"] = (f"La fiabilitat ens costa més que el model: amb el mateix model érem #{N['best_rank']} amb el "
                   f"{pct(N['best_s'], 0)} de respostes a temps ({N['best_label']}) i #{N['worst_rank']} amb el {pct(N['worst_s'], 0)} "
                   f"({N['worst_label']}).")
    else:
        t["h1"] = (f"Model servit #{N['rank_m']} de {N['n_plotted']} en qualitat i {pct(N['sel_s'], 0)} de respostes a temps: "
                   f"#{N['sel_rank']} a {N['sel_label']}.")
    t["legend"] = ("Grau d'evidència de cada vista: EXPLORATORI = patró trobat a la pràctica · PRE-REGISTRAT = regla o "
                   "predicció fixada abans de la final · CONFIRMATORI = comprovat amb dades noves (la final).")
    t["ruler"] = (f"Moneda única: punts finals sobre 100. 1 compra més per cada 100 peticions ≈ {f(N['pts_per_conv'], 0)} punts de "
                  f"conversió = {f(N['pts_per_conv'] / 2, 0)} punts finals · +1 punt percentual d'on-time ≈ {f(N['per_pp'], 2)} "
                  f"punts finals (amb q = {f(N['live_med'], 0)}).")
    cfg = next((i for i in json.loads((ROOT / "data" / "manual" / "decisions.json").read_text(encoding="utf-8"))["items"]
                if i["id"] == "final-config"), None)
    cand_txt = " · ".join(f"{k} {f(-v, 1, sign=True)}" for k, v in sorted(N["d2"].items(), key=lambda kv: -kv[1]))
    t["verdict"] = [
        ("D1", "Fiabilitat primer",
         f"Un sol procés que envia les respostes (writer) i un de reserva en una altra xarxa; objectiu ≥ 98 % per finestra. "
         f"Cada punt percentual d'on-time val {f(N['per_pp'], 2)} punts finals.", "V1 · V2"),
        ("D2 · D6", "Congelar el model, sense repartir el trànsit",
         (f"fz-v9a i fz-v10-nocorr empaten ({tie['k']} finestres aparellades, Δ {f(tie['dconv'], 2, sign=True)} compres/100); "
          if tie and tie.get("paired") else f"Servir {N['live']}; ")
         + (f"l'equip va congelar {cfg['version']} a les {cfg['t_cet'][-5:]} (commit {cfg['commit']}), coherent amb l'empat. "
            if cfg else "")
         + f"Un 50/50 a la final només veuria diferències ≥ {f(N['mde_e'], 2)}.", "V3 · V5"),
        ("D3 · D4", "La posició 1 decideix",
         f"El slot 1 fa el {pct(N['slot1_share'], 0)} de les compres: a dalt, productes vistos a la sessió i al carret; mai ja "
         f"comprats. L'exploració actual al slot 10 costa ≤ {f(N['explore_cost'], 1)} punts.", "V4"),
    ]
    t["watch_head"] = "95 % = llindar d'acció · 98 % = objectiu de D1"
    t["watch"] = [
        ("On-time d'una finestra de 15 min < 95 %", "passar al writer de reserva", f"cada pp = {f(N['per_pp'], 2)} punts"),
        ("Una versió serveix < 95 % de les peticions", "revisar el desplegament: dos writers alhora", "D6"),
        ("Latència p95 > 2,5 s", "xarxa: el model triga mil·lisegons", f"pràctica p95 {f(N['p95_lo'], 1)}–{f(N['p95_hi'], 1)} s"),
        ("Residu de la identitat fora de ±0,05", "dades o API: no fiar-se dels números", "V2"),
    ]
    st_txt = []
    if N.get("status_served") is not None:
        st_txt.append(f"{pct(N['status_served'], 1)} servit per nosaltres ({N['status_t']})")
    if N.get("status_version"):
        st_txt.append(f"versió principal {N['live']} ({pct(N['live_share'], 0)} de les respostes les 2 darreres hores, API)")
    if (N.get("live_share") or 100) < 95:
        t["alarm"] = (f"⚠ ACTIU: el disparador de D6 ja salta ({N['live']} serveix el {pct(N['live_share'], 0)} de les respostes): "
                      f"tancar el repartiment entre versions abans de les 10:00.")
    if N.get("status_p95"):
        st_txt.append(f"p95 {f(N['status_p95'] / 1000, 1)} s")
    t["status"] = " · ".join(st_txt)
    t["v1_title"] = (f"Ens movem en horitzontal: a {N['worst_label']} el model servit feia {f(N['worst_m'])} compres/100 "
                     f"(#{N['worst_rank_m']} de {N['worst_n']} en qualitat) però l'on-time del {pct(N['worst_s'], 0)} ens va "
                     f"deixar #{N['worst_rank']}; tornar al 98 % amb el mateix model valia +{f(N['gain_worst'], 1)} punts finals")
    t["v1_sub"] = (f"Cada punt és un equip a {N['sel_label']} CET; a la dreta, detall de 90–100 %. Eix vertical: qualitat del "
                   f"model quan respon, q = 100·(m̂ − baseline)/(oracle − baseline) (baseline {f(N['b_h'])}, oracle {f(N['o_h'])} "
                   f"compres/100). Corbes: puntuació de conversió = on-time × q. Camí blau: team_37 hora a hora des de "
                   f"{N['path_start']}. × = q mesurada per versió a l'API. Per als rivals m̂ suposa que les peticions no respostes "
                   f"converteixen com la baseline. {N['dropped']} equips amb on-time < 20 % i {N['not_reported']} sense dada no es "
                   f"mostren; buits = on-time < 50 %.")
    box, tb = N["box_team_37"], N["box_top-6"]
    t["v2_title"] = (f"Si la final fos com la pràctica, quedar per sota del 98 % ens costaria ≥ {f(N['loss_mean'], 1)} punts finals; "
                     f"l'hora {N['worst_label']} (on-time {pct(N['worst_s'], 0)}) en costava {f(N['worst_loss'], 1)}. "
                     f"Mediana horària {pct(box['med'], 0)} (frontisses {f(box['h1'], 0)}–{f(box['h2'], 0)}) vs "
                     f"{f(tb['h1'], 0)}–{f(tb['h2'], 0)} % del top-6")
    t["v2_sub"] = (f"Dalt: on-time de team_37 per finestra de 15 min (blau) i del top-6 de cada finestra (gris: mediana i "
                   f"frontisses). Mig: punts finals que es perdrien si tota la final fos com aquella finestra = "
                   f"(0,98 − on-time)·(0,5·q + 10); mitjana ponderada per peticions, mai suma; no inclou el component fred, per "
                   f"això «≥». Baix: residu de la identitat conversió = on-time·model + (1 − on-time)·baseline: {N['resid_ok']} de "
                   f"{N['resid_k']} finestres informatives (servei < 99 %) dins ±0,05. Arrossega a dalt per ressaltar aquestes "
                   f"hores a V1 i V3. Latència p95 {f(N['p95_lo'], 1)}–{f(N['p95_hi'], 1)} s per hora, però el model triga "
                   f"mil·lisegons: el retard és xarxa. n = {N['n_windows']} finestres, {f(N['n_requests'], 0)} peticions.")
    loss_txt = " · ".join(f"{k} {f(-v, 1, sign=True)}" for k, v in sorted(N["d2"].items(), key=lambda kv: kv[1]))
    if tie and tie.get("paired") and abs(tie["dconv"]) < N["mde_e"]:
        head = (f"{N['live']} i fz-v10-nocorr empaten (Δ aparellat fz-v9a − nocorr {f(tie['dconv'], 2, sign=True)} compres/100, IC95 "
                f"{f(tie['lo'], 2)} a {f(tie['hi'], 2)}, {tie['k']} finestres); la resta queda clarament per sota")
    else:
        head = f"{N['live']} és la millor versió per finestra (q mediana {f(N['live_med'], 0)})"
    t["v3_title"] = (f"{head} → servir-ne un sol" + (f" (l'equip: {cfg['version']}, {cfg['t_cet'][-5:]})" if cfg else "")
                     + f". En fred converteix ×{f(N['live_cold_ratio'], 1)} la baseline freda "
                     f"(referència ×{f(N['ref_cold_ratio'], 1)}): no cal una ruta freda pròpia")
    t["v3_sub"] = (f"Una marca per finestra de 15 min (≥ 100 peticions; pàl·lida si < 300; més pàl·lida si la versió ja no "
                   f"s'usa). Caixa de Tukey amb ≥ 5 finestres: frontisses, mediana i bigotis fins als valors adjacents "
                   f"(1,5·H). q normalitzat a la baseline i l'oracle de cada finestra perquè les hores no són comparables. "
                   f"Punts finals que perdríem servint una alternativa: {loss_txt}. Només fz-v10-nocorr va córrer alhora "
                   f"amb {N['live']} (comparació aparellada; l'ordre de les seves caixes és soroll); la resta són finestres diferents"
                   + (f" i fins al {pct(N['multi_max'], 0)} de peticions amb diverses versions: no és un A/B." if N.get("multi_max") else ": no és un A/B."))
    if N.get("ev1") is not None:
        t["v4_title"] = (f"Al slot 1, un producte vist abans a la sessió es ven {f(N['ev1'], 1)} cops per 1.000 i un ja comprat "
                         f"{f(N['bb1'], 1)}: slot 1 per a vistos a la sessió i carret, mai recompres")
        t["v4_sub"] = (f"Median polish de Tukey sobre log(compres per 1.000 + 0,5): files = relació del producte amb el comprador, "
                       f"columnes = bloc de posicions. Barra grisa = ajust additiu (efecte relació + efecte posició); punt blau = "
                       f"observat amb IC95 exacte de Poisson (buit si < 10 compres); ×k = residu en aquesta escala quan "
                       f"|log| ≥ 0,4 (interacció: la relació importa sobretot a dalt). El slot 1 ven {f(N['slot1_vs_710'], 0)} vegades més que "
                       f"els slots 7–10 i fa el {pct(N['slot1_share'], 0)} de les compres. Ja comprat: {pct(N['bb_pre'], 1)} dels "
                       f"slots abans del vet de les 15:50 i {pct(N['bb_post'], 1)} després; {N['bb_total']} compres en "
                       f"{f(N['bb_imp'], 0)} impressions (a l'historial convertia {f(10 * N['hist_rebuy_pct'], 1) if N['hist_rebuy_pct'] else '–'} per 1.000). Hipòtesi del "
                       f"dissabte («l'historial menteix sobre les recompres») sostinguda en directe.")
    worst_alt = max([abs(v["dconv"]) for v in N["comp"].values()] + [0])
    ratio = N["drop"] / worst_alt if worst_alt else 9
    weigh = "pesa més que" if ratio > 1.25 else "pesa tant com" if ratio >= 0.8 else "pesa menys que"
    t["v5_title"] = (f"Un 50/50 a la final (≈ {f(N['n_final'], 0)} peticions) només detecta Δ ≥ {f(N['mde_e'], 2)} compres/100 "
                     f"amb la mètrica oficial (≥ {f(N['mde_r'], 2)} amb compres reals): l'alternativa propera no es pot "
                     f"distingir, i una caiguda del writer {weigh} servir el pitjor candidat → congelar {N['live']}")
    t["v5_sub"] = (f"80 % de potència, α = 5 %, dos braços iguals. La mètrica oficial (probabilitat de compra del simulador, sense "
                   f"sort) té {f(N['var_ratio'], 0)} vegades menys variància per petició que les compres reals (dispersió entre finestres "
                   f"de 15 min de la mateixa versió; consistent amb les finestres aparellades fz-v9a/nocorr). Línies blaves: "
                   f"diferència amb cada alternativa i peticions necessàries. Regla pre-registrada: canviar de model només si "
                   f"un 50/50 abans de les 09:30 dona Δ > diferència detectable; a la final, una versió ≥ 95 %.")
    t["v6_title"] = (f"La fiabilitat (D1) és la decisió que val més: fins a {f(N['d1_hi'], 1)} punts finals; triar malament "
                     f"el model en costaria fins a {f(max(N['d2'].values()) if N['d2'] else None, 1)}; l'exploració ≤ "
                     f"{f(N['explore_cost'], 1)}")
    return t


def ledger_rows(P: dict, pred: dict, out: dict) -> list[dict]:
    N = P["N"]
    cfg = next((i for i in json.loads((ROOT / "data" / "manual" / "decisions.json").read_text(encoding="utf-8"))["items"]
                if i["id"] == "final-config"), None)
    it = pred["items"]
    d2 = N["d2"]
    rows = [
        {"id": "D1", "what": "Un sol writer + un de reserva en una altra xarxa", "ticks": [("mediana", N["d1_lo"]), (N["worst_label"], N["d1_hi"])],
         "range": (N["d1_lo"], N["d1_hi"]), "badge": "PRE-REGISTRAT"},
        {"id": "D2", "what": (f"Servir {cfg['version']} congelat (decisió {cfg['t_cet'][-5:]}; empata amb fz-v9a)" if cfg
                              else f"Servir {N['live']} congelat"), "ticks": [(k, v) for k, v in sorted(d2.items(), key=lambda kv: kv[1])],
         "badge": "PRE-REGISTRAT", "tick_note": "punts que perdríem amb cada alternativa"},
        {"id": "D6", "what": "Sense repartir el trànsit a la final", "ticks": [(k, v) for k, v in sorted(N["d6"].items(), key=lambda kv: kv[1])],
         "badge": "PRE-REGISTRAT", "tick_note": "cost d'un 50/50 amb cada alternativa"},
        {"id": "D4", "what": "Mantenir l'exploració del slot 10", "ticks": [("≤", N["explore_cost"])], "upper": True, "badge": "EXPLORATORI"},
        {"id": "D5", "what": "Sense ruta freda pròpia", "ticks": [], "note": "sense estimació en punts", "badge": "EXPLORATORI"},
        {"id": "D3", "what": "Vet a recompres; vistos a la sessió al slot 1", "ticks": [("ja guanyat", N["d3_gain"])] if N.get("d3_gain") else [],
         "banked": True, "badge": "EXPLORATORI", "note": "ja aplicat"},
    ]
    for r in rows:
        r["pred"] = it[r["id"]]["text"]
        if r["id"] in out:
            r["outcome"] = out[r["id"]]
    return rows


# ----------------------------------------------------------------------------- HTML
CSS = (Path(__file__).resolve().parent / "page.css").read_text(encoding="utf-8")
JS = (Path(__file__).resolve().parent / "page.js").read_text(encoding="utf-8")


def ledger_html(rows, scale_max):
    out = []
    axis = "".join(f'<span style="left:{100 * v / scale_max:.1f}%">{f(v, 0)}</span>' for v in range(0, int(scale_max) + 1, 5))
    for r in rows:
        ticks = [(lab, v) for lab, v in r.get("ticks", []) if v is not None]
        if not ticks:
            cell = f'<span class="na">{esc(r.get("note", "sense estimació"))}</span>'
        else:
            marks = ""
            if r.get("range"):
                lo, hi = r["range"]
                marks += f'<i class="rng" style="left:{100 * lo / scale_max:.1f}%;width:{max(0.5, 100 * (hi - lo) / scale_max):.1f}%"></i>'
            for lab, v in ticks:
                cls = "dot hollow" if r.get("banked") else "dot open" if r.get("upper") else "dot"
                marks += f'<i class="{cls}" style="left:{100 * max(v, 0) / scale_max:.1f}%" title="{esc(lab)}: {f(v, 1)}"></i>'
            labs = " · ".join(f"{esc(lab)} {f(v, 1)}" for lab, v in ticks)
            cell = f'<div class="track">{marks}</div><span class="stake-lab">{labs}</span>'
            if r.get("tick_note"):
                cell += f'<span class="tick-note">{esc(r["tick_note"])}</span>'
        oc = r.get("outcome")
        if oc:
            cls = {"✓": "ok", "✗": "ko", "~": "pend", "…": "pend"}[oc[0]]
            word = {"✓": "confirmat", "✗": "refutat", "~": "", "…": ""}[oc[0]]
            outc = f'<td class="outc {cls}">{esc(oc[0])} {esc(word)} <span>{esc(oc[1])}</span></td>'
        else:
            outc = '<td class="outc pend">… pendent</td>'
        out.append(f'<tr><th scope="row"><span class="did">{r["id"]}</span>{esc(r["what"])}'
                   f'<span class="badge b-{r["badge"].lower()}">{esc(r["badge"])}</span></th>'
                   f'<td class="stake">{cell}</td><td class="pred">{esc(r["pred"])}</td>{outc}</tr>')
    return axis, "\n".join(out)


def section(vid, title, sub, badge, extra_class="", pid="practice"):
    uid = f"{pid}-{vid}"
    return (f'<section class="view {extra_class}" id="{uid}" aria-labelledby="{uid}-t">'
            f'<header><span class="vid">{vid.upper()}</span><span class="badge b-{badge.lower().split()[0]}">{esc(badge)}</span>'
            f'<h3 id="{uid}-t">{esc(title)}</h3><p class="sub">{esc(sub)}</p></header>'
            f'<div class="chart" id="c-{uid}" role="img" aria-label="{esc(title)}"></div></section>')


def page_body(P, T, rows, period, pred, final_mode):
    N = P["N"]
    stakes = [v for r in rows for _, v in r.get("ticks", []) if v is not None]
    scale_max = max(5.0, math.ceil(max(stakes + [1]) / 5) * 5)
    verdict = "".join(f'<li><span class="did">{esc(d)}</span><strong>{esc(h)}.</strong> {esc(b)} <span class="ptr">→ {esc(p)}</span></li>'
                      for d, h, b, p in T["verdict"])
    watch = "".join(f'<li><strong>{esc(a)}</strong> → {esc(b)} <span class="muted">({esc(c)})</span></li>' for a, b, c in T["watch"])
    axis, ledger = ledger_html(rows, scale_max)
    ev = "CONFIRMATORI" if final_mode else "EXPLORATORI"
    v4 = section("v4", T.get("v4_title", ""), T.get("v4_sub", ""), ev, "wide", period) if P["specs"].get("v4") else ""
    reg = f"PRE-REGISTRAT {pred['registered_at_cet']} · sha {pred['sha256'][:8]}"
    alarm_html = (f'<p class="alarm">{esc(T["alarm"])}</p>' if T.get("alarm") else "")
    status_html = (f'<p class="status">Estat a l&#39;última dada: {esc(T["status"])}</p>' if T.get("status") else "")
    return f"""
<div class="period" data-period="{period}">
  <section class="verdict" aria-label="Veredicte">
    <h2>{esc(T['h1'])}</h2>
    <ol>{verdict}</ol>
    <div class="watch"><h4>Vigilar durant la final (10:00–12:00) <span class="badge b-pre-registrat">{esc(reg)}</span>
      <span class="muted">{esc(T['watch_head'])}</span></h4>{alarm_html}
      <ul>{watch}</ul>{status_html}</div>
    <p class="ruler">{esc(T['ruler'])}<br>{esc(T['legend'])}</p>
  </section>
  <div class="row r1">
    {section("v1", T['v1_title'], T['v1_sub'], ev, "", period)}
    <section class="view ledger" id="{period}-v6" aria-labelledby="{period}-v6-t">
      <header><span class="vid">V6</span><span class="badge b-pre-registrat">{esc(reg)}</span>
      <h3 id="{period}-v6-t">{esc(T['v6_title'])}</h3>
      <p class="sub">Registre de decisions ordenat per punts en joc (punts finals sobre 100, escala comuna des de zero; són cotes
      inferiors perquè no inclouen el component fred). Punt = valor per alternativa; barra = rang entre la mediana de pràctica i
      l'hora pitjor; buit = ja guanyat (D3, abans/després del vet, hores diferents); contorn = cota superior. Les prediccions es
      van fixar abans de la final (hash a la insígnia); la columna Final s'omple sola en reexecutar el pipeline.</p></header>
      <table><thead><tr><th>Decisió</th><th>Punts en joc<div class="axis">{axis}</div></th><th>Predicció registrada</th><th>Final</th></tr></thead>
      <tbody>{ledger}</tbody></table>
    </section>
  </div>
  <div class="row">{section("v2", T['v2_title'], T['v2_sub'], ev, "wide", period)}</div>
  <div class="row r3">
    {section("v3", T['v3_title'], T['v3_sub'], ev, "", period)}
    {section("v5", T['v5_title'], T['v5_sub'], "PRE-REGISTRAT", "", period)}
  </div>
  <div class="row">{v4}</div>
</div>"""


WHY = [
    ("V1", "Dispersió per a una relació entre dues variables quantitatives, posició en escala comuna (Munzner, P2 p35); "
           "un sol to sobre gris (P1 p61); vista general + detall per a la zona densa (MV p35)."),
    ("V2", "Línia per al temps (W3 p90), panells alineats en comptes de doble eix (P2 p54), barres des de zero (W3 p6), "
           "caixa de Tukey + tira perquè la caixa sola amaga dades (W3 p29)."),
    ("V3", "Distribució per finestra, no barres de mitjanes (VOTD Wilmer & Kerns); ordenat per mediana (MV p48); valors normalitzats (PR p4)."),
    ("V4", "Petits múltiples amb la mateixa escala (MV p45); ajust + residu (diferència explícita, MV p25); escala log etiquetada (W3 p16)."),
    ("V5", "Incertesa comunicada com a corba de potència (AV p41-43); dues línies directament etiquetades, sense llegenda (CB p14)."),
    ("V6", "Rangs de línia en lloc d'indicadors de rellotge (W3 p19); estat amb glif + paraula, mai només color (CB p11)."),
]


def footer(meta):
    why = "".join(f"<li><strong>{v}</strong> {esc(t)}</li>" for v, t in WHY)
    return f"""
<footer>
  <div><h4>Per què aquests gràfics</h4><ul class="why">{why}</ul></div>
  <div><h4>Fórmules</h4>
  <p>Conversió = compres esperades per 100 peticions (probabilitat del simulador, sense sort). Puntuació de conversió =
  100·(equip − baseline)/(oracle − baseline); l'oracle de cada hora es dedueix de la sèrie <code>progress</code> de l'API (idèntic
  per a tots els equips dins l'hora, i reprodueix la puntuació publicada). Una petició no resposta a temps rep la llista
  baseline: equip = on-time·m + (1 − on-time)·baseline, d'on m̂ = (equip − (1 − on-time)·baseline)/on-time i
  q = 100·(m̂ − baseline)/(oracle − baseline). Punts finals: conversió 50 = 0,5·puntuació; fiabilitat 10 = 10·on-time
  (supòsit A1); fred 10 (no inclòs); jurat 30. Punts perduts = (1 − on-time)·(0,5·q + 10).</p></div>
  <div><h4>Mètodes de Tukey i dades</h4>
  <p>Resum de cinc números amb frontisses i tanques 1,5·H (V2, V3); median polish amb residus (V4); anàlisi exploratòria →
  regla pre-registrada (hash SHA-256) → confirmació a la final (V6). API pública <code>datathon.rawtree.dev/api/state?by=model</code>
  (finestres d'1 h i 15 min); RawTree: <code>team_37.feedback</code>, <code>team_37.submissions</code>, <code>shop.requests</code>,
  <code>shop.events</code>, <code>shop.history_events</code>, <code>shop.catalog_updates</code>; Notion i repositori de l'equip
  per a les decisions. Dades fins a {esc(meta['data_until'])} CET · generat {esc(meta['built_cet'])} CET ·
  <code>run_all.ps1</code>.</p></div>
  <div><h4>Glossari</h4>
  <p>on-time = respostes vàlides i a temps (en 3 s) · writer = procés que envia les respostes · fallback = llista baseline de
  l'organització · slot = posició al carrusel (1 = la primera) · petició freda = usuari nou o vista d'un producte nou ·
  frontisses = quartils de Tukey · referència = recomanador fort de l'organització · 50/50 = repartir el trànsit entre dues versions.</p></div>
</footer>"""


def main():
    offline = "--cdn" not in sys.argv
    D = json.loads((ROOT / "data" / "dashboard_data.json").read_text())
    built = datetime.now(timezone.utc) + timedelta(hours=1)
    last_t = max(r["t"] for r in D["windows15"]) + 900
    meta = {"built_cet": built.strftime("%d/%m %H:%M"), "data_until": dhm(last_t)}
    P = build_period(D, "practice")
    pred = predictions(P)
    F = build_period(D, "final")
    F_db = None if F else build_final_db(D, P)
    out = outcomes(pred, F or F_db, P)
    rows = ledger_rows(P, pred, out)
    bodies = page_body(P, texts(P, pred, False), rows, "practice", pred, False)
    spec_sets = {"practice": P["specs"]}
    if F:
        rows_f = ledger_rows(F, pred, out)
        bodies += page_body(F, texts(F, pred, True), rows_f, "final", pred, True)
        spec_sets["final"] = F["specs"]
    elif F_db:
        bodies += page_body_db(F_db, rows, pred)
        spec_sets["final"] = F_db["specs"]
        F = F_db
    toggle = ('<div class="toggle" role="radiogroup" aria-label="Període">'
              '<label><input type="radio" name="period" id="p-practice" value="practice"' + ("" if F else " checked") + '> Pràctica</label>'
              '<label><input type="radio" name="period" id="p-final" value="final"' + (" checked" if F else " disabled") + '> Final'
              + ("" if F else ' <span class="pend">(a partir de les 12:00)</span>') + '</label></div>')
    libs = ""
    if offline:
        for name in ("vega.min.js", "vega-lite.min.js", "vega-embed.min.js"):
            libs += "<script>" + (VENDOR / name).read_text(encoding="utf-8") + "</script>\n"
    else:
        libs = ('<script src="https://cdn.jsdelivr.net/npm/vega@6.4.0/build/vega.min.js"></script>\n'
                '<script src="https://cdn.jsdelivr.net/npm/vega-lite@6.4.1/build/vega-lite.min.js"></script>\n'
                '<script src="https://cdn.jsdelivr.net/npm/vega-embed@7.1.0/build/vega-embed.min.js"></script>\n')
    specs_json = json.dumps(spec_sets).replace("</", "<" + chr(92) + "/")
    head = f"""<title>Tauler Tukey · team_37</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&display=swap">
<style>{CSS}</style>"""
    body = f"""<div class="page">
  <div class="top">
    <div class="brand"><span class="eyebrow">Datathon FME 2026 · Side Challenge Tukey · repte RawTree</span>
      <h1>Tauler de decisions de team_37</h1>
      <p class="lede">Descobrir, interpretar i decidir: què ens fa guanyar o perdre punts al recomanador en temps real i què fem a la final.</p></div>
    <div class="topright">{toggle}<span class="fresh">Dades fins a {esc(meta['data_until'])} CET</span></div>
  </div>
  {bodies}
  {footer(meta)}
</div>
{libs}<script id="specs" type="application/json">{specs_json}</script>
<script>{JS}</script>"""
    DIST.mkdir(exist_ok=True)
    if offline:
        doc = ('<!doctype html><html lang="ca"><head><meta charset="utf-8"><meta name="viewport" '
               'content="width=device-width, initial-scale=1, viewport-fit=cover">' + head + "</head><body>" + body + "</body></html>")
        (DIST / "index.html").write_text(doc, encoding="utf-8")
        print("wrote", DIST / "index.html", f"{len(doc) / 1e6:.2f} MB")
    else:
        (DIST / "artifact.html").write_text(head + "\n" + body, encoding="utf-8")
        print("wrote", DIST / "artifact.html")
    print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in P["N"].items()
                      if not isinstance(v, (dict, list))}, ensure_ascii=False)[:1800])


if __name__ == "__main__":
    main()
