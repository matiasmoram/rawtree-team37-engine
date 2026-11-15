"""Tauler de decisions de team_37 — Shiny for Python + Altair (Side Challenge Tukey, Datathon FME 2026, repte RawTree).

One view, simple on purpose (VI course: few views, many variables; titles = conclusions; one colour = one meaning;
minimal interactions with meaningful defaults): verdict + 4 KPIs + 4 charts + the decision table.
Numbers come from pipeline/render.py, so text, KPIs and charts agree. The app reloads by itself when the pipeline
rewrites data/dashboard_data.json (run_all.ps1).

Run:  .venv\\Scripts\\python.exe -m shiny run app\\app.py --port 8000   ->  http://127.0.0.1:8000
"""
from __future__ import annotations

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


def vega(id_, make):
    try:
        chart = make() if callable(make) else make
    except (ValueError, StopIteration, KeyError, IndexError):
        chart = None
    if chart is None:
        return ui.p("Sense dades en aquesta finestra (la final es publica després de les 12:00).", class_="tk-small")
    spec = json.dumps(chart.to_dict()).replace("</", "<\\/")
    return ui.HTML(f'<div id="c-{id_}" class="tk-chart"></div><script>TK.embed("{id_}", {spec});</script>')


def head(title, how):
    return ui.TagList(ui.span(title, class_="tk-title"),
                      ui.popover(ui.span(" ⓘ", class_="tk-info"), ui.p(how, style="font-size:12.5px;margin:0"),
                                 title="Com es llegeix", placement="bottom"))


def card(h, c):
    return ui.card(ui.card_header(ui.output_ui(h)), ui.output_ui(c), full_screen=True)


app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_radio_buttons("period", "Període", {"practice": "Pràctica", "final": "Final"}, selected="practice", inline=True),
        ui.input_slider("win", "Finestra (CET)", min=dt(T_MIN), max=dt(T_MAX), value=(dt(T_MIN), dt(T_MAX)),
                        step=timedelta(hours=1), time_format="%d/%m %H:%M", timezone="+0100", drag_range=True),
        ui.h6("Vigilar durant la final"),
        ui.output_ui("watch"),
        ui.h6("Llegenda"),
        ui.p(ui.HTML('<span style="color:#2a78d6;font-weight:700">blau</span> = team_37 o la versió que servim · '
                     '<span style="color:#d55e00;font-weight:700">vermelló</span> = pèrdua · negre discontinu = referència de '
                     "l'organització · gris = la resta d'equips."), class_="tk-small"),
        ui.output_ui("meta"),
        width=290, open="always",
    ),
    ui.head_content(
        ui.tags.link(rel="stylesheet", href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&display=swap"),
        ui.tags.link(rel="stylesheet", href="tukey.css"),
        ui.tags.script(src="vega.min.js"), ui.tags.script(src="vega-lite.min.js"), ui.tags.script(src="vega-embed.min.js"),
        ui.tags.script(src="tukey.js"),
    ),
    ui.output_ui("verdict"),
    ui.layout_columns(
        ui.value_box("Posició a l'última hora", ui.output_text("k1"), ui.output_text("k1s")),
        ui.value_box("Respostes a temps", ui.output_text("k2"), ui.output_text("k2s")),
        ui.value_box("El model, quan respon", ui.output_text("k3"), ui.output_text("k3s")),
        ui.value_box("En joc a la final", ui.output_text("k4"), ui.output_text("k4s")),
        col_widths=[3, 3, 3, 3], fill=False,
    ),
    ui.layout_columns(card("h1", "c1"), card("h2", "c2"), col_widths=[6, 6], fill=False),
    ui.layout_columns(card("h3", "c3"), card("h4", "c4"), col_widths=[6, 6], fill=False),
    ui.card(ui.card_header(ui.span("Decisions per a la final: punts en joc, predicció registrada i resultat", class_="tk-title")),
            ui.output_ui("ledger")),
    title=ui.div(ui.div("Datathon FME 2026 · Side Challenge Tukey · repte RawTree", class_="tk-eyebrow"),
                 ui.div("Tauler de decisions de team_37")),
    fillable=False, lang="ca", window_title="Tauler Tukey · team_37",
)


