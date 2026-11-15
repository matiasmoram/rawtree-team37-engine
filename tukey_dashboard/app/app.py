"""Tauler de decisions de team_37 — Shiny for Python + Altair (Side Challenge Tukey, Datathon FME 2026, repte RawTree).

Two periods, one layout. Pràctica = the exploratory evidence behind the decisions. Final = confirmatory: the predictions
frozen before the final (Sun 10:00-12:00 CET) checked against it (RawTree DB + the official API aggregate).

Design rules (VI course, UPC; see docs/vi_theory.md and README):
- Overview first, details on demand (Shneiderman): one headline, four KPIs, four charts, one decision register;
  every longer explanation sits behind the ⓘ of its card.
- Minimum amount of text, keep headers simple, label directly (Good practices part 2, "Copy & labels"); the text that
  stays is annotation inside the charts, where readers find it useful (Stokes & Hearst 2022, homework reading).
- Start with greys, one accent: blue = team_37 / what we serve; vermillion = points lost; black dashed = organisers'
  reference; grey = everyone else. No red/green pairs; status always glyph + word (colour-blindness lecture).
- KPIs as bullet charts (value bar + target tick + reference tick), not gauges: lengths beat angles.
- Working memory holds 3-4 chunks: 4 KPIs, 4 charts.
Numbers come from pipeline/render.py, so text, KPIs and charts agree. The app reloads by itself when the pipeline
rewrites data/dashboard_data.json (run_all.ps1 / run_all.sh).

Run:  .venv/bin/python -m shiny run app/app.py --port 8000   ->  http://127.0.0.1:8000
"""
from __future__ import annotations

import html
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shiny import App, reactive, render, ui

APP = Path(__file__).resolve().parent
ROOT = APP.parent
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(APP))
import charts as C  # noqa: E402
import render as R  # noqa: E402

DATA = ROOT / "data" / "dashboard_data.json"
CET = timezone(timedelta(hours=1))
D0 = json.loads(DATA.read_text())
T_MIN = min(r["t"] for r in D0["windows15"])
T_MAX = min(max(r["t"] for r in D0["windows15"] if r["t"] < R.FINAL_START) + 900, R.FINAL_START)
dt = lambda t: datetime.fromtimestamp(t, tz=CET)
E = lambda s: html.escape(str(s), quote=True)


# ------------------------------------------------------------------------------------------------ small builders
def vega(id_, make):
    try:
        chart = make() if callable(make) else make
    except (ValueError, StopIteration, KeyError, IndexError, TypeError):
        chart = None
    if chart is None:
        return ui.p("Sense dades per a aquesta vista en aquest període.", class_="tk-empty")
    spec = json.dumps(chart.to_dict()).replace("</", "<\\/")
    return ui.HTML(f'<div id="c-{id_}" class="tk-chart" role="img"></div><script>TK.embed("{id_}", {spec});</script>')


def head(title, takeaway, enc, how=""):
    """Card header. Title = what the chart shows (variables, unit, period: "a title on the graph", VI course);
    takeaway = the message in one line (explanatory vis); the encoding and the long explanation on demand (ⓘ)."""
    pop = ui.TagList(ui.p(ui.strong("Com es llegeix. "), enc, class_="tk-pop"), ui.p(how, class_="tk-pop") if how else None)
    return ui.div(
        ui.div(ui.span(title, class_="tk-title"),
               ui.popover(ui.tags.button("i", class_="tk-info", **{"aria-label": "Com es llegeix"}), pop,
                          title="Com es llegeix", placement="left")),
        ui.div(takeaway, class_="tk-take") if takeaway else None)


def card(h, c):
    return ui.card(ui.card_header(ui.output_ui(h)), ui.output_ui(c), class_="tk-card", full_screen=True)


