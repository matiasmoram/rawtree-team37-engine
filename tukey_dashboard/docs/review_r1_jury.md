# Review R1: simulated Tukey jury and VI professor (build it3, 15/11 03:41)

Sources: shots it3_s1–s4 (1440×900), the visible text of dist/index.html, spec_v2, vi_theory (cited as deck p.N).

## 1. Scores

| Criterion | Score |
|---|---|
| 1 Usefulness for deciding | 7 / 10 |
| 2 Adequacy of charts for data and comparisons | 6 / 10 |
| 3 Coherence of indicators, charts, conclusions and data | 5 / 10 |
| VI theory visibly applied | 7 / 10 |
| Tukey spirit | 8 / 10 |

**Usefulness (7).** This page beats a live monitor because it is built around decisions. Every view names its decision. One currency (punts finals) runs through it, and the ledger has outcome slots. Two gaps cost points:
- **Nothing covers the final itself.** There is no current status (writer, standby, on-time over the last hour, which version is serving). There are no pre-registered triggers ("if X, do Y"), although the brief asks for decisions "before, during and after".
- **The stakes look inflated.** D2 "0,4–15,9" and D6 "0,2–8,0" take their upper end from ev-v2-nocovis, a retired version nobody proposes to serve. The D4 decision is also ambiguous: is it 30 % of requests on slot 10, or "només slots 9–10"?

The 10-second test half-passes. A non-expert gets "reliability is the problem". They do not get what we will do, because of jargon: writer, split, q, slot, mètrica oficial, frontisses.

**Adequacy (6).** The chart types are right: a field scatter with iso-curves, aligned time panels, box+strip, median-polish small multiples, power curves. The execution has five problems:
- V1 crams about 25 teams into on-time 95–100 % and the labels collide ("team_37 dg 02:00" sits on top of "team_05 #2").
- V1's team_37 path is spaghetti.
- V4 clamps values below 0,3 to the floor, so the fit and the residual vanish in "Ja comprat" and "home".
- V6 draws ranges as blue bars on an unlabelled track.
- In V5 the nocorr line ("1.801 k pet.") never meets the curve on screen.

**Coherence (5).** This is the weakest criterion, and the jury reads for it.
- H1 says "de podi" for rank #4. It also uses two different "#4"s (model rank and API rank) in one sentence.
- The worst incident gets three figures: "hora pitjor (40 %) … 22,9" in V0, "dg 01:00–01:45, on-time 20 % … 28,7" in V2, and "40 % dg 01:00" in the V2 box.
- The target is 98 %, but the gains are computed to 99 %.
- V3 says "+15,9" for a loss.
- "Δ" means a q gap against the reference in V3, but a compres/100 gap against fz-v9a in V5.
- V2 counts "48 de 56" windows against "n = 58".
- V1's title says "no en vertical" over a path that climbs from q 0 to 62.
- "PRE-REGISTRAT 15/11 03:41" is the same timestamp as "generat 15/11 03:41".
- V4 says "Ja comprat 2,1 % dels slots", yet V6 says the re-buy ban was "ja aplicat".

**VI theory (7).** The course rules are visibly applied:
- Takeaway titles (P2 p70) and one hue over grey (P1 p61-64).
- Direct labels and status shown by border, not hue (CB p11-14).
- Aligned small multiples (MV p45-47), labelled log axes (W3 p16-17) and bars from zero (W3 p6).
- One brush with a sensible default (PR p4).

They are undercut by:
- Overlapping text in V1 and V2, which is clutter (W1 p119).
- Blue for stake bars in V6, which breaks one colour = one meaning (PR p4).
- No overview+detail where the data is dense (MV p35-37).
- Annotations that restate what is visible ("on-time < 50 %"; Stokes & Hearst).
- No line anywhere that says why each chart was chosen (PR p2-4 asks for one).

**Tukey spirit (8).** This is the jury's language: hinges and 1,5·H fences, box+strip per window, median polish shown as fit + residual, re-expression on a log scale, and the EXPLORATORI → PRE-REGISTRAT → CONFIRMATORI chain. It loses points in four places:
- The pre-registration is not frozen (it carries the build timestamp).
- The top-6 band in V2 is a min–max range, which is not resistant: at ds 13:00 it spans about 0–100.
- The V2 outlier is not labelled as lying beyond the fence.
- V4 is badged CONFIRMATORI without naming the hypothesis it confirms.