def server(input, output, session):
    @reactive.file_reader(DATA)
    def data():
        return json.loads(DATA.read_text())

    @reactive.calc
    def pred():
        return json.loads(R.PRED.read_text(encoding="utf-8"))

    @reactive.calc
    def window():
        if input.period() == "final":
            return R.FINAL_START, R.FINAL_END
        a, b = input.win()
        t0, t1 = a.timestamp(), b.timestamp()
        return (T_MIN, T_MAX) if t1 - t0 < 3 * 3600 else (t0, t1)

    @reactive.calc
    def P():
        D = dict(data())
        t0, t1 = window()
        period = "final" if input.period() == "final" else "practice"
        for key in ("windows15", "arms15", "field_hourly", "versions_hourly"):
            D[key] = [r for r in D[key] if t0 <= r["t"] < t1]
        try:
            res = R.build_period(D, period)
        except Exception:
            res = None
        if res is None:
            if period == "final":
                ui.notification_show("La final encara no té dades publicades: es mostra la pràctica.", duration=5)
            return R.build_period(data(), "practice")
        return res

    N = lambda: P()["N"]

    @reactive.calc
    def T():
        return R.texts(P(), pred(), input.period() == "final")

    @render.ui
    def verdict():
        items = [ui.tags.li(ui.span(d, class_="tk-did"), ui.strong(h + ". "), b) for d, h, b, _ in T()["verdict"]]
        return ui.div(ui.p(T()["h1"], class_="tk-h1"), ui.tags.ul(*items, class_="tk-verdict3"), class_="tk-top")

    @render.text
    def k1():
        return f"#{N()['sel_rank']}"

    @render.text
    def k1s():
        n = N()
        return f"{n['sel_label']} · amb el mateix model vam ser #{n['worst_rank']} a {n['worst_label']}"

    @render.text
    def k2():
        return R.pct(N()["sel_s"], 1)

    @render.text
    def k2s():
        n = N()
        return f"objectiu 98 % · mediana horària {R.pct(n['box_team_37']['med'], 0)} · mínim {R.pct(n['worst_s'], 0)}"

    @render.text
    def k3():
        return f"{R.f(N()['live_conv'], 2)} compres/100"

    @render.text
    def k3s():
        n = N()
        return f"{n['live']} · referència de l'organització {R.f(next(r['reference'] for r in data()['windows15'][-4:]), 2)}"

    @render.text
    def k4():
        return f"fins a {R.f(N()['d1_hi'], 1)} punts"

    @render.text
    def k4s():
        n = N()
        return f"per fiabilitat (D1), sobre 100 · canviar de model ≤ {R.f(max(n['d2'].values()) if n['d2'] else None, 1)}"

    @render.ui
    def h1():
        n = N()
        return head(f"Ens movem en horitzontal: el model és dels millors i el que ens fa caure és respondre tard "
                    f"(#{n['best_rank']} amb {R.pct(n['best_s'], 0)} a temps, #{n['worst_rank']} amb {R.pct(n['worst_s'], 0)})",
                    "Cada punt gris és un equip a l'última hora de la finestra. A la dreta = respon a temps; amunt = el seu model "
                    "ven més quan respon (compres/100 descomptant les respostes per defecte). Blau ple: team_37 ara; blau buit: "
                    "el mateix model a l'hora pitjor. Teoria: posició en escala comuna per a la relació entre dues variables "
                    "(Munzner); un to sobre gris (pop-out).")

    @render.ui
    def c1():
        t0, t1 = window()
        return vega("v1", lambda: C.field(data(), t0, t1))

    @render.ui
    def h2():
        n = N()
        b, tb = n["box_team_37"], n["box_top-6"]
        return head(f"Responem a temps el {R.pct(b['med'], 0)} de mediana (frontisses {R.f(b['h1'], 0)}–{R.f(b['h2'], 0)}) "
                    f"contra el {R.f(tb['h1'], 0)}–{R.f(tb['h2'], 0)} % del top-6: la caiguda de {n['worst_label']} "
                    f"va costar {R.f(n['gain_worst'], 1)} punts",
                    "On-time per finestra de 15 minuts. Blau: team_37; gris: mediana dels 6 primers equips; discontinu: objectiu "
                    "del 98 %. Una petició no resposta a temps rep la llista per defecte de l'organització. Teoria: línia per al "
                    "temps; resum de cinc números de Tukey al títol.")

    @render.ui
    def c2():
        t0, t1 = window()
        return vega("v2", lambda: C.reliability(data(), t0, t1))

    @render.ui
    def h3():
        n = N()
        tie = n["comp"].get("fz-v10-nocorr")
        lead = (f"fz-v9a i fz-v10-nocorr empaten (diferència aparellada {R.f(tie['dconv'], 2, sign=True)} compres/100 en "
                f"{tie['k']} finestres); la resta, per sota" if tie and tie.get("paired") else "Les versions fz són les millors")
        return head(f"{lead} → servir-ne una de sola, sense repartir el trànsit (en 2 h un 50/50 només veu diferències ≥ "
                    f"{R.f(n['mde_e'], 2)})",
                    "Caixa de Tukey per versió (bigotis fins a 1,5 vegades l'interval entre quartils): diferència de compres/100 "
                    "respecte a la referència de l'organització a la mateixa finestra de 15 min, per comparar hores diferents de "
                    "forma justa. Blau: la versió triada per a la final (fz-v10-nocorr, 09:43). Teoria: distribucions, no barres "
                    "de mitjanes.")

    @render.ui
    def c3():
        t0, t1 = window()
        return vega("v3", lambda: C.versions(data(), t0, t1))

    @render.ui
    def h4():
        n = N()
        return head(f"El slot 1 fa el {R.pct(n['slot1_share'], 0)} de les compres: a dalt, productes vistos a la sessió i "
                    f"del carret; un producte ja comprat gairebé no es ven ({R.f(n['bb1'], 1)} per 1.000)",
                    "Compres per cada 1.000 vegades que un producte es mostra en primera posició, segons la seva relació amb el "
                    "comprador. Barres des de zero, ordenades per valor. Vermelló: posició malgastada (ja comprat). Dades de "
                    "pràctica (team_37.feedback).")

    @render.ui
    def c4():
        return vega("v4", lambda: C.slot_one(data()))

    @render.ui
    def watch():
        base = R.build_period(data(), "practice")
        t = R.texts(base, pred(), False)
        lis = [ui.tags.li(ui.strong(a), f" → {b}") for a, b, _ in t["watch"]]
        return ui.TagList(ui.p(t["alarm"], class_="tk-alarm") if t.get("alarm") else None, ui.tags.ul(*lis, class_="tk-watch"))

    @render.ui
    def meta():
        p_ = pred()
        built = datetime.fromtimestamp(DATA.stat().st_mtime, tz=CET).strftime("%d/%m %H:%M")
        return ui.p(f"Prediccions registrades {p_['registered_at_cet']} (sha {p_['sha256'][:8]}). Dades: API pública de RawTree, "
                    f"base de dades team_37, Notion i GitHub de l'equip. Actualitzat {built} CET.", class_="tk-small")

    @render.ui
    def ledger():
        base = R.build_period(data(), "practice")
        F = R.build_period(data(), "final") or R.build_final_db(data(), base)
        out = R.outcomes(pred(), F, base)
        rows = R.ledger_rows(base, pred(), out)
        trs = []
        for r in rows:
            vals = [(lab, v) for lab, v in r.get("ticks", []) if v is not None]
            stake = (" · ".join(f"{lab} {R.f(v, 1)}" for lab, v in vals)) if vals else r.get("note", "–")
            oc = r.get("outcome")
            res = f"{oc[0]} {oc[1]}" if oc else "pendent (després de les 12:00)"
            cls = "ok" if oc and oc[0] == "✓" else "ko" if oc and oc[0] == "✗" else "pend"
            trs.append(f"<tr><th><span class='tk-did'>{r['id']}</span>{R.esc(r['what'])}</th><td>{R.esc(stake)}</td>"
                       f"<td>{R.esc(r['pred'])}</td><td class='outc {cls}'>{R.esc(res)}</td></tr>")
        return ui.HTML("<table class='tk-table'><thead><tr><th>Decisió</th><th>Punts finals en joc</th><th>Predicció (abans de la final)</th>"
                       f"<th>Resultat a la final</th></tr></thead><tbody>{''.join(trs)}</tbody></table>")


app = App(app_ui, server, static_assets=APP / "www")