def bullet(lo, hi, value, ticks=(), bar_class="", band=None):
    """Bullet chart in HTML: bar = value; ticks = (value, label, css class); optional band = (from, to, label)."""
    pos = lambda v: max(0.0, min(100.0, 100 * (v - lo) / (hi - lo)))
    parts = []
    if band:
        parts.append(f'<i class="bb-band" style="left:{pos(band[0]):.1f}%;width:{pos(band[1]) - pos(band[0]):.1f}%"></i>')
    if value is not None:
        parts.append(f'<i class="bb-bar {bar_class}" style="width:{pos(value):.1f}%"></i>')
    labs = []
    for v, lab, cls in ticks:
        if v is None:
            continue
        parts.append(f'<i class="bb-tick {cls}" style="left:{pos(v):.1f}%" title="{E(lab)}"></i>')
        edge = " r" if pos(v) > 82 else ""   # keep right-hand labels inside the card
        labs.append(f'<span class="{cls}{edge}" style="left:{pos(v):.1f}%">{E(lab)}</span>')
    return f'<div class="bb">{"".join(parts)}</div><div class="bb-labs">{"".join(labs)}</div>'


def kpi(label, value, viz, note=""):
    return (f'<div class="kpi"><div class="kpi-l">{E(label)}</div><div class="kpi-v">{value}</div>{viz}'
            + (f'<div class="kpi-n">{E(note)}</div>' if note else "") + "</div>")


def rank_strip(rank, n, other=None, other_lab="", top=None, top_lab=""):
    """Positions 1..n on one line (1 = left): a filled dot for us, a hollow one for the comparison."""
    pos = lambda r: 100 * (r - 1) / max(n - 1, 1)
    s = '<div class="rs"><i class="rs-line"></i>'
    if top:
        s += f'<i class="rs-top" style="width:{pos(top) + 1.2:.1f}%"></i>'
    if other:
        s += f'<i class="rs-dot hollow" style="left:{pos(other):.1f}%" title="{E(other_lab)}"></i>'
    s += f'<i class="rs-dot" style="left:{pos(rank):.1f}%"></i></div>'
    labs = (f'<span class="us" style="left:0%">{E(top_lab)}</span>' if top else '<span style="left:0%">#1</span>')
    labs += f'<span style="left:100%">#{n}</span>'
    if other:
        labs += f'<span class="lost" style="left:{pos(other):.1f}%">{E(other_lab)}</span>'
    return s + f'<div class="bb-labs">{labs}</div>'


GLYPH = {"✓": ("ok", "✓", "confirmat"), "✗": ("ko", "✗", "refutat"), "~": ("na", "–", "sense veredicte"),
         "…": ("na", "…", "pendent")}