## 2. Fixes (highest impact first)

1. **V0 · the H1 is false and the first screen is opaque.**
   - *Problem:* "El model ja és de podi … (#4 de 32 en qualitat) vam ser #4 amb on-time 100 %": #4 is not a podium, and the two "#4"s measure different things. The badges are only explained in the footer, and the data timestamp is only in the footer.
   - *Why it matters:* coherence; one entry point (P1 p95); audience (W2 p5).
   - *Fix:*
     - New H1: "La fiabilitat ens costa més que el model: amb el mateix model érem #4 amb el 100 % de respostes a temps i #21 amb el 40 %".
     - Under the H1, one line: "EXPLORATORI = patró trobat · PRE-REGISTRAT = predicció fixada abans de la final · CONFIRMATORI = comprovat amb dades noves".
     - Next to the toggle: "Dades fins a dg 03:30 CET".
     - Gloss each term at first use: writer → "procés que envia les respostes"; split → "repartir el trànsit 50/50"; slot → "posició".
     - Cut the stake numbers from the V0 cards: one sentence per card, because V6 already holds those numbers.
2. **V0 / V1 / V2 · one incident, three figures.**
   - *Problem:* "des de l'hora pitjor (40 %), 22,9" (V0) vs "la pitjor caiguda (dg 01:00–01:45, on-time 20 %) en costava 28,7" (V2). The objective is "≥ 98 %", yet the gains are computed "a 99 %". "4,8 punts finals per finestra" reads as a per-window sum.
   - *Why it matters:* coherence; spec §2.1 says points are rates and the API hour is the only official figure.
   - *Fix:*
     - Anchor V0, V1, V2 and V6 on the official hour dg 01:00–02:00 (40 %) and on 98 %. Recompute 5,2 and 22,9 to 98 %.
     - V2 title: "Si la final fos com la pràctica, la fiabilitat ens costaria 4,8 punts finals (mitjana ponderada, no suma); l'hora dg 01:00–02:00 (40 %) en costava X".
     - Keep "01:00–01:45" only as an annotation.
3. **V6 / V5 · the pre-registration is not frozen.**
   - *Problem:* "PRE-REGISTRAT 15/11 03:41" is identical to the footer's "generat 15/11 03:41", so every rebuild re-dates it. V5's "PRE-REGISTRAT" has no time and no rule.
   - *Why it matters:* this is Tukey's EDA → confirmation chain (W1 p66), and a statistician will spot it at once.
   - *Fix:*
     - Write the predictions to a committed `manual.decisions` with `registered_at`, and print "registrat 03:41 · sha 1a2b3c" (SHA-256 of the file).
     - build.py asserts that the hash is unchanged after the 12:00 re-run.
     - Print the V5 rule in its empty bottom area: "Canviar de model només si un 50/50 abans de les 09:30 dona Δ̂ > MDE(n); si no, fz-v9a congelat; a la final una versió ≥ 95 %".
4. **V3 / V6 · loss signs and strawman stakes.**
   - *Problem:* "Punts finals si se servís cada alternativa …: ev-v2-nocovis +15,9, cf-rot +14,7" reads as gains. D2 "0,4–15,9" and D6 "0,2–8,0" take their upper end from a retired version.
   - *Why it matters:* coherence; honesty (W2 p3).
   - *Fix:*
     - Reword: "Punts finals que perdríem: cf-rot −14,7 · lgbm-recent −11,8 · fz-v10-nocorr −0,4".
     - In V6 D2 and D6, draw one labelled tick per real candidate (nocorr, lgbm, cf-rot) instead of a min–max bar.
5. **V0 / V6 · nothing covers the final.**
   - *Problem:* the page has no "estat ara" and no triggers. At 09:45 the team cannot see whether the standby writer is live, or what to watch from 10:00 to 12:00.
   - *Why it matters:* usefulness criterion; brief §5 ("durant la final").
   - *Fix:* add a pre-registered "Vigilar durant la final" block in the units the page already uses:
     - On-time of a 15-min window < 95 % → switch to the standby (0,39 punts/pp).
     - One version < 95 % of requests → check the deploy.
     - p95 latency > 2,5 s → the network.
     - Identity residual outside ±0,05 → API/data.
     - Add one status line: writer, standby, last-hour on-time, serving version.
