# Review R2: simulated Tukey jury and VI professor (build it6, generat 15/11 08:11)

Sources: shots it6_s1–s4 (1440×900, cropped and enlarged), the visible text of dist/index.html, and render.py where a number had to be traced.

## 1. Scores

| Criterion | R1 | R2 | Δ | Why |
|---|---|---|---|---|
| 1 Usefulness for deciding | 7 | 8 | +1 | "Vigilar durant la final" (4 triggers, a status line) and the printed V5 rule now cover "durant", but the status line shows a trigger already firing (fz-v9a al 73 % < 95 %) and gives no action. |
| 2 Adequacy of charts | 6 | 7 | +1 | Overview+detail, log(r+0,5), the line-range ledger and the extended V5 axis fix the encodings; labels still collide in V1-detail, V2 and V5, and the V4 panel headers run together. |
| 3 Coherence | 5 | 7 | +2 | The paired A/B, loss signs, frozen hash and EXPLORATORI badges remove most R1 contradictions; the dg 01h incident still has three prices (V1 23,4 · V6 23,1 · V2 24,2). |
| VI theory | 7 | 8 | +1 | The "Per què aquests gràfics" column, L4 cause annotations and one colour per meaning in V6 are visible; text overprinting (W1 p119) is the main remaining lapse. |
| Tukey spirit | 8 | 9 | +1 | Frozen SHA, hinge band, "fora de la tanca 48,9", re-expression and a paired Δ with IC95; ×k residuals are still printed on hollow cells (< 10 buys), and D3 "ja guanyat 11,7" is an ev-v1→ev-v2 before/after that the model change confounds. |

## 2. Round-1 fixes

