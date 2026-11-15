# Tauler de decisions de team_37 · Side Challenge Tukey (Datathon FME 2026, repte RawTree)

Un tauler que ajuda a decidir què fem al recomanador en temps real: **què ens fa guanyar o perdre punts i què fem a la
final**. Tot en una sola moneda (punts finals sobre 100), amb l'evidència etiquetada com a EXPLORATÒRIA, PRE-REGISTRADA o
CONFIRMATÒRIA, a l'estil de Tukey: *visualitzar per descobrir, interpretar i decidir*.

**Entregable: dashboard Shiny (Shiny for Python + Altair), una sola vista.**

```powershell
cd tukey_dashboard
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m shiny run app\app.py --port 8000      # obrir http://127.0.0.1:8000
```

macOS / Linux:

```bash
cd tukey_dashboard
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m shiny run app/app.py --port 8000              # obrir http://127.0.0.1:8000
./run_all.sh                                                      # refrescar totes les dades
```

Les dades incloses permeten obrir el tauler sense credencials. Per refrescar la base de dades, poseu
`RAWTREE_API_KEY` al fitxer `.env` de l'arrel del repositori (no es publica a Git).

Una vista: veredicte (3 decisions) + 4 indicadors + 4 gràfics simples (fiabilitat vs qualitat del model de tots els equips,
on-time per finestra, caixes de Tukey per versió, compres al slot 1 per relació) + taula de decisions amb la predicció
registrada abans de la final i el resultat. Barra lateral: període (pràctica/final), finestra temporal (filtra totes les
vistes) i què vigilar durant la final. Cada títol és la conclusió; el botó ⓘ explica com es llegeix i quina regla de
l'assignatura aplica.

- Refrescar dades: `run_all.ps1` (Windows) o `run_all.sh` (macOS/Linux): API + base de dades + taules. La app es
  recarrega sola quan canvia `data/dashboard_data.json`.
- Exportació estàtica antiga (més detallada, sense servidor): `dist/index.html`.

## Disseny (assignatura de VI)

Una sola pàgina per període, pensada per llegir-se en 30 segons: **titular** (la conclusió) → **4 KPI** com a *bullet
charts* (valor, objectiu i referència en una barra; millors que els indicadors de rellotge perquè comparem longituds) →
**4 gràfics** amb el títol com a conclusió i una línia del que codifiquen → **registre de decisions**. Les explicacions
llargues són a la ⓘ de cada targeta (*overview first, details on demand*). Regles seguides: el mínim de text i etiquetes
directes dins el gràfic en lloc de llegendes (*Good practices* part 2; Stokes & Hearst 2022: el text útil és l'anotació,
no els paràgrafs), grisos i un sol accent (blau = team_37, vermelló = pèrdua, negre discontinu = referència), cap
parella vermell/verd i l'estat sempre amb glif + paraula (daltonisme), barres des de zero, caixes de Tukey amb totes les
observacions a sobre, i 3-4 *chunks* per bloc (memòria de treball).

## Període Final (confirmatori)

El selector **Final** canvia tota la vista a la comprovació de les prediccions congelades abans de la final
(`data/manual/predictions.json`, 15/11 08:12, sha `b4c5f609`):

| Vista final | Què mostra | Font |
|---|---|---|
| Veredicte + 4 indicadors | on-time de la final, compres reals amb IC95, prediccions confirmades, posició oficial | BD + API |
| F1 Fiabilitat | caixa de Tukey + tira de l'on-time per finestra de 10 min: pràctica vs final | `team_37.feedback` |
| F2 Latència | p95 per hora, pràctica vs final: la millora no ve de la velocitat sinó d'un sol writer estable | `team_37.feedback` |
| F3 Model | compres reals/100 de la versió servida a la final vs la mateixa versió, l'anterior i la llista baseline a la pràctica (IC95 exacte de Poisson) | `team_37.feedback` + `submissions` |
| F4 Què ven | compres per 1.000 al slot 1 per relació: patró de la pràctica (marca) replicat a la final (punt + IC95) | BD |
| Disparadors | cadascun dels quatre disparadors pre-registrats: ha saltat o no | BD |
| Registre | columna «Resultat a la final» amb ✓/✗ per predicció | BD + API |

**Mentre dura la final l'API pública amaga la classificació** (mode `final_running`: només llums verd/vermell). Per això
el període final es llegeix de la base de dades de RawTree, i D2 (q oficial) i D5 (conversió freda oficial) es contrasten
primer amb compres reals (marcat al text) i amb la mètrica oficial quan l'API la publiqui: només cal tornar a executar
`run_all`. `fetch_api.py` no sobreescriu mai un fitxer bo amb una resposta buida i torna a baixar les finestres que van
quedar buides.

## Què respon (una vista per decisió)

| Vista | Decisió | Missatge (amb dades fins dg 08:00) |
|---|---|---|
| V0 Veredicte | Què fem ara i què vigilem a la final | La fiabilitat ens costa més que el model: mateix model, #3 amb 100 % a temps i #21 amb 40 %. |
| V1 Camp | D1 vs D2: ens cal millor model o més fiabilitat? | Ens movem en horitzontal: tornar al 98 % valia +23 punts finals; el model ja és del top-5. |
| V6 Registre | Prioritat de decisions i prediccions per a la final | D1 fins a 23 punts; triar malament el model fins a 16; l'exploració ≤ 0,3. |
| V2 Fiabilitat | D1: objectiu d'on-time, writer de reserva | Si la final fos com la pràctica perdríem ≥ 3,7 punts; la caiguda de dg 01h en costava 24. |
| V3 Models | D2/D5: quina versió servim, ruta freda? | fz-v9a i fz-v10-nocorr empaten (30 finestres aparellades); la resta, clarament per sota. |
| V5 Potència | D6: repartir trànsit a la final? | Un 50/50 en 2 h només veu Δ ≥ 0,19 compres/100: congelar. |
| V4 Què ven | D3/D4: què va al slot 1, on explorar | Slot 1 = 42 % de les compres; vistos a la sessió i carret a dalt, mai recompres. |