6. **V1 · the cluster at 95–100 % is unreadable.**
   - *Problem:* about 25 grey dots sit on roughly 3 % of the x range. "team_37 dg 02:00" overprints "team_05 #2". The top 6 are not labelled, as spec §2.3 requires. The "×" measured tick (60) and the ±0,05 whisker are hidden under the dot.
   - *Why it matters:* overview+detail (MV p35-37); clutter (W1 p119).
   - *Fix:*
     - Add a detail panel for on-time 90–100 % (same y) to the right of the overview, linked by a grey bracket.
     - Label #1–#6 and team_37 with offsets.
     - Print "m̂ 61 · mesurat 60" as text next to our dot.
7. **V1 · the title is contradicted by the path.**
   - *Problem:* "Pugem o baixem en horitzontal, no en vertical", yet the blue path zig-zags from q≈0 (ds 13:00) to 62. That is model progress, and it reads as spaghetti (W1 p45-46).
   - *Fix:*
     - Draw the path only for the hours when fz-v9a-xcat1.0 was serving (dg 00:00–03:00), with arrowheads and a label at every node ("00h 99 % #3 → 01h 40 % #21 → 02h 100 % #4").
     - Fade the earlier hours to #d4d4d4, or drop them, since V3 already shows model progress.
8. **V4 · clamped values hide the data.**
   - *Problem:* "Escala log; valors < 0,3 a la base". In "Ja comprat" and "Sense vistes" the observed dot and the fit sit on the same floor, so "×1,9" and "×0,5" have no visible distance. A zero looks like 0,3.
   - *Why it matters:* lie factor (P2 p62-65); missing ≠ 0 (AV p69).
   - *Fix:* plot y = rate + 0,5 on the log scale, which is the polish's own re-expression. Tick labels show the raw rate (0 · 0,5 · 1 · 2 · 5 · 10 · 20), so 0 gets a real position.
9. **V6 · stake encoding and title.**
   - *Problem:* blue bars ("team_37 observat" in spec §2.4) on a track with no ticks. The note says "des de zero, escala comuna" but no scale is printed. "D3 ja aplicat" has no number, yet it sits 3rd in a list "ordenat per punts en joc". The title "Llibre de decisions: què hi ha en joc…" is descriptive.
   - *Why it matters:* PR p4 (colour consistency); line ranges (AV p42); takeaway as title (P2 p70).
   - *Fix:*
     - Draw a #3a3a3a line range with end dots and a shared 0 · 10 · 20 axis in the header.
     - D3: a hollow dot "≈ 12 ja guanyats (abans/després)".
     - Title: "La fiabilitat (D1) val fins a 22,9 punts; el model fins a 14,7 si tornéssim a cf-rot; l'exploració ≤ 0,2".
10. **V5 · labels and message.**
    - *Problem:* "fz-v10-nocorr: Δ 0,02 → 1.801 k pet." means 1,8 M, and it lies beyond the 1M axis, so it has no intersection dot. "cf-rot: Δ 0,81 → 1,3 k pet." hides the point that cf-rot is visibly worse within minutes. "caiguda del writer: Δ 1,25" is unexplained.
    - *Fix:*
      - Labels: "1,8 M peticions (≈ 7 dies)" and "1.300 peticions (7 min)". Extend x to 3M.
      - Title: "cf-rot ja és clarament pitjor; fz-v10-nocorr empata (caldria 1,8 M peticions): cap split val la pena → congelar fz-v9a".
      - Vermillion rule: "efecte d'una caiguda (dg 01h): més gran que qualsevol diferència entre models".
11. **V3 · the title overclaims, Δ means two things, and the cold panel is incomplete.**
    - *Problem:* "fz-v9a-xcat1.0 és la millor versió", but fz-v10-nocorr also shows "Δ +7" with a median of about 57 vs 58. Cold: the title cites "referència ×2,0", but the reference row shows only a dotted segment, and there is no black ×1 rule (spec).
    - *Fix:*
      - Title: "fz-v9a i fz-v10-nocorr empaten (q 58 vs 57); la resta ≥ 20 q per sota → servir fz-v9a (k 17)".
      - Column header "Δq vs referència (mateixa finestra)". In V5, write "Δ compres/100 vs fz-v9a".
      - Add black reference ticks and a "×1 = baseline freda" rule to the cold panel.
      - Put the 9 retired versions below a "versions retirades" separator, at lower opacity.
