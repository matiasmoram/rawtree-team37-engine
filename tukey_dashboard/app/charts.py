"""Four simple Altair charts for the one-view Shiny dashboard (VI course rules: few views, position on a common scale,
one highlight hue over grey, titles = conclusions, bars from zero, Tukey boxplots instead of bars of means).
Colours: blue = team_37 / the version we serve · vermillion = lost · black = organisers' reference · grey = context."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import altair as alt
import pandas as pd

US, LOST, REF, GREY, LIGHT, INK, MUTED = "#2a78d6", "#d55e00", "#1f1f1f", "#9a9993", "#d9d8d2", "#3b3b38", "#6a6964"
FONT = "'Source Sans 3', 'Segoe UI', system-ui, sans-serif"
CET = timezone(timedelta(hours=1))
TEAM = "team_37"
REL_LABEL = {"session_earlier_view": "Vist abans a la sessió", "session_last_view": "Últim vist a la sessió",
             "carted_not_bought": "Al carret, no comprat", "new_product_other": "Producte nou", "other": "Altres",
             "no_session_views": "Sense vistes (home)", "bought_before": "Ja comprat"}


def _cfg(ch):
    return (ch.configure(background="#ffffff", font=FONT, autosize={"type": "fit-x", "contains": "padding"})
            .configure_view(stroke=None)
            .configure_axis(labelColor=MUTED, titleColor=INK, domainColor="#c3c2b7", tickColor="#c3c2b7", gridColor="#ecebe6",
                            labelFontSize=11, titleFontSize=11.5, titleFontWeight=600)
            .configure_text(font=FONT, fontSize=11))


def field(D, t0, t1, width="container", height=250):
    """Every team in the latest hour of the window: x = on-time, y = conversion of the model when it answers."""
    fh = [r for r in D["field_hourly"] if t0 <= r["t"] < t1 and r["model_conv"] is not None and (r["on_time"] or 0) >= 30]
    hour = max(r["t"] for r in fh)
    rows = [r for r in fh if r["t"] == hour]
    ours = [r for r in fh if r["team"] == TEAM]
    worst = min(ours, key=lambda r: r["on_time"])
    me = next(r for r in rows if r["team"] == TEAM)
    ref = me["reference"]
    df = pd.DataFrame([{"team": r["team"], "on_time": r["on_time"], "m": r["model_conv"], "conv": r["conv"], "rank": r["rank"]}
                       for r in rows if r["team"] != TEAM])
    hh = lambda t: datetime.fromtimestamp(t, tz=CET).strftime("%a %Hh").replace("Sat", "ds").replace("Sun", "dg")
    us = pd.DataFrame([
        {"on_time": me["on_time"], "m": me["model_conv"], "conv": me["conv"], "rank": me["rank"], "lab": f"team_37 {hh(hour)}: #{me['rank']}", "kind": "ara"},
        {"on_time": worst["on_time"], "m": worst["model_conv"], "conv": worst["conv"], "rank": worst["rank"],
         "lab": f"mateix model, {hh(worst['t'])}: #{worst['rank']}", "kind": "pitjor"}])
    x = alt.X("on_time:Q", title="Peticions respostes a temps (%) · l'eix comença al 30 %", scale=alt.Scale(domain=[30, 100]))
    y = alt.Y("m:Q", title="Compres per 100 quan el model respon", scale=alt.Scale(domain=[0, 3], nice=False))
    tip = [alt.Tooltip("team:N", title="Equip"), alt.Tooltip("on_time:Q", title="On-time %", format=".1f"),
           alt.Tooltip("m:Q", title="Compres/100 del model", format=".2f"), alt.Tooltip("conv:Q", title="Compres/100 publicades", format=".2f"),
           alt.Tooltip("rank:Q", title="Posició")]
    others = alt.Chart(df).mark_circle(size=45, color=GREY, opacity=0.8).encode(x=x, y=y, tooltip=tip)
    refl = alt.Chart(pd.DataFrame([{"m": ref}])).mark_rule(color=REF, strokeDash=[4, 3]).encode(y="m:Q")
    reft = alt.Chart(pd.DataFrame([{"m": ref, "t": "referència de l'organització"}])).mark_text(
        align="left", x=4, dy=-6, color=REF, fontSize=10.5).encode(y="m:Q", text="t:N")
    arrow = alt.Chart(pd.DataFrame([{"x": worst["on_time"], "x2": me["on_time"], "m": worst["model_conv"]}])).mark_rule(
        color=US, strokeDash=[3, 3]).encode(x="x:Q", x2="x2:Q", y="m:Q")
    pts = alt.Chart(us).mark_point(size=130, color=US, strokeWidth=2).encode(
        x=x, y=y, fill=alt.condition("datum.kind == 'ara'", alt.value(US), alt.value("#ffffff")),
        tooltip=[alt.Tooltip("lab:N", title=""), alt.Tooltip("on_time:Q", title="On-time %", format=".1f"),
                 alt.Tooltip("m:Q", title="Compres/100 del model", format=".2f")])
    lab = (alt.Chart(us[us["kind"] == "ara"]).mark_text(align="right", dx=-10, dy=-10, color=US, fontWeight=700, fontSize=11)
           .encode(x=x, y=y, text="lab:N")
           + alt.Chart(us[us["kind"] == "pitjor"]).mark_text(align="left", dx=10, dy=-10, color=US, fontWeight=700, fontSize=11)
           .encode(x=x, y=y, text="lab:N"))
    return _cfg(alt.layer(others, refl, reft, arrow, pts, lab).properties(width=width, height=height))


def reliability(D, t0, t1, width="container", height=250):
    """On-time per 15-min window: team_37 (blue) vs the median of the top-6 (grey) and the 98 % target."""
    W = [r for r in D["windows15"] if t0 <= r["t"] < t1]
    df = pd.DataFrame([{"tc": (r["t"] + 3600) * 1000, "us": r["on_time"], "top": r.get("top6_med")} for r in W])
    x = alt.X("tc:T", title=None, scale=alt.Scale(type="utc"), axis=alt.Axis(format="%H:%M", tickCount=10, grid=False))
    y = alt.Y("v:Q", title="Respostes a temps (%)", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(values=[0, 25, 50, 75, 98]))
    top = alt.Chart(df).transform_calculate(v="datum.top").mark_line(color=GREY, strokeWidth=1.5, interpolate="step-after").encode(x=x, y=y)
    us = alt.Chart(df).transform_calculate(v="datum.us").mark_line(color=US, strokeWidth=2, interpolate="step-after").encode(
        x=x, y=y, tooltip=[alt.Tooltip("tc:T", title="Finestra (CET)", format="%a %H:%M", formatType="utc"),
                           alt.Tooltip("us:Q", title="team_37 %", format=".1f"), alt.Tooltip("top:Q", title="Top-6 (mediana) %", format=".1f")])
    goal = alt.Chart(pd.DataFrame([{"v": 98}])).mark_rule(color=US, strokeDash=[5, 4], opacity=0.7).encode(y="v:Q")
    g = alt.Chart(pd.DataFrame([{"tc": df["tc"].iloc[-1], "v": 98, "t": "objectiu 98 %"}])).mark_text(
        align="right", dy=-7, fontSize=10.5, color=US).encode(x="tc:T", y="v:Q", text="t:N")
    k = alt.Chart(pd.DataFrame([{"tc": df["tc"].iloc[0], "v": 8, "t": "blau: team_37 · gris: mediana del top-6"}])).mark_text(
        align="left", fontSize=10.5, color=MUTED).encode(x="tc:T", y="v:Q", text="t:N")
    return _cfg(alt.layer(top, us, goal, g, k).properties(width=width, height=height))


VERSIONS = ["fz-v10-nocorr", "fz-v9a-xcat1.0", "t37-cf-rot", "t37-lgbm-recent", "t37-ev-v2-nocovis"]


def versions(D, t0, t1, served="fz-v10-nocorr", width="container", height=230):
    """Tukey boxplot per version of (conversion − organisers' reference in the same 15-min window)."""
    A = [r for r in D["arms15"] if t0 <= r["t"] < t1 and r["version"] in VERSIONS and r["requests"] >= 100]
    df = pd.DataFrame([{"version": r["version"], "d": r["conv"] - r["reference"], "n": r["requests"],
                        "serveix": r["version"] == served} for r in A])
    if df.empty:
        return None
    order = df.groupby("version")["d"].median().sort_values(ascending=False).index.tolist()
    y = alt.Y("version:N", sort=order, title=None, axis=alt.Axis(labelLimit=150, labelFontSize=11.5))
    x = alt.X("d:Q", title="Compres/100 per sobre de la referència (mateixa finestra de 15 min)", scale=alt.Scale(domain=[-1.5, 1.5], clamp=True))
    zero = alt.Chart(pd.DataFrame([{"d": 0}])).mark_rule(color=REF, strokeDash=[4, 3]).encode(x="d:Q")
    zt = alt.Chart(pd.DataFrame([{"d": 0, "t": "= referència"}])).mark_text(align="left", dx=3, y=-6, fontSize=10, color=REF).encode(x="d:Q", text="t:N")
    box = alt.Chart(df).mark_boxplot(extent=1.5, size=16, median={"color": "#ffffff"}, outliers={"size": 18}).encode(
        y=y, x=x, color=alt.Color("serveix:N", scale=alt.Scale(domain=[True, False], range=[US, GREY]), legend=None))
    return _cfg(alt.layer(zero, zt, box).properties(width=width, height=height))


def slot_one(D, width="container", height=230):
    """Purchases per 1,000 impressions in slot 1, by the product's relation to the shopper (bars from zero)."""
    rel = [r for r in D["practice"]["relation_slot"] if r["sb"] == "team" and r["slot"] == 1]
    agg = {}
    for r in rel:
        a = agg.setdefault(r["relation"], [0, 0])
        a[0] += r["impressions"]
        a[1] += r["purchases"]
    df = pd.DataFrame([{"rel": REL_LABEL[k], "rate": 1000 * b / a, "imp": a, "buys": b, "lost": k == "bought_before"}
                       for k, (a, b) in agg.items() if a >= 500])
    y = alt.Y("rel:N", sort="-x", title=None, axis=alt.Axis(labelLimit=170, labelFontSize=11.5))
    x = alt.X("rate:Q", title="Compres per 1.000 vegades que es mostra al slot 1", scale=alt.Scale(domainMin=0))
    bars = alt.Chart(df).mark_bar(size=16, cornerRadiusEnd=3).encode(
        y=y, x=x, color=alt.condition("datum.lost", alt.value(LOST), alt.value(US)),
        tooltip=[alt.Tooltip("rel:N", title="Relació"), alt.Tooltip("rate:Q", title="Compres/1.000", format=".1f"),
                 alt.Tooltip("imp:Q", title="Impressions", format=",.0f"), alt.Tooltip("buys:Q", title="Compres")])
    txt = alt.Chart(df).mark_text(align="left", dx=4, fontSize=11, color=INK).encode(y=y, x=x, text=alt.Text("rate:Q", format=".1f"))
    return _cfg(alt.layer(bars, txt).properties(width=width, height=height))


# ------------------------------------------------------------------------------------------------ final (confirmatory)
# Drawn from the RawTree DB (team_37.feedback) because the public API hides the leaderboard while the final runs.
# Same colour rules: blue = the final (what we confirm), grey = practice (what we predicted from).

def _box_layers(df, y, x, color, size=18):
    """Tukey box (hinges, median, whiskers to the adjacent values within 1.5·H) + every observation as a strip."""
    box = alt.Chart(df).mark_boxplot(extent=1.5, size=size, median={"color": "#ffffff"}, outliers=False, opacity=0.9).encode(
        y=y, x=x, color=color)
    strip = alt.Chart(df).mark_tick(thickness=1.2, size=size + 8, opacity=0.35).encode(y=y, x=x, color=color)
    return box, strip


def final_reliability(N, width="container", height=200):
    """On-time per 10-minute window: every practice window vs every final window (Tukey box + strip)."""
    rows = [{"who": "Pràctica (ds 13:00 – dg 10:00)", "v": v, "final": False} for v in N["prac_w"]]
    rows += [{"who": "Final (dg 10:00 – 12:00)", "v": r["on_time"], "final": True, "lab": r["label"]} for r in N["windows"]]
    df = pd.DataFrame(rows)
    y = alt.Y("who:N", title=None, sort=["Final (dg 10:00 – 12:00)", "Pràctica (ds 13:00 – dg 10:00)"],
              axis=alt.Axis(labelLimit=220, labelFontSize=11.5))
    x = alt.X("v:Q", title="Respostes a temps per finestra de 10 min (%)", scale=alt.Scale(domain=[0, 100]),
              axis=alt.Axis(values=[0, 25, 50, 75, 95, 100]))
    color = alt.Color("final:N", scale=alt.Scale(domain=[True, False], range=[US, GREY]), legend=None)
    box, strip = _box_layers(df, y, x, color)
    goal = alt.Chart(pd.DataFrame([{"v": 98}])).mark_rule(color=US, strokeDash=[5, 4], opacity=0.7).encode(x="v:Q")
    gt = alt.Chart(pd.DataFrame([{"v": 98, "t": "objectiu 98 %"}])).mark_text(align="right", dx=-4, y=6, fontSize=10.5,
                                                                              color=US).encode(x="v:Q", text="t:N")
    return _cfg(alt.layer(strip, box, goal, gt).properties(width=width, height=height))


def final_latency(D, width="container", height=200):
    """Latency of team-served answers per hour (5–25–50–75–95 percentiles): practice hours vs final hours."""
    rows = []
    for period, lab in (("practice", "Pràctica"), ("final", "Final")):
        for r in (D.get(period) or {}).get("latency_hourly", []):
            q = r.get("q") or []
            if len(q) < 8 or int(r["n"]) < 300:
                continue
            rows.append({"who": lab, "t": int(r["t"]), "p5": q[1] / 1000, "p25": q[2] / 1000, "p50": q[3] / 1000,
                         "p75": q[4] / 1000, "p95": q[5] / 1000, "final": period == "final", "n": int(r["n"]),
                         "hora": datetime.fromtimestamp(int(r["t"]), tz=CET).strftime("%a %H:%M").replace("Sat", "ds").replace("Sun", "dg")})
    df = pd.DataFrame(rows)
    if df.empty:
        return None
    y = alt.Y("p95:Q", title="Latència p95 per hora (s)", scale=alt.Scale(domain=[0, max(3.2, float(df["p95"].max()) + 0.2)]))
    x = alt.X("who:N", title=None, sort=["Pràctica", "Final"], axis=alt.Axis(labelAngle=0, labelFontSize=11.5))
    color = alt.Color("final:N", scale=alt.Scale(domain=[True, False], range=[US, GREY]), legend=None)
    box = alt.Chart(df).mark_boxplot(extent="min-max", size=46, median={"color": "#ffffff"}).encode(x=x, y=y, color=color)
    pts = alt.Chart(df).mark_circle(size=34, opacity=0.55).encode(
        x=x, y=y, color=color, xOffset=alt.XOffset("jit:Q", scale=alt.Scale(domain=[-1, 1])),
        tooltip=[alt.Tooltip("hora:N", title="Hora (CET)"), alt.Tooltip("p50:Q", title="p50 (s)", format=".2f"),
                 alt.Tooltip("p95:Q", title="p95 (s)", format=".2f"), alt.Tooltip("n:Q", title="Respostes", format=",.0f")]
    ).transform_calculate(jit="sin(datum.t) * 0.6")
    lim = alt.Chart(pd.DataFrame([{"p95": 3.0, "t": "límit 3 s"}]))
    rule = lim.mark_rule(color=LOST, strokeDash=[4, 3]).encode(y="p95:Q")
    rt = lim.mark_text(align="left", x=4, dy=-6, fontSize=10.5, color=LOST).encode(y="p95:Q", text="t:N")
    return _cfg(alt.layer(box, pts, rule, rt).properties(width=width, height=height))


def final_realised(N, width="container", height=200):
    """Realised purchases per 100 requests with exact Poisson 95 % intervals: the served version at the final vs practice."""
    rows = []
    live, prev = N.get("live"), N.get("prev_live")
    for lab, r, fin in ((f"{live} · final", N.get("real"), True),
                        (f"{live} · pràctica", N.get("real_prac_live"), False),
                        (f"{prev} · pràctica", N.get("real_prac_prev"), False),
                        ("llista baseline · pràctica", (N.get("real_prac") or {}).get("(fallback:missing)"), False)):
        if r:
            rows.append({"lab": lab, "rate": r["rate"], "lo": r["lo"], "hi": r["hi"], "n": r["n"], "k": r["k"], "final": fin})
    df = pd.DataFrame(rows)
    y = alt.Y("lab:N", title=None, sort=[r["lab"] for r in rows], axis=alt.Axis(labelLimit=220, labelFontSize=11.5))
    x = alt.X("rate:Q", title="Compres reals per 100 peticions (IC95 exacte de Poisson)", scale=alt.Scale(domainMin=0))
    color = alt.Color("final:N", scale=alt.Scale(domain=[True, False], range=[US, GREY]), legend=None)
    tip = [alt.Tooltip("lab:N", title=""), alt.Tooltip("rate:Q", title="Compres/100", format=".2f"),
           alt.Tooltip("lo:Q", title="IC95 inf.", format=".2f"), alt.Tooltip("hi:Q", title="IC95 sup.", format=".2f"),
           alt.Tooltip("k:Q", title="Compres"), alt.Tooltip("n:Q", title="Peticions", format=",.0f")]
    band = alt.Chart(df[~df["final"]].head(1)).mark_rect(opacity=0.12, color=GREY).encode(x="lo:Q", x2="hi:Q")
    err = alt.Chart(df).mark_rule(strokeWidth=2).encode(y=y, x="lo:Q", x2="hi:Q", color=color)
    dot = alt.Chart(df).mark_point(size=110, filled=True).encode(y=y, x=x, color=color, tooltip=tip)
    txt = alt.Chart(df).mark_text(align="left", dx=8, dy=-9, fontSize=11, color=INK).encode(y=y, x="hi:Q", text=alt.Text("rate:Q", format=".2f"))
    return _cfg(alt.layer(band, err, dot, txt).properties(width=width, height=height))


def final_slot_one(D, width="container", height=230):
    """Slot-1 purchases per 1,000 impressions by relation: practice pattern (grey) replicated at the final (blue, IC95)."""
    import math

    def agg(period):
        out = {}
        for r in (D.get(period) or {}).get("relation_slot", []):
            if r["sb"] == "team" and r["slot"] == 1:
                a = out.setdefault(r["relation"], [0, 0])
                a[0] += r["impressions"]
                a[1] += r["purchases"]
        return out

    pr, fi = agg("practice"), agg("final")
    rows = []
    for k, (imp, buys) in fi.items():
        if imp < 200 or k not in pr:
            continue
        z = 1.959964
        lo = 0.0 if buys == 0 else buys * (1 - 1 / (9 * buys) - z / (3 * math.sqrt(buys))) ** 3
        hi = (buys + 1) * (1 - 1 / (9 * (buys + 1)) + z / (3 * math.sqrt(buys + 1))) ** 3
        rows.append({"rel": REL_LABEL[k], "final": 1000 * buys / imp, "lo": 1000 * max(lo, 0) / imp, "hi": 1000 * hi / imp,
                     "prac": 1000 * pr[k][1] / pr[k][0], "imp": imp, "buys": buys, "lost": k == "bought_before"})
    df = pd.DataFrame(rows)
    if df.empty:
        return None
    order = df.sort_values("prac", ascending=False)["rel"].tolist()
    y = alt.Y("rel:N", sort=order, title=None, axis=alt.Axis(labelLimit=170, labelFontSize=11.5))
    x = alt.X("final:Q", title="Compres per 1.000 vegades al slot 1", scale=alt.Scale(domainMin=0))
    err = alt.Chart(df).mark_rule(color=US, strokeWidth=2, opacity=0.6).encode(y=y, x="lo:Q", x2="hi:Q")
    prac = alt.Chart(df).mark_tick(color=REF, thickness=2.5, size=18).encode(
        y=y, x="prac:Q", tooltip=[alt.Tooltip("rel:N", title="Relació"), alt.Tooltip("prac:Q", title="Pràctica /1.000", format=".1f")])
    fin = alt.Chart(df).mark_point(size=100, filled=True).encode(
        y=y, x=x, color=alt.condition("datum.lost", alt.value(LOST), alt.value(US)),
        tooltip=[alt.Tooltip("rel:N", title="Relació"), alt.Tooltip("final:Q", title="Final /1.000", format=".1f"),
                 alt.Tooltip("lo:Q", title="IC95 inf.", format=".1f"), alt.Tooltip("hi:Q", title="IC95 sup.", format=".1f"),
                 alt.Tooltip("prac:Q", title="Pràctica /1.000", format=".1f"), alt.Tooltip("imp:Q", title="Impressions", format=",.0f"),
                 alt.Tooltip("buys:Q", title="Compres")])
    return _cfg(alt.layer(err, prac, fin).properties(width=width, height=height))


def final_field(N, width="container", height=230):
    """Official final, every team: on-time (x) vs expected purchases per 100 (y); team_37 in blue, references in black."""
    rows = [r for r in N.get("field_final", []) if r.get("on_time") is not None and r["on_time"] >= 50]
    if not rows:
        return None
    df = pd.DataFrame([{**r, "us": r["team"] == TEAM} for r in rows])
    x = alt.X("on_time:Q", title="Peticions respostes a temps a la final (%) · l'eix comença al 50 %", scale=alt.Scale(domain=[50, 100]))
    y = alt.Y("conv:Q", title="Compres esperades per 100 (mètrica oficial)", scale=alt.Scale(domainMin=0))
    tip = [alt.Tooltip("team:N", title="Equip"), alt.Tooltip("rank:Q", title="Posició (conversió)"),
           alt.Tooltip("conv:Q", title="Compres/100", format=".2f"), alt.Tooltip("on_time:Q", title="On-time %", format=".1f"),
           alt.Tooltip("cold:Q", title="Fred /100", format=".2f"), alt.Tooltip("version:N", title="Versió")]
    others = alt.Chart(df[~df["us"]]).mark_circle(size=45, color=GREY, opacity=0.8).encode(x=x, y=y, tooltip=tip)
    us = alt.Chart(df[df["us"]]).mark_point(size=150, filled=True, color=US).encode(x=x, y=y, tooltip=tip)
    me = df[df["us"]].iloc[0]
    lab = alt.Chart(pd.DataFrame([{"on_time": me["on_time"], "conv": me["conv"], "t": f"team_37 #{int(me['rank'])}"}])).mark_text(
        align="right", dx=-10, dy=10, color=US, fontWeight=700, fontSize=11.5).encode(x="on_time:Q", y="conv:Q", text="t:N")
    lines = pd.DataFrame([{"conv": N["ref_conv"], "t": "referència de l'organització"}, {"conv": N["base_conv"], "t": "baseline"}])
    rule = alt.Chart(lines).mark_rule(color=REF, strokeDash=[4, 3]).encode(y="conv:Q")
    rt = alt.Chart(lines).mark_text(align="left", x=4, dy=-6, color=REF, fontSize=10.5).encode(y="conv:Q", text="t:N")
    return _cfg(alt.layer(rule, rt, others, us, lab).properties(width=width, height=height))