Jury items
1. H1 and first screen: done (the H1 states #3 dg 07h and #21 dg 01h; evidence-grade line; "Dades fins a dg 08:00 CET"; glosses).
2. One incident, three figures: partial. 40 % and dg 01h are used everywhere, but the cost is 23,4 / 23,1 / 24,2, and V2 prices against 100 % (≥ 3,7) while D1 uses 98 % (3,3).
3. Pre-registration frozen: done ("15/11 08:09 · sha f3653538" vs "generat 08:11"; the V5 rule is printed).
4. Loss signs and strawman stakes: done ("−0,4 · −12,9 · −15,8"; one tick per real candidate).
5. Coverage of the final: done, with a gap: the D6 trigger fires now and no action is written.
6. V1 dense cluster: partial. The detail panel exists, but only #1 is labelled (spec asks #1–#6), "#1 team_06" overprints our blue node, and there is no "m̂ · mesurat" text.
7. V1 title vs path: done (the path starts at dg 00h; the 01h and 07h nodes are labelled).
8. V4 clamp: done (log(r+0,5); 0 has its own position).
9. V6 encoding and title: done (dark line ranges, 0–25 axis, hollow D3, takeaway title).
10. V5 labels and message: done ("2,0 M pet. (8 dies)", "1 k pet. (6 min)", axis past 2 M); new label collisions.
11. V3 title, Δ and cold panel: partial. The tie title and the "Δq vs ref. · k" header are done; the cold panel has no black ×1 rule and there is no "versions retirades" separator.
12. V2 collisions and L1 notes: partial. Rule labels moved to the margin and 4 causal events replaced the L1 notes, but the line and the rules still cross the event labels.
13. V2 resistant summaries: partial. Median + hinge band and the fence label are done; the five numbers are not printed under the box.
14. Epistemic labels, D3 vs V4, D4: done (all EXPLORATORI; 7,8 % → 0,8 % split; D4 "no mesurable").
15. Catalan polish and "Per què" column: mostly done; new errors are listed in fix 8.

Audit BLOCKER / MAJOR
- B1 paired A/B: done (30 shared windows, IC95; used in D2, D6 and V5).
- B2 D3 refuted on a zero share: done (explicit `None` check in `outcomes`).
- B3 fragile final re-run: partial. Final mode is now gated on API `field_hourly`, not the DB; there is no evidence of the synthetic 2-window smoke test.
- M4 D1 outcome: done (`w_min` over 15-min windows).
- M5 D4/D6 outcomes: done (D4 "no mesurable"; D6 on `live_share`).
- M6 rank H1 vs V1: partial. H1 and V1 now agree, but V1's "#4 de 32" (dg 01h) cannot be counted on dots plotted at dg 07h.
- M7 identity residual: done ("36 de 44 finestres informatives"; whisker hidden above 95 %).
- M8 CONFIRMATORI on practice: done.
- M9 D3 vs V4: partial. The sub splits 7,8 %/0,8 %, but the "Ja comprat" header still shows the pooled 1,7 %, which is above the D3 threshold of 1,5 %.
- M10 V4 × factors: done ("×13" is the raw ratio; ×k is called a residual on this scale).
- M11 top-6 definitions: partial. The box uses top-6 rivals by API rank with zeros as missing; the 15-min band (build_dataset.py:108) still takes the top-6 by conversion, including team_37, with zeros unfiltered.

## 3. Remaining fixes (highest impact first, each < 10 min)

1. **One price for dg 01h: the first screen shows 23,4 (V1) beside 23,1 (V6).** render.py:486 `N["d1_hi"] = N["gain_worst"]`; render.py:241 `worst_loss` uses `(0.98 − s)`.
   - V2 title: "…quedar per sota del 98 % ens costaria 3,3 punts finals (mediana horària); l'hora dg 01h (on-time 40 %), 23,4". Move "≥ 3,7 respecte al 100 %, mitjana ponderada" to the sub.
2. **The status line shows a pre-registered trigger already firing, with no action.**
   - New line: "⚠ ACTIU · Estat (07:30–08:00): 100,0 % servit · fz-v9a-xcat1.0 només al 73 % → el disparador D6 ja salta: tancar el repartiment amb fz-v10-nocorr abans de les 10:00 · p95 1,4 s". Under the triggers: "95 % = llindar d'acció; 98 % = objectiu D1".
3. **V5 says "pesa més" for 0,88 vs 0,86, yet the page calls a 0,02 gap a tie.**
   - Title: "…i una hora de caiguda del writer (Δ 0,88) pesa tant com servir el pitjor candidat (cf-rot, Δ 0,86) → congelar fz-v9a-xcat1.0". Move "efecte d'una caiguda" to the right end above its line, cf-rot below its line, nocorr to x ≈ 3k: the black curve now strikes through all three.
4. **V3: nocorr tops the chart (+9 vs +8), yet V6 says we would lose 0,4 by serving it.**
   - Title: "Δ aparellat (fz-v9a − nocorr) +0,02". Sub: "nocorr encapçala per mediana perquè fz-v9a té 5 finestres més; a les 30 compartides fz-v9a va +0,02 per sobre: l'ordre és soroll".
5. **V1 labels collide on the first screen.** "#1 team_06" overprints our blue node and the "60" iso tick: put it above its own dot with a 1 px leader. "referència org.": `text-anchor: end`, left of the ✚.
   - Label #2 too, so "#3" can be counted. Break "mateix model a 98 % → +23,4 punts finals" into two lines that end before the "detall" box.
6. **Text halo on every annotation (V1, V2, V5):** `paint-order: stroke; stroke: var(--bg); stroke-width: 4px; stroke-linejoin: round`. In V2 set `text-anchor: end` on "14:50 motor nou (ev-v1)" and "00:19 entra fz-v9a", so the 15:50 rule and the 01h dip stop crossing them.
7. **V4 panel headers run together ("…dels slots slot 1: 9,0/1.000…") and mix units.** Two lines per header: "slot 1: 9,7 per 1.000" / "25,4 % dels slots"; "Ja comprat": "0,8 % dels slots després del vet" (matches D3 ≤ 1,5 %).
   - Sub: "convertia 1,66 %" → "convertia 16,6 per 1.000". Print no ×k on hollow cells (< 10 buys): drop "×0,5" and "×2,0" in "Ja comprat".
8. **Catalan.** "residu de l'identitat" → "residu de la identitat" (V2) · "re-executar" → "reexecutar" (V6) · D2·D6 card "diferències ≥ 0,19." → "diferències ≥ 0,19 compres/100."
   - "El slot 1 ven ×13 els slots 7–10" → "ven 13 vegades més que els slots 7–10" · "es ven 18,3 cops per 1.000" → "es ven 18,3 vegades per cada 1.000 impressions".
   - "converteix ×3,4 la baseline freda" → "converteix 3,4 vegades més que la baseline freda" · "8,1× menys variància" → "8,1 vegades menys variància".