12. **V2 · text collisions and L1 annotations.**
    - *Problem:* "objectiu D1 98 %", "llum d'estat 90 %" and "01:00–01:45 on-time < 50 %" overprint at the top right. "13:00–13:30 on-time < 50 %" restates the line. "18:49 writer local aturat" sits where on-time stays at about 90 %, so a lay reader sees an outage that never happened.
    - *Why it matters:* Stokes & Hearst (prefer L4 causes, avoid redundant text); clutter (W1 p119).
    - *Fix:*
      - Move the rule labels to the right margin outside the plot.
      - Annotate causes, at most 4: "14:50 canvi de motor", "15:50 vet a recompres", "00:19 entra fz-v9a", "01:00 writer caigut".
      - Rephrase the 18:49 note to say what changed.
13. **V2 · resistant summaries.**
    - *Problem:* the top-6 band is a min–max range, so it spans about 0–100 at ds 13:00 because of a single team. The box label "40 % dg 01:00" does not say "fora de la tanca". The box has no numbers. "48 de 56 finestres" sits against "n = 58".
    - *Why it matters:* Tukey and resistance; MV p104 (fences).
    - *Fix:*
      - Show the top-6 median as a grey step line plus its hinge band.
      - Label "40 %: fora de la tanca (47,5)". Print "40 | 73 | 86 | 91 | 100" under the box.
      - Explain "2 finestres sense model servit".
14. **V4 / V6 D3 / D4 · epistemic labels and an unclear decision.**
    - *Problem:* V4 is "CONFIRMATORI" without a named prior hypothesis. "Ja comprat: 2,1 % dels slots … 25.353 impressions" contradicts "vet a re-compres … ja aplicat". D4 says "Explorar només als slots 9–10" while V0 says "Explorar el slot 10 en el 30 % de peticions". Its prediction "cost ≤ 0,2 punts" cannot be measured at the final.
    - *Fix:*
      - V4 subtitle: "hipòtesi del 15:50 (historial: ja comprat 1,66 %) confirmada en directe". Otherwise downgrade V4 to EXPLORATORI.
      - Split the "Ja comprat" share before and after 15:50.
      - D4: state one decision, with a measurable prediction such as "exploració ≤ 5 % dels slots, només 9–10".
15. **Catalan and consistency polish.**
    - "×1,49 efecte" → "efecte ×1,49".
    - "Cada punt d'on-time" → "Cada punt percentual d'on-time".
    - "re-compres" → "recompres".
    - "llum verda ≥ 90 %" (V1) and "llum d'estat 90 %" (V2) → "semàfor de l'organització ≥ 90 %" in both.
    - "Llibre de decisions" → "Registre de decisions".
    - Use the same slot-1 rule everywhere: "vistos a la sessió (abans o últim) i carret". Today V0 says "vist abans … i carret" and V6 says "vistos a la sessió".
    - Add a 6-line footer column, "Per què aquests gràfics", with one rule and a deck reference per view, so the professor sees the theory.

## 3. Already strong: do not change

- Every title is a numeric takeaway generated from one `numbers` dict. Numbers use the ca-ES format ("154.889", "0,39").
- There is one currency (punts finals), stated in the header ruler, and q is normalised (0 = baseline, 100 = oracle) in V1, V2 and V3.
- V1's idea: iso-score curves with score = on-time × q as the what-if. Points with on-time < 50 % are hollow, and the count of dropped teams is printed.
- V2 aligns on-time, points lost (vermillion bars from zero) and the identity residual on one shared x axis. Its latency L4 line ("el model triga 10–45 ms: el retard és xarxa") is good.
- V3 uses box+strip per window, sorted by median, with Δ paired against the same-window reference, and is honest: "no és un A/B".
- V4 shows the median polish as fit + residual in aligned small multiples, with honest unequal slot bands, exact Poisson CIs, and hollow dots when there are fewer than 10 buys.
- V5 draws the expected and realised power curves with labelled log axes.
- V6's outcome column reads "pendent", never a number. The badges use borders, not colours. There are no green/red cues and no legends (direct labels only).
- Interaction is limited to the brush and a Final toggle that stays disabled until 12:00. The footer gives formulas, sources and a glossary.
