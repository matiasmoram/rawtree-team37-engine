"""Tauler de decisions de team_37 — Shiny for Python + Altair (Side Challenge Tukey, Datathon FME 2026, repte RawTree).

Two periods share the same layout. Pràctica = exploratory evidence behind the decisions. Final = confirmatory: the frozen
predictions checked against the final (Sun 10:00-12:00 CET), from the RawTree DB while the public API hides the leaderboard,
plus the official metric once the API publishes it.

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
        return ui.p("Sense dades per a aquesta vista en aquest període.", class_="tk-small")
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
        ui.panel_conditional(
            "input.period === 'practice'",
            ui.input_slider("win", "Finestra (CET)", min=dt(T_MIN), max=dt(T_MAX), value=(dt(T_MIN), dt(T_MAX)),
                            step=timedelta(hours=1), time_format="%d/%m %H:%M", timezone="+0100", drag_range=True)),
        ui.output_ui("watch_head"),
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
        ui.value_box(ui.output_text("t1"), ui.output_text("k1"), ui.output_text("k1s")),
        ui.value_box(ui.output_text("t2"), ui.output_text("k2"), ui.output_text("k2s")),
        ui.value_box(ui.output_text("t3"), ui.output_text("k3"), ui.output_text("k3s")),
        ui.value_box(ui.output_text("t4"), ui.output_text("k4"), ui.output_text("k4s")),
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
    def BASE():
        return R.build_period(data(), "practice", with_specs=False)

    @reactive.calc
    def FIN():
        """Final: DB summary (always, once the final has started) merged with the official API numbers when published."""
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
        if period == "final":
            return BASE()
        try:
            res = R.build_period(D, period, with_specs=False)
        except Exception:
            res = None
        return res or BASE()

    N = lambda: P()["N"]

    @reactive.calc
    def T():
        return R.texts(P(), pred(), input.period() == "final")

    def final_text():
        F, o = FIN()["N"], OUT()
        ok = [k for k, v in o.items() if v[0] == "✓"]
        ko = [k for k, v in o.items() if v[0] == "✗"]
        rf, rp = F.get("real"), F.get("real_prac_live")
        h = (f"Final ({R.hm(F['t_first'])}–{R.hm(F['t_last'])} CET{'' if F.get('complete') else ', en curs'}): "
             f"{R.pct(F['served_total'], 3)} de les peticions respostes a temps, una sola versió ({F.get('live')}, "
             f"{R.pct(F.get('live_share'), 0)}) i {R.f(rf['rate'], 2) if rf else '–'} compres reals per 100. "
             f"{len(ok)} de {len(ok) + len(ko)} prediccions mesurables, confirmades.")
        res = data().get("manual", {}).get("final_result", {}).get("overall")
        if F.get("official"):
            h = (f"Final: {res + ', ' if res else ''}#{F['sel_rank']} de {F['n_teams']} en conversió "
                 f"({R.f(F['sel_conv'], 2)} compres/100). " + h.split(": ", 1)[1][0].upper() + h.split(": ", 1)[1][1:])
        items = [
            ("D1", "La fiabilitat era la palanca, i s'ha arreglat",
             f"Pitjor finestra de 10 min: {R.pct(F['w_min'], 1)} (pràctica: {R.pct(F['prac_served'], 1)} en total, "
             f"{R.pct(F['prac_below95'], 0)} de finestres per sota del 95 %). "
             f"{F['late_or_missing']} {'petició' if F['late_or_missing'] == 1 else 'peticions'} sense resposta a temps de "
             f"{R.f(F['n_requests'], 0)}."),
            ("D2 · D6", "Un sol model congelat; el model, per sota del previst",
             f"{F.get('live')} va servir el {R.pct(F.get('live_share'), 1)} de les respostes, sense cap petició amb dues versions. "
             + (f"Oficial: {R.f(F['sel_conv'], 2)} compres/100 (q {R.f(F['live_med'], 0)}), per sota de les frontisses de "
                f"pràctica; la referència va caure igual (q {R.f(F['ref_q_final'], 0)}): {R.f(F['sel_conv'] - F['ref_conv'], 2, sign=True)} "
                f"respecte a ella." if F.get("official") else
                f"{R.f(rf['rate'], 2)} compres reals/100 (IC95 {R.f(rf['lo'], 2)}–{R.f(rf['hi'], 2)}) vs {R.f(rp['rate'], 2)} a la "
                f"pràctica." if rf and rp else "")),
            ("D3 · D5", "El patró de la pràctica es repeteix",
             f"Slot 1 = {R.pct(F.get('slot1_share'), 0)} de les compres (predicció ≥ 35 %); ja comprat {R.pct(F.get('bb_all'), 1)} "
             f"dels slots (≤ 1,5 %); en fred ×{R.f(F.get('live_cold_ratio') or F.get('cold_ratio_real'), 1)} la baseline freda (≥ ×2)."),
        ]
        return h, items

    @render.ui
    def verdict():
        if is_final():
            h, its = final_text()
            items = [ui.tags.li(ui.span(d, class_="tk-did"), ui.strong(t + ". "), b) for d, t, b in its]
            return ui.div(ui.p(h, class_="tk-h1"), ui.tags.ul(*items, class_="tk-verdict3"), class_="tk-top")
        items = [ui.tags.li(ui.span(d, class_="tk-did"), ui.strong(h + ". "), b) for d, h, b, _ in T()["verdict"]]
        return ui.div(ui.p(T()["h1"], class_="tk-h1"), ui.tags.ul(*items, class_="tk-verdict3"), class_="tk-top")

    def _titles():
        if is_final():
            return ("Final: respostes a temps", "Final: compres reals", "Prediccions registrades", "Resultat de la final")
        return ("Posició a l'última hora", "Respostes a temps", "El model, quan respon", "En joc a la final")

    @render.text
    def t1():
        return _titles()[0]

    @render.text
    def t2():
        return _titles()[1]

    @render.text
    def t3():
        return _titles()[2]

    @render.text
    def t4():
        return _titles()[3]

    @render.text
    def k1():
        if is_final():
            return R.pct(FIN()["N"]["served_total"], 3)
        return f"#{N()['sel_rank']}"

    @render.text
    def k1s():
        if is_final():
            F = FIN()["N"]
            return f"respostes a temps · pitjor finestra {R.pct(F['w_min'], 1)} · pràctica {R.pct(F['prac_served'], 1)}"
        n = N()
        return f"{n['sel_label']} · amb el mateix model vam ser #{n['worst_rank']} a {n['worst_label']}"

    @render.text
    def k2():
        if is_final():
            r = FIN()["N"].get("real")
            return f"{R.f(r['rate'], 2)} compres/100" if r else "–"
        return R.pct(N()["sel_s"], 1)

    @render.text
    def k2s():
        if is_final():
            F = FIN()["N"]
            r, p_ = F.get("real"), F.get("real_prac_live")
            return (f"reals, IC95 {R.f(r['lo'], 2)}–{R.f(r['hi'], 2)} · {F.get('live')} a la pràctica {R.f(p_['rate'], 2)}" if r and p_ else "")
        n = N()
        return f"objectiu 98 % · mediana horària {R.pct(n['box_team_37']['med'], 0)} · mínim {R.pct(n['worst_s'], 0)}"

    @render.text
    def k3():
        if is_final():
            o = OUT()
            ok = sum(v[0] == "✓" for v in o.values())
            m = sum(v[0] in "✓✗" for v in o.values())
            return f"{ok} de {m} ✓"
        return f"{R.f(N()['live_conv'], 2)} compres/100"

    @render.text
    def k3s():
        if is_final():
            o = OUT()
            pend = [k for k, v in o.items() if v[0] not in "✓✗"]
            return "prediccions mesurables confirmades" + (f" · sense veredicte: {', '.join(pend)}" if pend else "")
        n = N()
        return f"{n['live']} · referència de l'organització {R.f(next(r['reference'] for r in data()['windows15'][-4:]), 2)}"

    @render.text
    def k4():
        if is_final():
            F, res = FIN()["N"], data().get("manual", {}).get("final_result", {})
            if res.get("overall"):
                return res["overall"].capitalize()
            return f"#{F['sel_rank']}" if F.get("has_api") and F.get("sel_rank") else "pendent"
        return f"fins a {R.f(N()['d1_hi'], 1)} punts"

    @render.text
    def k4s():
        if is_final():
            F = FIN()["N"]
            if F.get("has_api"):
                return (f"#{F['sel_rank']} de {F['n_teams']} en conversió: {R.f(F.get('sel_conv'), 2)} compres/100 esperades "
                        f"(referència {R.f(F.get('ref_conv'), 2)}, baseline {R.f(F.get('base_conv'), 2)})")
            return "l'API amaga la classificació fins que acaba la final"
        n = N()
        return f"per fiabilitat (D1), sobre 100 · canviar de model ≤ {R.f(max(n['d2'].values()) if n['d2'] else None, 1)}"

    @render.ui
    def h1():
        if is_final():
            F = FIN()["N"]
            pb, fb = F["prac_box"], F["final_box"]
            return head(f"A la pràctica, el {R.pct(F['prac_below95'], 0)} de les finestres de 10 min van quedar per sota del 95 % "
                        f"(frontissa inferior {R.pct(pb['h1'], 0)}); a la final, {'cap' if not F['final_below98'] else F['final_below98']} "
                        f"de {F['n_windows']} per sota del 98 % (mínim {R.pct(fb['min'], 1)})",
                        "Cada marca és una finestra de 10 minuts; la caixa de Tukey en resumeix la distribució (frontisses, mediana i "
                        "bigotis fins a 1,5·H). Gris: pràctica; blau: final. Discontinu: objectiu del 98 % (D1). Font: "
                        "team_37.feedback, on una resposta tardana compta com a no resposta, igual que a l'on-time oficial.")
        n = N()
        return head(f"Ens movem en horitzontal: el model és dels millors i el que ens fa caure és respondre tard "
                    f"(#{n['best_rank']} amb {R.pct(n['best_s'], 0)} a temps, #{n['worst_rank']} amb {R.pct(n['worst_s'], 0)})",
                    "Cada punt gris és un equip a l'última hora de la finestra. A la dreta = respon a temps; amunt = el seu model "
                    "ven més quan respon (compres/100 descomptant les respostes per defecte). Blau ple: team_37 ara; blau buit: "
                    "el mateix model a l'hora pitjor. Teoria: posició en escala comuna per a la relació entre dues variables "
                    "(Munzner); un to sobre gris (pop-out).")

    @render.ui
    def c1():
        if is_final():
            return vega("v1", lambda: C.final_reliability(FIN()["N"]))
        t0, t1 = window()
        return vega("v1", lambda: C.field(data(), t0, t1))

    @render.ui
    def h2():
        if is_final() and FIN()["N"].get("field_final"):
            F = FIN()["N"]
            top = F["field_final"][:5]
            return head(f"A la final els equips forts responen gairebé tots ~100 % a temps: ara ens separa el model. team_37, "
                        f"#{F['sel_rank']} de {F['n_teams']} amb {R.f(F['sel_conv'], 2)} compres/100, a "
                        f"{R.f(F['top_conv'] - F['sel_conv'], 2)} del primer i a {R.f(F['sel_conv'] - F['ref_conv'], 2, sign=True)} "
                        f"de la referència",
                        "Mètrica oficial de l'API per a tota la final (10:00–12:00): cada punt és un equip; a la dreta = respon a "
                        "temps; amunt = compres esperades per 100 peticions. Blau: team_37; negre discontinu: referència i baseline "
                        "de l'organització. És la mateixa vista que V1 de la pràctica: allà ens movíem en horitzontal (fiabilitat); "
                        "aquí la fiabilitat ja no diferencia. Primers cinc en conversió: "
                        + ", ".join(f"{r['team']} {R.f(r['conv'], 2)}" for r in top) + ".")
        if is_final():
            F = FIN()["N"]
            return head(f"La latència no ha canviat (p95 ≤ {R.f(F['p95_final'], 1)} s a la final, {R.f(F['p95_lo'], 1)}–"
                        f"{R.f(F['p95_hi'], 1)} s per hora a la pràctica): la millora ve d'un sol writer estable, no d'anar més ràpid",
                        "Caixa de Tukey de la latència p95 de cada hora (respostes servides per team_37), mínim a màxim; cada punt és "
                        "una hora. Vermelló: el límit de 3 s de la competició. Si el problema hagués estat la velocitat del model, la "
                        "caixa de la final seria més baixa; és igual, per tant el que va fallar a la pràctica eren les caigudes.")
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
        if is_final():
            if FIN()["N"].get("field_final"):
                return vega("v2", lambda: C.final_field(FIN()["N"]))
            return vega("v2", lambda: C.final_latency(data()))
        t0, t1 = window()
        return vega("v2", lambda: C.reliability(data(), t0, t1))

    @render.ui
    def h3():
        if is_final():
            F = FIN()["N"]
            rf, rp = F.get("real"), F.get("real_prac_live")
            if not (rf and rp):
                return head("Compres reals de la versió servida", "Sense dades.")
            same = rp["lo"] <= rf["rate"] <= rp["hi"] or rf["lo"] <= rp["rate"] <= rf["hi"]
            return head(f"{F['live']} ven a la final el que prometia: {R.f(rf['rate'], 2)} compres reals/100 contra "
                        f"{R.f(rp['rate'], 2)} a la pràctica ({'intervals que se solapen' if same else 'diferència real'}), "
                        f"{R.f(rf['rate'] / ((F.get('real_prac') or {}).get('(fallback:missing)') or {'rate': rf['rate']})['rate'], 1)} vegades la llista baseline",
                        "Compres reals per 100 peticions amb interval de confiança del 95 % exacte de Poisson. Blau: la final; gris: la "
                        "pràctica (la mateixa versió, la versió anterior i la llista baseline que reben les peticions no respostes). La "
                        "mètrica oficial (compres esperades del simulador) té ~8 vegades menys soroll i s'afegirà quan l'API la publiqui.")
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
        if is_final():
            return vega("v3", lambda: C.final_realised(FIN()["N"]))
        t0, t1 = window()
        return vega("v3", lambda: C.versions(data(), t0, t1))

    @render.ui
    def h4():
        if is_final():
            F = FIN()["N"]
            return head(f"El patró del slot 1 es repeteix: fa el {R.pct(F.get('slot1_share'), 0)} de les compres i els productes "
                        f"vistos a la sessió continuen a dalt; ja comprat = {R.pct(F.get('bb_all'), 1)} dels slots",
                        "Compres per cada 1.000 vegades que un producte surt en primera posició, segons la seva relació amb el comprador. "
                        "Marca negra: la pràctica (exploratori); punt blau amb IC95: la final (confirmatori). Si el punt cau sobre la "
                        "marca, la regla apresa a la pràctica es manté amb dades noves.")
        n = N()
        return head(f"El slot 1 fa el {R.pct(n['slot1_share'], 0)} de les compres: a dalt, productes vistos a la sessió i "
                    f"del carret; un producte ja comprat gairebé no es ven ({R.f(n['bb1'], 1)} per 1.000)",
                    "Compres per cada 1.000 vegades que un producte es mostra en primera posició, segons la seva relació amb el "
                    "comprador. Barres des de zero, ordenades per valor. Vermelló: posició malgastada (ja comprat). Dades de "
                    "pràctica (team_37.feedback).")

    @render.ui
    def c4():
        if is_final():
            return vega("v4", lambda: C.final_slot_one(data()))
        return vega("v4", lambda: C.slot_one(data()))

    @render.ui
    def watch_head():
        return ui.h6("Disparadors durant la final: han saltat?" if is_final() else "Vigilar durant la final")

    @render.ui
    def watch():
        if is_final():
            F = FIN()["N"]
            checks = [
                ("On-time d'una finestra < 95 %", F["w_min"] < 95, f"pitjor {R.pct(F['w_min'], 1)}"),
                ("Una versió < 95 % de les respostes", (F.get("live_share") or 0) < 95, f"{F.get('live')} {R.pct(F.get('live_share'), 0)}"),
                ("Latència p95 > 2,5 s", (F.get("p95_final") or 0) > 2.5, f"p95 màxim {R.f(F.get('p95_final'), 1)} s"),
                ("Peticions amb dues versions", (F.get("multi_version") or 0) > 0, f"{F.get('multi_version', 0)}"),
            ]
            lis = [ui.tags.li(ui.strong(a), f" → {'SÍ' if fired else 'no'} ({v})") for a, fired, v in checks]
            return ui.tags.ul(*lis, class_="tk-watch")
        base = BASE()
        t = R.texts(base, pred(), False)
        lis = [ui.tags.li(ui.strong(a), f" → {b}") for a, b, _ in t["watch"]]
        alarm = t.get("alarm")
        if alarm and FIN() is not None:   # the trigger was acted on before the final: say so instead of a stale alarm
            F = FIN()["N"]
            alarm = (f"Disparador D6 resolt abans de la final: a les 09:43 es va congelar {F.get('live')}, que ha servit el "
                     f"{R.pct(F.get('live_share'), 0)} de les respostes de la final.")
            return ui.TagList(ui.p(alarm, class_="tk-small"), ui.tags.ul(*lis, class_="tk-watch"))
        return ui.TagList(ui.p(alarm, class_="tk-alarm") if alarm else None, ui.tags.ul(*lis, class_="tk-watch"))

    @render.ui
    def meta():
        p_ = pred()
        built = datetime.fromtimestamp(DATA.stat().st_mtime, tz=CET).strftime("%d/%m %H:%M")
        return ui.p(f"Prediccions registrades {p_['registered_at_cet']} (sha {p_['sha256'][:8]}). Dades: API pública de RawTree, "
                    f"base de dades team_37, Notion i GitHub de l'equip. Actualitzat {built} CET.", class_="tk-small")

    @render.ui
    def ledger():
        base = BASE()
        out = OUT()
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