# ------------------------------------------------------------------------------------------------ layout
app_ui = ui.page_fillable(
    ui.head_content(
        ui.tags.link(rel="stylesheet", href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&display=swap"),
        ui.tags.link(rel="stylesheet", href="tukey.css"),
        ui.tags.script(src="vega.min.js"), ui.tags.script(src="vega-lite.min.js"), ui.tags.script(src="vega-embed.min.js"),
        ui.tags.script(src="tukey.js"),
        ui.tags.title("Tauler Tukey · team_37"),
    ),
    ui.div(
        ui.div(ui.div("Datathon FME 2026 · Side Challenge Tukey", class_="tk-eyebrow"),
               ui.h1("Tauler de decisions de team_37", class_="tk-brand"), class_="tk-brandbox"),
        ui.div(
            ui.input_radio_buttons("period", None, {"practice": "Pràctica", "final": "Final"}, selected="final", inline=True),
            ui.panel_conditional(
                "input.period === 'practice'",
                ui.input_slider("win", None, min=dt(T_MIN), max=dt(T_MAX), value=(dt(T_MIN), dt(T_MAX)),
                                step=timedelta(hours=1), time_format="%d/%m %H:%M", timezone="+0100", drag_range=True, width="300px")),
            class_="tk-controls"),
        ui.HTML('<div class="tk-legend" aria-label="Llegenda">'
                '<span><i class="sw us"></i>team_37</span><span><i class="sw lost"></i>pèrdua</span>'
                '<span><i class="sw ref"></i>referència de l\'organització</span><span><i class="sw grey"></i>altres equips</span></div>'),
        class_="tk-top"),
    ui.div(
        ui.output_ui("hero"),
        ui.output_ui("kpis"),
        ui.output_ui("timeline_card"),
        ui.div(card("h1", "c1"), card("h2", "c2"), card("h3", "c3"), card("h4", "c4"), class_="tk-grid"),
        ui.output_ui("ledger"),
        ui.output_ui("foot"),
        class_="tk-main"),
    lang="ca", fillable_mobile=False, padding=0, gap=0, class_="tk-page",
)


# ------------------------------------------------------------------------------------------------ server
def server(input, output, session):
    @reactive.file_reader(DATA)
    def data():
        return json.loads(DATA.read_text())

    @reactive.calc
    def pred():
        return json.loads(R.PRED.read_text(encoding="utf-8"))

    @reactive.calc
    def BASE():
        return R.build_period(data(), "practice", with_specs=False)

    @reactive.calc
    def FIN():
        """Final: DB summary merged with the official API aggregate when published."""
        D, base = data(), BASE()
        db = R.build_final_db(D, base, with_specs=False)
        try:
            api = R.build_period(D, "final", with_specs=False)
        except Exception:
            api = None
        if not db and not api:
            return None
        N = dict(db["N"]) if db else {"period": "final"}
        if api:
            N.update(api["N"])
            N["source"] = "api"
        N["has_api"] = bool(api) or bool(N.get("official"))
        return {"N": N, "specs": {}}

    @reactive.calc
    def OUT():
        return R.outcomes(pred(), FIN(), BASE())

    @reactive.calc
    def is_final():
        return input.period() == "final" and FIN() is not None

    @reactive.effect
    def _no_final_yet():
        if input.period() == "final" and FIN() is None:
            ui.notification_show("La final encara no té dades: es mostra la pràctica.", duration=5)

    @reactive.calc
    def window():
        a, b = input.win()
        t0, t1 = a.timestamp(), b.timestamp()
        return (T_MIN, T_MAX) if t1 - t0 < 3 * 3600 else (t0, t1)

    @reactive.calc
    def P():
        D = dict(data())
        t0, t1 = window()
        for key in ("windows15", "arms15", "field_hourly", "versions_hourly"):
            D[key] = [r for r in D[key] if t0 <= r["t"] < t1]
        try:
            res = R.build_period(D, "practice", with_specs=False)
        except Exception:
            res = None
        return res or BASE()

    N = lambda: P()["N"]

    def H(title, takeaway, enc, how=""):
        """Practice is the live operating view (what we would have watched during the datathon): it shows the data and
        how to read it, but states no conclusions; takeaways only appear in the final (confirmatory) view."""
        return head(title, takeaway if is_final() else None, enc, how)
    F = lambda: FIN()["N"]
    result = lambda: data().get("manual", {}).get("final_result", {}).get("overall")

    def counts():
        o = OUT()
        ok = sum(v[0] == "✓" for v in o.values())
        return ok, sum(v[0] in "✓✗" for v in o.values())

    # ---------------------------------------------------------------- headline
    @render.ui
    def hero():
        if is_final():
            f, (ok, m) = F(), counts()
            res = result()
            h = (f"{(res + ' a la final').capitalize() if res else 'Final'}: {R.pct(f['served_total'], 3)} de respostes a temps "
                 f"i {ok} de {m} prediccions confirmades.")
            sub = "Final del diumenge, de 10 a 12 h."
            tag = "CONFIRMATORI"
        else:
            n = N()
            h = (f"Ara ({n['sel_label']}): #{n['sel_rank']} de 42, {R.pct(n['sel_s'], 0)} de respostes a temps i "
                 f"{R.f(n['sel_conv'], 2)} compres per 100.")
            sub = "Pràctica, de dissabte a la tarda a diumenge al matí. Mou la barra de dalt per veure una altra franja."
            tag = "EXPLORATORI"
        return ui.div(ui.span(tag, class_=f"tk-tag t-{tag.lower()}"), ui.h2(h, class_="tk-h1"), ui.p(sub, class_="tk-lede"),
                      class_="tk-hero")

    # ---------------------------------------------------------------- KPIs (bullet charts)
    @render.ui
    def kpis():
        if is_final():
            f, o = F(), OUT()
            rf, rp = f.get("real"), f.get("real_prac_live")
            base_rate = ((f.get("real_prac") or {}).get("(fallback:missing)") or {}).get("rate")
            glyphs = "".join(
                f'<span class="g {GLYPH[o[k][0]][0]}" title="{E(k + ": " + GLYPH[o[k][0]][2])}">{k}<b>{GLYPH[o[k][0]][1]}</b></span>'
                for k in ("D1", "D2", "D3", "D5", "D6") if k in o)
            ok, m = counts()
            cards = [
                kpi("Respostes a temps", R.pct(f["served_total"], 3),
                    bullet(50, 100, f["served_total"], [(98, "objectiu 98", "tgt"), (f.get("prac_served"), f"pràctica {R.f(f.get('prac_served'), 0)}", "ref")]),
                    f"pitjor finestra de 10 min: {R.pct(f['w_min'], 1)}"),
                kpi("Compres reals per 100", R.f(rf["rate"], 2) if rf else "–",
                    bullet(0, 3, rf["rate"] if rf else None, [(rp["rate"] if rp else None, f"pràctica {R.f(rp['rate'], 2) if rp else ''}", "ref"),
                                                             (base_rate, "baseline", "base")],
                           band=(rf["lo"], rf["hi"], "IC95") if rf else None),
                    f"interval del 95 %: {R.f(rf['lo'], 2)}–{R.f(rf['hi'], 2)}" if rf else ""),
                kpi("Prediccions confirmades", f"{ok} de {m}", f'<div class="glyphs">{glyphs}</div>', "D4 no es podia mesurar"),
                kpi("Resultat", E((result() or (f"#{f['sel_rank']}" if f.get("sel_rank") else "pendent")).capitalize()),
                    rank_strip(f["sel_rank"], f["n_teams"], top=5, top_lab="top 5") if f.get("sel_rank") else "",
                    f"#{f['sel_rank']} de {f['n_teams']} en conversió" if f.get("sel_rank") else "l'API encara no ho ha publicat"),
            ]
        else:
            n = N()
            ref = next((r["reference"] for r in reversed(data()["windows15"]) if r.get("reference")), None)
            cards = [
                kpi("Posició, última hora", f"#{n['sel_rank']}",
                    rank_strip(n["sel_rank"], 42, other=n["worst_rank"], other_lab=f"#{n['worst_rank']} {n['worst_label']}"),
                    f"mateix model a {n['worst_label']}: #{n['worst_rank']}"),
                kpi("Respostes a temps", R.pct(n["sel_s"], 0),
                    bullet(0, 100, n["box_team_37"]["med"], [(98, "objectiu 98", "tgt"), (n["worst_s"], f"pitjor {R.f(n['worst_s'], 0)}", "lost")]),
                    f"barra = mediana horària ({R.pct(n['box_team_37']['med'], 0)})"),
                kpi("Compres per 100, quan respon", R.f(n["live_conv"], 2),
                    bullet(0, 3, n["live_conv"], [(ref, f"referència {R.f(ref, 2)}", "ref")]), n["live"]),
                kpi("Versió principal, últimes 2 h", R.pct(n.get("live_share"), 0),
                    bullet(0, 100, n.get("live_share"), [(95, "objectiu 95", "tgt")]),
                    n["live"]),
            ]
        return ui.HTML(f'<div class="tk-kpis">{"".join(cards)}</div>')

    # ---------------------------------------------------------------- chart cards
    @render.ui
    def h1():
        if is_final():
            f = F()
            return H("Respostes a temps per finestra de 10 minuts: pràctica vs final",
                        f"De {R.pct(f['prac_served'], 1)} a la pràctica a {R.pct(f['served_total'], 3)} a la final: cap "
                        "finestra per sota de l'objectiu del 98 %.",
                        "Cada punt és una finestra de 10 minuts; la caixa grisa és el resum de Tukey de la pràctica "
                        "(frontisses, mediana i bigotis fins a 1,5·H); la línia discontínua blava, l'objectiu del 98 %.",
                        f"Pràctica: el {R.pct(f['prac_below95'], 0)} de les finestres van quedar per sota del 95 % (frontissa inferior "
                        f"{R.pct(f['prac_box']['h1'], 0)}). Final: cap de les {f['n_windows']} per sota del 98 % (mínim "
                        f"{R.pct(f['final_box']['min'], 1)}). Una resposta tardana compta com a no resposta, igual que a l'on-time "
                        "oficial. Font: team_37.feedback.")
        n = N()
        return H(f"Qualitat del model vs respostes a temps, tots els equips ({n['sel_label']})",
                    f"Amb el mateix model vam ser #{n['best_rank']} responent-ho tot i #{n['worst_rank']} amb el "
                    f"{R.pct(n['worst_s'], 0)} a temps: el que ens feia caure era la fiabilitat.",
                    "Cada punt és un equip. Eix horitzontal: % de peticions respostes a temps. Eix vertical: compres per 100 "
                    "peticions quan el model respon.",
                    f"Blau ple: team_37 ara (#{n['best_rank'] if n['sel_rank'] == n['best_rank'] else n['sel_rank']}); blau buit: el "
                    f"mateix model a {n['worst_label']}, quan només responia el {R.pct(n['worst_s'], 0)} (#{n['worst_rank']}). La "
                    "fletxa és el que hauríem guanyat responent-ho tot. Eix vertical: compres per 100 descomptant les respostes "
                    "per defecte, perquè una petició no resposta rep la llista baseline. Teoria: dispersió per a una relació entre "
                    "dues variables; un sol to sobre gris.")

    @render.ui
    def c1():
        if is_final():
            return vega("v1", lambda: C.final_reliability(F()))
        t0, t1 = window()
        return vega("v1", lambda: C.field(data(), t0, t1))

    @render.ui
    def h2():
        if is_final() and F().get("field_final"):
            f = F()
            top = f["field_final"][:5]
            return H("Compres esperades per 100 vs respostes a temps, els 42 equips a la final",
                        f"Som #{f['sel_rank']} de {f['n_teams']} en conversió ({R.f(f['sel_conv'], 2)}); gairebé tots els equips "
                        "responen ~100 %, ara la diferència és el model.",
                        "Cada punt és un equip; mètrica oficial de l'API per a tota la final (10:00–12:00). Línies discontínues: "
                        "referència i baseline de l'organització.",
                        f"{R.f(f['sel_conv'], 2)} compres esperades per 100 peticions, a {R.f(f['top_conv'] - f['sel_conv'], 2)} del "
                        f"primer i a {R.f(f['sel_conv'] - f['ref_conv'], 2, sign=True)} de la referència. Gairebé tots els equips "
                        "forts responen ~100 % a temps: a la pràctica ens moviem en horitzontal (fiabilitat), aquí ja no. Primers "
                        "cinc en conversió: " + ", ".join(f"{r['team']} {R.f(r['conv'], 2)}" for r in top) + ".")
        if is_final():
            return H("Latència p95 per hora: pràctica vs final", "La latència no ha canviat: la millora ve d'un sol "
                        "writer estable, no d'anar més ràpid.", "Cada punt és una hora; caixa de mínim a màxim.")
        n = N()
        return H("Respostes a temps de team_37 per finestra de 15 minuts, pràctica",
                    f"La caiguda del writer de dg 01h ens va costar {R.f(n['gain_worst'], 0)} punts en una hora; el top-6 "
                    "es manté a prop del 100 %.",
                    "Línia blava: team_37; línia grisa: mediana dels sis primers equips de cada finestra; discontínua: "
                    "objectiu del 98 %.",
                    f"Mediana horària {R.pct(n['box_team_37']['med'], 0)} (frontisses {R.f(n['box_team_37']['h1'], 0)}–"
                    f"{R.f(n['box_team_37']['h2'], 0)}) contra {R.f(n['box_top-6']['h1'], 0)}–{R.f(n['box_top-6']['h2'], 0)} % "
                    "del top-6. Una petició no resposta a temps rep la llista per defecte de l'organització. Arrossega a la "
                    "barra de dalt per filtrar les hores.")

    @render.ui
    def c2():
        if is_final():
            if F().get("field_final"):
                return vega("v2", lambda: C.final_field(F()))
            return vega("v2", lambda: C.final_latency(data()))
        t0, t1 = window()
        return vega("v2", lambda: C.reliability(data(), t0, t1))

    @render.ui
    def h3():
        if is_final():
            f = F()
            rf, rp = f.get("real"), f.get("real_prac_live")
            if not (rf and rp):
                return H("Compres reals per 100 peticions de la versió servida", "", "Sense dades.")
            return H("Compres reals per 100 peticions amb interval del 95 %: final vs pràctica",
                        f"{f['live']} fa {R.f(rf['rate'], 2)} a la final i {R.f(rp['rate'], 2)} a la pràctica: els intervals "
                        "se solapen, el model ven el que prometia.",
                        "Punt = compres reals per 100 peticions; línia = interval del 95 % (Poisson exacte). Blau: la final; "
                        "gris: la pràctica.",
                        f"{f['live']}: {R.f(rf['rate'], 2)} a la final contra {R.f(rp['rate'], 2)} a la pràctica; els intervals se "
                        "solapen. Blau: la final; gris: la pràctica (la mateixa versió, l'anterior i la llista baseline). Són "
                        f"compres reals, amb sort; la mètrica oficial (sense sort) dona q {R.f(f.get('live_med'), 0)}, per sota del "
                        "que esperàvem, però la referència també va caure: la final era més difícil.")
        n = N()
        tie = n["comp"].get("fz-v10-nocorr")
        take = (f"fz-v9a i fz-v10-nocorr empaten (diferència {R.f(tie['dconv'], 2, sign=True)}); la resta de versions "
                "queden per sota de la referència." if tie and tie.get("paired") else f"{n['live']} és la millor versió.")
        return H("Compres per 100 de cada versió respecte a la referència, per finestra de 15 minuts", take,
                    "Cada caixa resumeix les finestres de 15 minuts d'una versió (frontisses, mediana, bigotis fins a 1,5·H; "
                    "punts = valors fora de les tanques). 0 = igual que la referència de l'organització a la mateixa finestra.",
                    (f"Diferència aparellada fz-v9a − nocorr: {R.f(tie['dconv'], 2, sign=True)} compres/100 en {tie['k']} "
                     "finestres compartides, dins del soroll. " if tie and tie.get("paired") else "")
                    + f"Amb el trànsit de 2 h, un 50/50 entre dues versions només detecta diferències ≥ {R.f(n['mde_e'], 2)} "
                    "compres/100. Blau: fz-v10-nocorr.")

    @render.ui
    def c3():
        if is_final():
            return vega("v3", lambda: C.final_realised(F()))
        t0, t1 = window()
        return vega("v3", lambda: C.versions(data(), t0, t1))

    @render.ui
    def h4():
        if is_final():
            f = F()
            return H("Compres per 1.000 impressions al slot 1, per relació amb el comprador: pràctica vs final",
                        f"El patró es repeteix: els productes vistos a la sessió continuen a dalt, i els ja comprats ocupen "
                        f"només l'{R.pct(f.get('bb_all'), 1)} dels slots.",
                        "Marca negra: la pràctica; punt blau amb línia: la final amb interval del 95 %.",
                        f"El slot 1 fa el {R.pct(f.get('slot1_share'), 0)} de les compres (predicció ≥ 35 %) i els productes ja "
                        f"comprats ocupen l'{R.pct(f.get('bb_all'), 1)} dels slots (≤ 1,5 %). Si el punt cau sobre la marca o la "
                        "supera, la regla apresa a la pràctica es manté amb dades noves.")
        n = N()
        return H("Compres per 1.000 impressions al slot 1, segons la relació del producte amb el comprador",
                    f"El slot 1 fa el {R.pct(n['slot1_share'], 0)} de les compres: hi venen els productes vistos a la sessió, "
                    "i els ja comprats gairebé gens.",
                    "Una barra per relació, des de zero i ordenades de més a menys; vermelló = posició malgastada.",
                    f"A dalt, productes vistos a la sessió i al carret. Un producte ja comprat gairebé no es ven "
                    f"({R.f(n['bb1'], 1)} per 1.000): per això el vet a recompres (D3). Barres des de zero, ordenades.")

    @render.ui
    def c4():
        if is_final():
            return vega("v4", lambda: C.final_slot_one(data()))
        return vega("v4", lambda: C.slot_one(data()))

    @render.ui
    def timeline_card():
        if is_final():
            return None
        t0, t1 = window()
        how = ("Cada línia és una versió del recomanador que va servir trànsit de veritat (més de 5.000 peticions en total), "
               "amb la mètrica oficial de l'API calculada hora a hora (hores amb ≥ 300 peticions). Els punts grisos són proves "
               "curtes. Negre discontinu: la referència de l'organització; gris puntejat: la baseline. Línies verticals: canvis "
               "importants (registre de decisions). Passa el ratolí per sobre d'una versió per aïllar-la.")
        return ui.card(ui.card_header(head("Compres esperades per 100 peticions de cada versió que hem servit, hora a hora",
                                           None, how)),
                       vega("v5", lambda: C.timeline(data(), t0, t1)), class_="tk-card", full_screen=True)

    # ---------------------------------------------------------------- decision register
    @render.ui
    def ledger():
        base, out = BASE(), OUT()
        rows = R.ledger_rows(base, pred(), out)
        stakes = [v for r in rows for _, v in r.get("ticks", []) if v is not None]
        top = max(5.0, (int(max(stakes + [1]) / 5) + 1) * 5)
        trs = []
        for r in rows:
            ticks = [(lab, v) for lab, v in r.get("ticks", []) if v is not None]
            if ticks:
                hi = max(v for _, v in ticks)
                track = (f'<div class="st"><i class="st-bar{" lost" if r["id"] == "D1" else ""}" style="width:{100 * hi / top:.1f}%"></i></div>'
                         f'<span class="st-l">fins a {R.f(hi, 1)}</span>')
            else:
                track = '<span class="st-l muted">–</span>'
            oc = r.get("outcome")
            cls, g, word = GLYPH[oc[0]] if oc else ("na", "…", "pendent")
            detail = oc[1] if oc else "després de les 12:00"
            short = detail.split(";")[0].split(" (")[0] if len(detail) > 60 else detail
            oc_td = (f'<td class="oc {cls}" title="{E(detail)}"><b>{g} {word}</b><span>{E(short)}</span></td>'
                     if is_final() else "")
            trs.append(f'<tr><td><span class="did">{r["id"]}</span></td><td class="what">{E(r["what"])}</td>'
                       f'<td class="stake">{track}</td><td class="pred">{E(r["pred"])}</td>{oc_td}</tr>')
        return ui.div(
            ui.div(ui.span("Decisions per a la final: punts en joc, predicció registrada i resultat" if is_final()
                           else "Decisions per a la final: punts en joc i predicció", class_="tk-title"),
                   ui.span(f"Prediccions fixades a les {pred()['registered_at_cet'][-5:]}, abans de la final.", class_="tk-sub inline"),
                   class_="tk-lhead"),
            ui.HTML('<table class="tk-ledger"><thead><tr><th></th><th>Decisió</th><th>Punts en joc (sobre 100)</th>'
                    f'<th>Predicció</th>{"<th>A la final</th>" if is_final() else ""}</tr></thead><tbody>{"".join(trs)}</tbody></table>'),
            class_="tk-card tk-ledgerbox")

    @render.ui
    def foot():
        built = datetime.fromtimestamp(DATA.stat().st_mtime, tz=CET).strftime("%d/%m %H:%M")
        return ui.HTML(
            '<footer class="tk-foot"><details><summary>Mètode, fonts i per què aquests gràfics</summary><div class="cols">'
            "<p><b>Mètriques.</b> Conversió = compres esperades per 100 peticions (probabilitat del simulador, sense sort). "
            "Puntuació = 100·(equip − baseline)/(oracle − baseline). Una petició no resposta a temps rep la llista baseline, "
            "d'on equip = on-time·model + (1 − on-time)·baseline.</p>"
            "<p><b>Tukey.</b> Caixes amb frontisses i bigotis fins a 1,5·H, mostrant també cada observació; anàlisi exploratòria "
            "a la pràctica → prediccions congelades amb hash → confirmació a la final.</p>"
            "<p><b>VI.</b> Vista general i detall a demanda (ⓘ); títols = conclusions; etiquetes directes; grisos i un sol "
            "accent; KPI com a <i>bullet charts</i>; estat amb glif + paraula, mai només color.</p>"
            "<p><b>Fonts.</b> API pública datathon.rawtree.dev (classificació), base de dades RawTree (team_37.feedback, "
            "submissions, shop.*), Notion i repositori de l'equip.</p>"
            f"</div></details><span>Actualitzat {built} CET</span></footer>")


app = App(app_ui, server, static_assets=APP / "www")
