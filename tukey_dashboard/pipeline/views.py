"""Altair view builders. Colours are written as tokens ("TOK:us") and resolved in the page from CSS custom
properties, so light and dark themes use the same specs. One colour = one meaning (docs/spec_v2.md §2.4):
blue = team_37 observed · light blue = team_37 path · vermillion = points lost · black = external benchmarks
(baseline, reference, oracle, organisers' status light) · grey = other teams, guides, fits."""
from __future__ import annotations

import math
import statistics as st

import altair as alt
import pandas as pd

T = {k: f"TOK:{k}" for k in [
    "surface", "ink", "ink2", "muted", "axis", "grid", "us", "us_light", "lost", "bench", "other", "guide",
    "band", "band2", "expected", "realised"]}
FONT = "'Source Sans 3', 'Segoe UI', system-ui, sans-serif"


def config(chart):
    return (chart.configure(background=T["surface"], font=FONT, padding=4)
            .configure_view(stroke=None)
            .configure_axis(labelColor=T["muted"], titleColor=T["ink2"], domainColor=T["axis"], tickColor=T["axis"],
                            gridColor=T["grid"], labelFontSize=11, titleFontSize=11, titleFontWeight=600,
                            labelFont=FONT, titleFont=FONT)
            .configure_text(color=T["ink2"], font=FONT, fontSize=11)
            .configure_header(labelColor=T["ink"], labelFontSize=12, labelFontWeight=600, titleFontSize=0,
                              labelFont=FONT)
            .configure_concat(spacing=10))