## Mètode i fonts

- **Fórmula de puntuació verificada**: puntuació = 100·(equip − baseline)/(oracle − baseline). L'oracle es dedueix de la
  sèrie `progress` de l'API pública i és idèntic per a tots els equips dins cada hora; el pipeline comprova que reprodueix
  la puntuació publicada.
- **Identitat de fiabilitat**: les peticions no respostes reben la llista baseline, per tant
  equip = on-time·model + (1 − on-time)·baseline. Permet separar la qualitat del model de la fiabilitat per als 42 equips (V1)
  i mesurar els punts perduts per finestra (V2). Validada: 36 de 44 finestres informatives dins ±0,05.
- **Soroll de la mètrica oficial**: la mètrica del simulador (sense sort) té ≈ 8× menys variància per petició que les compres
  reals → corbes de potència de V5.
- **Tukey**: resums de cinc números amb frontisses i tanques (V2, V3), median polish amb residus (V4), cadena exploratori →
  pre-registrat (hash SHA-256 a `data/manual/predictions.json`, escrit una sola vegada abans de la final) → confirmatori.
- **Dades**: API pública `datathon.rawtree.dev/api/state?by=model` (finestres d'1 h i 15 min); base de dades RawTree
  (`team_37.feedback`, `team_37.submissions`, `shop.requests`, `shop.events`, `shop.history_events`,
  `shop.catalog_updates`; només SELECT); Notion de l'equip i repositori `rawtree-team37-engine` per al registre de decisions.

## Teoria de VI aplicada (assignatura VI, cites a `docs/vi_theory.md`)

| Principi | On |
|---|---|
| Efectivitat: posició en escala comuna per al més important (Munzner, P2 p35) | V1, V3, V5 |
| Un to sobre gris; un color = un significat (P1 p61, PR p4): blau = team_37, vermelló = punts perduts, negre = referències externes, gris = context | tot |
| Mantra de Shneiderman: veredicte → vistes → tooltip (W2 p37) | ordre de la pàgina |
| Vistes enllaçades: arrossegar a V2 ressalta les mateixes hores a V1 i V3 (MV p64) | V2 → V1, V3 |
| Vista general + detall per a la zona densa (MV p35) | V1 |
| Petits múltiples amb la mateixa escala (MV p45) | V4 |
| Distribucions, no barres de mitjanes (W3 p29, VOTD Wilmer & Kerns, raincloud) | V2, V3 |
| Incertesa comunicada (AV p41-43) | V3 (IC aparellat), V4 (IC de Poisson), V5 |
| Títols = conclusions, text de context (P2 p70, VOTD Stokes & Hearst) | tots els títols |
| Barres des de zero; escales log etiquetades (W3 p6, p16) | V2, V4, V5 |
| Daltonisme: blau/vermelló validats, segona codificació (forma, buit/ple, etiqueta) (CB p3-14) | tot |
| Mínimes interaccions amb valors per defecte significatius (PR p4) | un brush + un selector de període |

## Procés de disseny (iteracions)

1. **Recerca en paral·lel** (subagents): teoria de l'assignatura (`docs/vi_theory.md`), inventari de dades amb SQL verificat
   (`docs/data_inventory.md`), Notion + GitHub + taulers rivals (`docs/notion_github.md`).
2. **Tres conceptes rivals** (subagents): A «cabina de decisions», B «descobrir → interpretar → decidir» (Tukey),
   C «llibre de punts i què-passaria-si» (`docs/concepts/`).
3. **Jurat simulat** (subagent): puntuació dels tres (B 39/50, A 35, C 33) i síntesi en una especificació única
   (`docs/spec_v2.md`): el camp de C, el rigor de B i el registre de decisions d'A. El «què passaria si» amb lliscador es va
   descartar: les corbes d'isopuntuació de V1 ja ho responen sense falsa precisió.
4. **Construcció** (Altair → Vega-Lite 6) i quatre rondes visuals (`shots/it1…it6`).
5. **Revisió crítica** (dos subagents): jurat + professor (`docs/review_r1_jury.md`) i auditoria numèrica
   (`docs/review_r1_audit.md`: comparació aparellada fz-v9a/nocorr, recompres abans/després del vet, «top-6» amb una sola
   definició, prediccions congelades amb hash…). Segona ronda (`docs/review_r2_jury.md`): utilitat 7→8, adequació 6→7,
   coherència 5→7, teoria VI 7→8, esperit Tukey 8→9; els seus cinc canvis prioritaris ja estan aplicats (un sol preu per a
   la caiguda de dg 01h, alarma activa de D6, redacció de V5, signe aparellat a V3, etiquetes de V1).

## Estructura

```
pipeline/fetch_api.py        API pública → data/raw/api
pipeline/build_api_tables.py → data/tidy/*.csv
pipeline/extract_db.py       RawTree (només SELECT) → data/raw/db/{practice,final}
pipeline/build_dataset.py    taules derivades → data/dashboard_data.json
pipeline/render.py, views.py números + textos + especificacions Vega-Lite → dist/
data/manual/                 decisions, esdeveniments i prediccions congelades (amb font)
```