def tukey(vals):
    """Tukey's five-number summary with hinges (depth (n+1)/2 halves), inner fences and adjacent values."""
    v = sorted(x for x in vals if x is not None and not math.isnan(x))
    n = len(v)
    if n == 0:
        return None
    med = st.median(v)
    h1, h2 = st.median(v[: (n + 1) // 2]), st.median(v[n // 2:])
    step = 1.5 * (h2 - h1)
    lo_f, hi_f = h1 - step, h2 + step
    inside = [x for x in v if lo_f <= x <= hi_f]
    return {"n": n, "min": v[0], "h1": h1, "med": med, "h2": h2, "max": v[-1], "lo_fence": lo_f, "hi_fence": hi_f,
            "lo_adj": min(inside) if inside else med, "hi_adj": max(inside) if inside else med,
            "outliers": [x for x in v if x < lo_f or x > hi_f]}


def cet_ms(t):
    return (float(t) + 3600) * 1000.0


def hl_opacity(field="tc", lo=1.0, hi=0.22):
    return alt.condition(f"hl[0] == 0 || (datum.{field} >= hl[0] && datum.{field} <= hl[1])", alt.value(lo), alt.value(hi))


HL = alt.param(name="hl", value=[0, 0])


def title(text):
    return alt.TitleParams(text, fontSize=11, color=T["ink2"], anchor="start", fontWeight=600)


# ----------------------------------------------------------------------------- V1 field (overview + detail)
def v1_field(field_rows, path_rows, sel, iso_levels, ref_q, proj, y_min=-10, w=360, wd=250, h=320):
    others = pd.DataFrame(field_rows)
    path = pd.DataFrame(path_rows)
    y = alt.Y("q:Q", title="Qualitat del model servit q (0 = llista baseline · 100 = oracle)",
              scale=alt.Scale(domain=[y_min, 100], nice=False), axis=alt.Axis(values=[0, 20, 40, 60, 80, 100]))
    tip_o = [alt.Tooltip("team:N", title="Equip"), alt.Tooltip("s:Q", title="On-time %", format=".1f"),
             alt.Tooltip("conv:Q", title="Conversió publicada", format=".2f"),
             alt.Tooltip("m:Q", title="Conversió del model servit m̂", format=".2f"), alt.Tooltip("q:Q", title="q", format=".0f"),
             alt.Tooltip("score:Q", title="Puntuació de conversió (0-100)", format=".0f"), alt.Tooltip("rank:Q", title="Posició API")]
    tip_p = [alt.Tooltip("label:N", title="Hora (CET)"), alt.Tooltip("s:Q", title="On-time %", format=".1f"),
             alt.Tooltip("conv:Q", title="Conversió publicada", format=".2f"), alt.Tooltip("m:Q", title="m̂", format=".2f"),
             alt.Tooltip("q:Q", title="q", format=".0f"), alt.Tooltip("rank:Q", title="Posició API"),
             alt.Tooltip("model_version:N", title="Versió principal")]

    def panel(x0, width, detail):
        x = alt.X("s:Q", title=("Detall: on-time 90–100 %" if detail else "On-time (% de peticions respostes a temps)"),
                  scale=alt.Scale(domain=[x0, 100], nice=False),
                  axis=alt.Axis(values=([90, 92, 94, 96, 98, 100] if detail else [0, 20, 40, 60, 80, 90, 100]), grid=False))
        iso = pd.DataFrame([{"C": c, "s": s / 10, "q": 1000 * c / s} for c in iso_levels
                            for s in range(max(int(10 * c), int(10 * x0)), 1001)])
        layers = [alt.Chart(iso).mark_line(color=T["guide"], strokeWidth=1).encode(x="s:Q", y="q:Q", detail="C:N")]
        if detail:
            iso_lab = pd.DataFrame([{"s": 100, "q": c, "label": f"{c}"} for c in iso_levels])
            layers.append(alt.Chart(iso_lab).mark_text(align="left", dx=4, fontSize=10, color=T["muted"]).encode(
                x="s:Q", y="q:Q", text="label:N"))
        else:
            iso_lab = pd.DataFrame([{"s": 100 * c / 96, "q": 96, "label": f"puntuació {c}"} for c in iso_levels])
            layers.append(alt.Chart(iso_lab).mark_text(align="left", dx=4, dy=2, fontSize=10, color=T["muted"]).encode(
                x="s:Q", y="q:Q", text="label:N"))
        layers.append(alt.Chart(pd.DataFrame([{"q": 0}])).mark_rule(color=T["bench"], strokeDash=[2, 3], strokeWidth=1).encode(y="q:Q"))
        if not detail:
            layers.append(alt.Chart(pd.DataFrame([{"q": 0, "s": 1, "t": "llista baseline = resposta per defecte (q 0)"}])).mark_text(
                align="left", dy=-6, fontSize=10, color=T["muted"]).encode(x="s:Q", y="q:Q", text="t:N"))
            layers.append(alt.Chart(pd.DataFrame([{"x0": 90, "x1": 100}])).mark_rect(
                fill="transparent", stroke=T["ink2"], strokeWidth=0.8, strokeDash=[3, 2]).encode(
                x="x0:Q", x2="x1:Q", y=alt.value(0), y2=alt.value(h)))
            layers.append(alt.Chart(pd.DataFrame([{"s": 95, "t": "detall →"}])).mark_text(
                fontSize=10, color=T["ink2"], dy=-5).encode(x="s:Q", y=alt.value(0), text="t:N"))
        layers.append(alt.Chart(pd.DataFrame([{"s": 90}])).mark_rule(color=T["bench"], strokeDash=[2, 3], strokeWidth=1).encode(x="s:Q"))
        layers.append(alt.Chart(pd.DataFrame([{"s": 90, "t": "semàfor ≥ 90 %"}])).mark_text(
            align="left" if detail else "right", dx=4 if detail else -4, fontSize=10, color=T["muted"]).encode(
            x="s:Q", y=alt.value(h - 8), text="t:N"))
        od = others[others["s"] >= x0] if detail else others
        layers.append(alt.Chart(od).mark_point(size=40 if detail else 30, strokeWidth=1.2, color=T["other"]).encode(
            x="s:Q", y="q:Q", fill=alt.condition("datum.s >= 50", alt.value(T["other"]), alt.value("transparent")),
            tooltip=tip_o))
        pth = path[path["s"] >= x0] if detail else path
        layers.append(alt.Chart(pth).mark_line(color=T["us_light"], strokeWidth=2).encode(x="s:Q", y="q:Q", order="t:Q"))
        layers.append(alt.Chart(pth).mark_point(size=40, filled=True, color=T["us_light"], stroke=T["us"], strokeWidth=1).encode(
            x="s:Q", y="q:Q", opacity=hl_opacity(), tooltip=tip_p))
        if detail:
            lab = od[od["label_detail"] != ""]
            layers.append(alt.Chart(lab).mark_text(align="right", dx=-7, dy=-8, fontSize=10, color=T["muted"]).encode(
                x="s:Q", y="q:Q", text="label_detail:N"))
            layers.append(alt.Chart(pd.DataFrame([{"s": 100, "q": ref_q}])).mark_point(
                shape="cross", size=90, color=T["bench"], filled=True).encode(x="s:Q", y="q:Q"))
            layers.append(alt.Chart(pd.DataFrame([{"s": 100, "q": ref_q, "t": "referència org. ✚"}])).mark_text(
                align="right", dx=-10, dy=4, fontSize=10, color=T["ink2"]).encode(x="s:Q", y="q:Q", text="t:N"))
            layers.append(alt.Chart(pth[pth["show_d"]]).mark_text(align="right", dx=-8, dy=18, fontSize=10.5, fontWeight=600,
                                                                   color=T["us"]).encode(x="s:Q", y="q:Q", text="end:N"))
            seld = pd.DataFrame([sel])
            if sel["s"] >= x0:
                layers.append(alt.Chart(seld).mark_rule(color=T["us"], strokeWidth=1.5).encode(x="s:Q", y="q_lo:Q", y2="q_hi:Q"))
                layers.append(alt.Chart(seld).mark_point(shape="cross", size=70, color=T["us"], strokeWidth=1.5, angle=45).encode(
                    x="s:Q", y="q_meas:Q", tooltip=[alt.Tooltip("q_meas:Q", title="q mesurada per versió (API)", format=".0f")]))
        else:
            layers.append(alt.Chart(pth[pth["s"] < 90]).mark_text(align="left", dx=6, dy=16, fontSize=10.5, fontWeight=600,
                                                                   color=T["us"]).encode(x="s:Q", y="q:Q", text="end:N"))
            if proj["label"]:
                pr = pd.DataFrame([{"s": proj["s0"], "s2": proj["s"], "q": proj["q"]}])
                layers.append(alt.Chart(pr).mark_rule(color=T["us"], strokeDash=[5, 4], strokeWidth=1.3).encode(x="s:Q", x2="s2:Q", y="q:Q"))
                layers.append(alt.Chart(pd.DataFrame([{"s": proj["s0"] + 2, "q": proj["q"], "t": proj["label"]}])).mark_text(
                    align="left", dy=-22, fontSize=10.5, color=T["us"], fontWeight=600, lineBreak="|").encode(x="s:Q", y="q:Q", text="t:N"))
        return alt.layer(*layers).encode(x=x, y=y).properties(width=width, height=h)

    overview = panel(0, w, False)
    detail = panel(90, wd, True)
    return config(alt.hconcat(overview, detail, spacing=6).resolve_axis(y="independent").add_params(HL))


# ----------------------------------------------------------------------------- V2 reliability
def v2_reliability(win_rows, events, box_rows, box_pts, box_text, w=990, target=98, ha=150, hb=90, hc=60, bw=170, show_box=True, show_rlab=True):
    d = pd.DataFrame(win_rows)
    brush = alt.selection_interval(name="brush", encodings=["x"])
    x = alt.X("tc:T", title=None, scale=alt.Scale(type="utc"), axis=alt.Axis(labels=False, ticks=False, grid=False, domain=False))
    xs = alt.X("tc:T", title="Hora (CET) · finestres de 15 min", scale=alt.Scale(type="utc"),
               axis=alt.Axis(format="%a %H:%M", labelOverlap=True, tickCount=16, grid=False))
    tip = [alt.Tooltip("label:N", title="Finestra (CET)"), alt.Tooltip("requests:Q", title="Peticions"),
           alt.Tooltip("on_time:Q", title="On-time %", format=".1f"),
           alt.Tooltip("model_conv:Q", title="Conversió del model servit", format=".2f"),
           alt.Tooltip("team_conv:Q", title="Conversió publicada", format=".2f"),
           alt.Tooltip("q:Q", title="q del model", format=".0f"),
           alt.Tooltip("lost_conv:Q", title="Punts perduts · conversió", format=".1f"),
           alt.Tooltip("lost_rel:Q", title="Punts perduts · fiabilitat", format=".1f"),
           alt.Tooltip("lost:Q", title="Punts finals perduts", format=".1f"),
           alt.Tooltip("resid:Q", title="Residu de la identitat", format="+.2f")]
    yd = alt.Y("top6_h1:Q", title="On-time %", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(values=[0, 25, 50, 75, 90, 100]))
    band = alt.Chart(d).mark_area(color=T["band"], interpolate="step-after").encode(x=x, y=yd, y2="top6_h2:Q")
    bmed = alt.Chart(d).mark_line(color=T["other"], strokeWidth=1, interpolate="step-after").encode(x=x, y="top6_med:Q")
    r90 = alt.Chart(pd.DataFrame([{"y": 90}])).mark_rule(color=T["bench"], strokeDash=[2, 3]).encode(y="y:Q")
    r98 = alt.Chart(pd.DataFrame([{"y": target}])).mark_rule(color=T["us"], strokeDash=[5, 4]).encode(y="y:Q")
    line = alt.Chart(d).mark_line(color=T["us"], strokeWidth=1.6, point=alt.OverlayMarkDef(size=14, color=T["us"])).encode(
        x=x, y="on_time:Q", tooltip=tip)
    ev = pd.DataFrame(events)
    evr = alt.Chart(ev).mark_rule(color=T["ink2"], strokeWidth=0.8, strokeDash=[1, 2]).encode(x="tc:T")
    evt = alt.Chart(ev).mark_text(align="left", dx=3, fontSize=10, color=T["ink2"], baseline="bottom").encode(
        x="tc:T", y=alt.Y("yy:Q", scale=None), text="t:N")
    a = alt.layer(band, bmed, r90, r98, line, evr, evt).add_params(brush).properties(width=w, height=ha)
    rl = pd.DataFrame([{"y": 97, "t": f"objectiu {target} %"}, {"y": 87, "t": "semàfor 90 %"},
                       {"y": 70, "t": "gris: top-6"}, {"y": 62, "t": "(mediana i"}, {"y": 54, "t": "frontisses)"}])
    rlab = alt.Chart(rl).mark_text(align="left", fontSize=10, color=T["muted"]).encode(
        y=alt.Y("y:Q", scale=alt.Scale(domain=[0, 100]), axis=None), text="t:N", x=alt.value(0)).properties(width=78, height=ha)
    lost = alt.Chart(d).mark_bar(color=T["lost"], size=4, cornerRadiusEnd=1).encode(
        x=alt.X("tc:T", title=None, scale=alt.Scale(type="utc"), axis=alt.Axis(labels=False, ticks=False, grid=False)),
        y=alt.Y("lost:Q", title="Punts finals perduts", scale=alt.Scale(domain=[0, 40], clamp=True), axis=alt.Axis(values=[0, 10, 20, 30, 40])),
        opacity=alt.condition(brush, alt.value(1), alt.value(0.35)), tooltip=tip).properties(width=w, height=hb)
    rband = alt.Chart(pd.DataFrame([{"lo": -0.05, "hi": 0.05}])).mark_rect(color=T["band"]).encode(
        y=alt.Y("lo:Q", title="Residu", scale=alt.Scale(domain=[-0.2, 0.2], clamp=True), axis=alt.Axis(values=[-0.2, 0, 0.2])), y2="hi:Q")
    rdots = alt.Chart(d).mark_point(size=16, filled=True, color=T["other"]).encode(x=xs, y="resid:Q", tooltip=tip)
    c = alt.layer(rband, rdots).properties(width=w, height=hc)
    timeline = alt.vconcat(alt.hconcat(a, rlab, spacing=4) if show_rlab else a, lost, c, spacing=6)
    b = pd.DataFrame(box_rows)
    p = pd.DataFrame(box_pts)
    sort = ["team_37", "top-6"]
    xb = alt.X("who:N", title=None, sort=sort, axis=alt.Axis(labelAngle=0, labelFontSize=10.5, orient="top"))
    yb = alt.Y("v:Q", title=None, scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(values=[0, 25, 50, 75, 90, 100]))
    wl = alt.Chart(b).mark_rule(color=T["ink2"]).encode(x=xb, y=alt.Y("lo_adj:Q", scale=alt.Scale(domain=[0, 100])), y2="hi_adj:Q")
    bx = alt.Chart(b).mark_bar(size=22, fill=T["surface"], stroke=T["ink2"], strokeWidth=1).encode(x=xb, y="h1:Q", y2="h2:Q")
    md = alt.Chart(b).mark_tick(size=22, thickness=2.5, color=T["ink"]).encode(x=xb, y="med:Q")
    strip = alt.Chart(p).mark_tick(size=9, thickness=1, opacity=0.85, xOffset=20).encode(
        x=alt.X("who:N", sort=sort), y=yb,
        color=alt.condition("datum.who == 'team_37'", alt.value(T["us"]), alt.value(T["other"])),
        tooltip=[alt.Tooltip("who:N", title="Grup"), alt.Tooltip("v:Q", title="On-time de l'hora %", format=".1f"),
                 alt.Tooltip("label:N", title="Hora")])
    outl = alt.Chart(p[p["outlier"]]).mark_text(align="left", dx=27, fontSize=10, color=T["lost"], lineBreak="|").encode(
        x=alt.X("who:N", sort=sort), y="v:Q", text="olabel:N")
    box = alt.layer(wl, bx, md, strip, outl).properties(width=bw, height=ha, title=title("On-time per hora (Tukey)"))
    if not show_box:
        return config(timeline)
    return config(alt.hconcat(timeline, box, spacing=14).resolve_scale(y="independent"))


# ----------------------------------------------------------------------------- V3 model choice
def v3_models(ticks, boxes, texts, order, cold_ticks, w=360, row=23, cw=150, label_limit=210):
    tk = pd.DataFrame(ticks)
    tk["base_op"] = tk.apply(lambda r: (0.9 if r["requests"] >= 300 else 0.45) * (0.45 if r["retired"] else 1), axis=1)
    bx = pd.DataFrame(boxes)
    tx = pd.DataFrame(texts)
    ck = pd.DataFrame(cold_ticks)
    h = row * len(order)
    y = alt.Y("version:N", sort=order, title=None, axis=alt.Axis(labelLimit=label_limit, labelFontSize=11, labelColor=T["ink2"]))
    x = alt.X("q:Q", title="q per finestra de 15 min (0 = baseline · 100 = oracle)", scale=alt.Scale(domain=[-10, 100]),
              axis=alt.Axis(values=[0, 20, 40, 60, 80]))
    tip = [alt.Tooltip("version:N", title="Versió"), alt.Tooltip("label:N", title="Finestra (CET)"),
           alt.Tooltip("requests:Q", title="Peticions"), alt.Tooltip("conv:Q", title="Conversió", format=".2f"),
           alt.Tooltip("q:Q", title="q", format=".0f"), alt.Tooltip("ref_q:Q", title="q de la referència (mateixa finestra)", format=".0f"),
           alt.Tooltip("dq:Q", title="Δq vs referència", format="+.0f")]
    zero = alt.Chart(pd.DataFrame([{"q": 0}])).mark_rule(color=T["bench"], strokeDash=[2, 3]).encode(x="q:Q")
    whisk = alt.Chart(bx).mark_rule(color=T["ink2"]).encode(y=y, x=alt.X("lo_adj:Q"), x2="hi_adj:Q")
    box = alt.Chart(bx).mark_bar(size=13, fill=T["surface"], stroke=T["ink2"], strokeWidth=1).encode(y=y, x="h1:Q", x2="h2:Q")
    med = alt.Chart(bx).mark_tick(size=15, thickness=2.5, color=T["ink"]).encode(y=y, x="med:Q")
    tks = alt.Chart(tk).mark_tick(size=11, thickness=1.6).encode(
        y=y, x=x, color=alt.condition("datum.is_ref", alt.value(T["bench"]), alt.value(T["us"])),
        opacity=alt.condition("hl[0] == 0 || (datum.tc >= hl[0] && datum.tc <= hl[1])", alt.Opacity("base_op:Q", scale=None), alt.value(0.1)),
        tooltip=tip)
    dtxt = alt.Chart(tx).mark_text(align="right", fontSize=10.5, color=T["ink2"]).encode(y=y, x=alt.value(w - 2), text="t:N")
    head = alt.Chart(pd.DataFrame([{"t": "Δq vs ref. · k"}])).mark_text(align="right", fontSize=10, color=T["muted"], dy=-8).encode(
        x=alt.value(w - 2), y=alt.value(0), text="t:N")
    allp = alt.layer(zero, tks, whisk, box, med, dtxt, head).properties(width=w, height=h, title=title("Totes les peticions"))
    xc = alt.X("ratio:Q", title="Freda ÷ baseline freda (log)", scale=alt.Scale(type="log", domain=[0.5, 8], base=2),
               axis=alt.Axis(values=[0.5, 1, 2, 4, 8], format=".1~f"))
    one = alt.Chart(pd.DataFrame([{"ratio": 1}])).mark_rule(color=T["bench"], strokeDash=[2, 3]).encode(x="ratio:Q")
    onet = alt.Chart(pd.DataFrame([{"ratio": 1, "t": "×1 = baseline freda"}])).mark_text(
        align="left", dx=3, fontSize=10, color=T["muted"], dy=-8).encode(x="ratio:Q", y=alt.value(0), text="t:N")
    ck["op"] = ck.apply(lambda r: (0.85 if r["cold_requests"] >= 100 else 0.35) * (0.45 if r["retired"] else 1), axis=1)
    ctk = alt.Chart(ck).mark_tick(size=11, thickness=1.6).encode(
        y=y, x=xc, color=alt.condition("datum.is_ref", alt.value(T["bench"]), alt.value(T["us"])),
        opacity=alt.Opacity("op:Q", scale=None),
        tooltip=[alt.Tooltip("version:N", title="Versió"), alt.Tooltip("label:N", title="Finestra"),
                 alt.Tooltip("cold_requests:Q", title="Peticions fredes"), alt.Tooltip("ratio:Q", title="× baseline freda", format=".2f")])
    cold = alt.layer(one, onet, ctk).properties(width=cw, height=h, title=title("Peticions fredes"))
    out = alt.hconcat(allp, cold.encode(y=alt.Y("version:N", sort=order, axis=None)), spacing=12)
    return config(out.add_params(HL))


# ----------------------------------------------------------------------------- V4 what sells
def v4_relations(cells, order, labels, w=150, h=230):
    d = pd.DataFrame(cells)
    y = alt.Y("obs_y:Q", title="Compres per 1.000 impressions (escala log de r + 0,5)",
              scale=alt.Scale(type="log", domain=[0.45, 45]),
              axis=alt.Axis(values=[0.5, 1, 1.5, 2.5, 5.5, 10.5, 20.5], labelExpr="format(datum.value - 0.5, '~g')"))
    x = alt.X("x:Q", title="Slot", scale=alt.Scale(domain=[0.5, 10.5], nice=False), axis=alt.Axis(values=[1, 2, 3, 4, 6, 7, 10], grid=False))
    fit = alt.Chart().mark_rule(color=T["guide"], strokeWidth=3).encode(x=alt.X("x0:Q"), x2="x1:Q", y=alt.Y("fit_y:Q"))
    conn = alt.Chart().mark_rule(color=T["guide"], strokeWidth=1).encode(x="x:Q", y="fit_y:Q", y2="obs_y:Q")
    ci = alt.Chart().mark_rule(color=T["us"], strokeWidth=1.2).encode(x="x:Q", y="lo_y:Q", y2="hi_y:Q")
    dot = alt.Chart().mark_point(size=48, strokeWidth=1.6, color=T["us"]).encode(
        x=x, y=alt.Y("obs_y:Q"), fill=alt.condition("datum.buys >= 10", alt.value(T["us"]), alt.value(T["surface"])),
        tooltip=[alt.Tooltip("rel_name:N", title="Relació"), alt.Tooltip("band:N", title="Slots"),
                 alt.Tooltip("impressions:Q", title="Impressions", format=",.0f"), alt.Tooltip("buys:Q", title="Compres"),
                 alt.Tooltip("rate:Q", title="Compres/1.000", format=".2f"), alt.Tooltip("lo_r:Q", title="IC95 inf.", format=".2f"),
                 alt.Tooltip("hi_r:Q", title="IC95 sup.", format=".2f"), alt.Tooltip("fit_r:Q", title="Ajust additiu", format=".2f"),
                 alt.Tooltip("res:Q", title="Residu ×", format=".2f")])
    lab = alt.Chart().mark_text(dy=-12, fontSize=10, fontWeight=600, color=T["ink2"]).encode(x="x:Q", y="obs_y:Q", text="res_label:N")
    layer = alt.layer(fit, conn, ci, dot, lab, data=d).encode(y=y).properties(width=w, height=h)
    fac = layer.facet(column=alt.Column("rel_label:N", sort=[labels[r] for r in order], title=None,
                                        header=alt.Header(labelAlign="left", labelAnchor="start", labelLimit=w + 30,
                                                          labelFontSize=11.5, labelExpr="split(datum.value, '|')", labelLineHeight=15)))
    return config(fac.resolve_scale(y="shared"))


# ----------------------------------------------------------------------------- V5 power
def v5_power(curve, gaps, n_final, w=470, h=250):
    c = pd.DataFrame(curve)
    g = pd.DataFrame(gaps)
    x = alt.X("n:Q", title="Peticions totals en un 50/50 (escala log)", scale=alt.Scale(type="log", domain=[500, 3_000_000]),
              axis=alt.Axis(values=[1000, 10000, 100000, 1000000], format="~s"))
    y = alt.Y("mde:Q", title="Diferència mínima detectable (compres/100, log)", scale=alt.Scale(type="log", domain=[0.01, 3]),
              axis=alt.Axis(values=[0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2], format="~g"))
    sc = alt.Scale(domain=["esperada", "real"], range=[T["expected"], T["realised"]])
    lines = alt.Chart(c).mark_line(strokeWidth=2).encode(
        x=x, y=y, detail="metric:N", color=alt.Color("metric:N", scale=sc, legend=None),
        strokeDash=alt.StrokeDash("metric:N", scale=alt.Scale(domain=["esperada", "real"], range=[[1, 0], [6, 4]]), legend=None),
        tooltip=[alt.Tooltip("metric:N", title="Mètrica"), alt.Tooltip("n:Q", title="Peticions", format=",.0f"),
                 alt.Tooltip("mde:Q", title="Diferència detectable (compres/100)", format=".2f"),
                 alt.Tooltip("minutes:Q", title="Minuts a 3 pet./s", format=",.0f")])
    lab = alt.Chart(c[c["label"] != ""]).mark_text(align="right", dx=-6, dy=12, fontSize=10.5, fontWeight=600).encode(
        x="n:Q", y="mde:Q", text="label:N", color=alt.Color("metric:N", scale=sc, legend=None))
    # labels sit below-left of the curves, away from the horizontal rules
    vr = pd.DataFrame([{"n": 10800, "t": "1 h"}, {"n": n_final, "t": "final (2 h)"}])
    vrule = alt.Chart(vr).mark_rule(color=T["guide"]).encode(x="n:Q")
    vtxt = alt.Chart(vr).mark_text(align="left", dx=3, fontSize=10, color=T["muted"], baseline="top").encode(x="n:Q", y=alt.value(2), text="t:N")
    hr = alt.Chart(g).mark_rule(strokeDash=[4, 3]).encode(
        y="mde:Q", color=alt.condition("datum.kind == 'lost'", alt.value(T["lost"]), alt.value(T["us"])))
    ht = alt.Chart(g[g["kind"] != "lost"]).mark_text(align="right", fontSize=10.5, fontWeight=600, baseline="bottom", dy=-2).encode(
        x=alt.value(w - 2), y="mde:Q", text="t:N", color=alt.value(T["us"]))
    hl_ = alt.Chart(g[g["kind"] == "lost"]).mark_text(align="left", fontSize=10.5, fontWeight=600, baseline="bottom", dy=-2).encode(
        x=alt.value(4), y="mde:Q", text="t:N", color=alt.value(T["lost"]))
    gx = g[g["n_star"].notna() & (g["n_star"] <= 3_000_000)]
    hit = alt.Chart(gx).mark_point(size=50, filled=True, color=T["us"]).encode(x="n_star:Q", y="mde:Q")
    return config(alt.layer(vrule, vtxt, hr, ht, hl_, lines, lab, hit).properties(width=w, height=h))
