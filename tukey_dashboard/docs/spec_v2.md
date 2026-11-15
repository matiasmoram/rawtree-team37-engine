# Spec v2: Tukey dashboard for team_37 (RawTree). Judge review and build contract

Inputs: brief_v1 §1–7 (G1–G8 override earlier facts), concepts A/B/C, vi_theory (cited as `deck p.N`).
Every example number below comes from the brief or is derived here with its formula. The pipeline recomputes each one from
`data/dashboard_data.json`; the table and field are named per view. Titles are templates filled from one `numbers` dict.

## Part 1: Scorecard (simulated Tukey jury plus the VI professor)

| Criterion (1–10) | A "Decision cockpit" | B "Descobrir→Interpretar→Decidir" | C "Points ledger & what-if" |
|---|---|---|---|
| 1 Usefulness for deciding | 8 | 7 | 8 |
| 2 Adequacy of charts for data & comparisons | 6 | 8 | 6 |
| 3 Coherence (indicators ↔ charts ↔ conclusions ↔ data) | 6 | 7 | 7 |
| Visible application of VI theory | 8 | 8 | 7 |
| Tukey spirit | 7 | 9 | 5 |
| **Total /50** | **35** | **39** | **33** |

**A (cockpit).**
- *Usefulness:* A has the best audit trail: a decision board, registered predictions and outcome slots. Its stakes, though, mix study designs. D1 "9–33" joins an extrapolation from the practice median to the observed drop between two adjacent hours. D2 "22–27 vs lgbm-recent" compares 15:00 with 00:00, which have a different oracle and baseline.
- *Adequacy:* V0 stacks 5 lines, the oracle band, a hatched area and 5 L4 notes. That breaks "2 layers, 3 with care" (MV p17). V3 pools raw purchases/100 across hours (b 0.45–0.79, o 3.09–3.73), so the hour is confounded with the model. D3 gets three views (V4–V6), built from back-computed counts (≈4 and ≈17 buys) and a table without n.
- *Coherence:* "23 banked" (conversion points) collides with C's "≤23·f" (LB pts), which is a different fact. The resistant line runs on about 8 fz-era windows, so each third holds 2–3 points: it is not resistant, and it duplicates the identity line. Status uses green and yellow fills, which adds two hues.
- *VI:* A has the richest citations. It draws unequal slot spans honestly and never shows missing as 0.
- *Tukey:* A uses fences, median polish and re-expression. Its jackknife over k≈6 windows gives false precision, and the letter-value plot is decoration.

**B (three acts).**
- *Usefulness:* The answer-first ledger works. But the view that actually settles D1 vs D2 (V7, isolines) sits on screen 3, because the acts are ordered by how certain the evidence is, not by how urgent the decision is. Two median polishes and about 2.6 screens make it read like an exam.
- *Adequacy:* B makes the best calls: it pairs each arm with the reference in the same window, shows residuals instead of a heatmap, uses the canonical power curve, and rightly rejects Wilson intervals on the expected (no-luck) metric. Yet V2 rebuilds k from rate × shown and then draws Wilson intervals anyway, which contradicts its own §1.
- *Coherence:* The headline "fz-v9a at 80 % = cf-rot at 100 %" compares two hours with a midpoint b of 0.6. That is the same confound B criticises elsewhere. The power analysis assumes 190 purchases, but G4's realised variance (0.0215/request, so p≈2.2 %) implies about 475 purchases in 21.6k requests.
- *VI and Tukey:* B codes status by border, learns fill/hollow once, and uses two hues. It has the strongest Tukey content: median polish with a diagnostic slope, explicit residuals, and EXPLORATORY → PRE-REGISTERED status labels. This is the jury's native language.

**C (points ledger).**
- *Usefulness:* The identity score = s·q, the field scatter with iso-score curves, and the triage by points are the most decision-shaped ideas, and G1 proves them right. The 2,000-draw rank forecast, however, resamples rivals' last 4 hours and an unknown cold oracle (A2). A statistician will call "P(top 3) = k/20" invented precision, and it cannot be built in pure Vega-Lite.
- *Adequacy:* The waterfall is in LB pts, and 2 of its 4 steps need assumptions (A1, A2). V6 crams three charts into one cell, without intervals and without median polish. A stem-and-leaf as a slider legend is ornament.
- *Coherence:* C has one currency, by construction. But LB pts are not what the API publishes: `api_progress` gives the conversion component. Also, when m̂ is obtained by inverting the identity, "the dot sits on its iso-curve" is algebra, not validation.
- *VI:* Scented widgets, quantile dots and a bullet chart are all correct. But radios, a slider, a dropdown, toggles and row-clicks exceed PR p4's "minimise interactions".
- *Tukey:* Thin: only medians, a residual strip and the five-number summary.

**Contradictions between concepts' numbers, and how they resolve.**
1. **35 vs 25 points per purchase/100.** Both are right, in different units.
   - Conversion component: 100/(o−b) = 100/(3.37−0.58) = **35.8 conv pts**. By hour it ranges 30–43, since o−b spans 2.30–3.28.
   - LB /100: × 50/70 gives **25.6**. Final ranking, where conversion is worth 50 of 100: × 0.5 gives **17.9 final pts**.
   - The real bug is mixing units without labels. A's "23" is the re-buy ban, 0.67 × 35. C's "+17" is the same fact × 25. C's "≤23·f" is a different fact (slot-1 swap, 0.92 × 25). v2 uses one currency (§2.1).
2. **D4 exploration cost.** A gives ≤0.8–1.5 conv pts (slot-10 share of purchases × 2.25). B gives 0.3 conv (mixed-sample slot-10 rate 0.31/1,000). C gives ≤0.2–0.6 LB pts.
   - From G5's live curve, slot 10 = 0.40/1,000. So 0.30 × 0.040 × 35.8 = 0.43 conv pts = **0.21 final pts**. Scaled ×1.65 to the served-model level, it is ≤ **0.36**. Show "≤ 0,4".
3. **fz-v9a 2.25 vs 2.33.** 2.25 is the arm-measured value, request-weighted over its windows (n=2,657). 2.33 is G1's m̂ from the identity in one 60-min window. These are different estimators, so show both with labels. Their gap is the validation.
4. **Sun 01–02 on-time.** Sources differ: 24–37 % (F1, 15-min windows), 39.8 % (G1, the API's 60-min window) and "100 % served since 01:40" (G2, DB writer). They differ in window bounds and in source. The API `on_time` is the only official reliability figure. The DB "served" share is never printed next to it.
5. **Power.** A, B and F7 say "190 purchases ⇒ 26–41 %". G4 instead gives realised variance 0.0215/request, so the 80 % MDE for a 50/50 split of 21.6k requests is 0.56/100 (≈25 %). On the expected metric (0.00256/request) it is **0.19/100 (≈9 %)**. Use G4, and retire "190" unless the pipeline re-sources it.
6. **Re-buy ban "+23 / +97 % / +17".** This is one before/after comparison (ev-v1 0.69 → ev-v2 1.36). It crosses hours and comes after the 14:50 engine change. Report it as q per window, drawn hollow and labelled "abans/després".
7. **Consistent across all three, so keep:** practice on-time five-number summary 40|73|84|90|99 (Tukey hinges, n=13, inner fence 47.5, so 40 is outside), and +10 pp on-time ≈ +0.166 purchases/100.

## Part 2: Final spec v2 (build contract)

### 2.1 Principles decided by the judge
- **One currency.** Data axes are in *compres/100 peticions*, or in *q*, the served-model score: q = 100·(m−b)/(o−b), with the same-window b and the hour's o. q = 0 is the fallback list and q = 100 is the oracle.
  - Every "points" number is in **punts finals** (out of 100: 70 automatic + 30 jury).
  - The header ruler says it once: 1 compra/100 = 100/(o_h−b_h) conv pts ≈ 36 = **18 punts finals**, and +1 pp on-time = 0.5·q/100 + 0.1 = **0.41 punts finals** at q = 63.
  - Assumption A1: reliability pts = 10 × on-time share, per the rule text. It is re-checked against the final ranking.
  - Why final points: decisions maximise the final ranking, and the conversion part is exact from `api_progress`.
- **Points are rates, not sums.** A window's "points lost" means *the final-equivalent loss if the whole final behaved like this window*. A period's loss is the **request-weighted mean** of its windows, never their sum. All three concepts risked summing windows.
- **Normalisation.** q is used identically in V1 (y), V2 (losses) and V3 (x). This removes the hourly drift in b and o.
- **Language.** All UI text in **Catalan**: the challenge statement and its slogan are Catalan, and the jury is the FME.
  - Model IDs and field names stay verbatim. The footer has a CA↔EN glossary.
  - Use the ca-ES number locale: "2,33", "21.600", "39,8 %" (with a space before %).
- **What-if slider: NO.**
  - The iso-curve field (V1) already *is* the what-if: one annotated arrow answers "same model at 99 %".
  - A rank simulation needs rivals' future behaviour and an unknown cold oracle (false precision).
  - Bootstrapping in JS breaks the Altair-only build.
  - PR p4 says to minimise interactions. Bertin's rule (W1 p78) is still honoured by the brush.
- **Exactly 2 interactions, with meaningful defaults.**
  - I1: a time brush on V2's x axis. Brushed items are linked in V1 and V3 by opacity (others drop to 0.25; no new colour). The default is no brush, so everything shows.
  - I2: a period toggle [Pràctica | Final]. It is an HTML radio that swaps pre-built specs, so the titles stay computed. It is disabled until the `final` block exists, and defaults to Final when it does.
  - Hover tooltips provide details on demand (W2 p37-40).
- **Epistemic badges** in the top-right corner of each view:
  - EXPLORATORI: dashed border.
  - PRE-REGISTRAT hh:mm: thin solid border.
  - CONFIRMATORI: thick solid border.
- **Build.**
  - Altair 5 → VL5 JSON. V1, V2, V3, V5 and V6 go in one `vconcat`, which the shared brush needs. V4 is a separate embed.
  - Pin exact versions of vega, vega-lite and vega-embed on jsDelivr. `--offline` inlines the JS so the file works offline (brief §6).
  - Compute Tukey hinges and fences in Python. VL's boxplot uses quantile interpolation, not hinges.
  - All times are CET. G7's UTC hours get +1 h.

### 2.2 Layout (1440×900; content 1408 px; 12 columns × 101 px; 16 px gutters; ≈2 screens)
```
y    0 ┌ H1 conclusion (24px)                                   [Pràctica|Final] · dades fins dg 02:00 CET ┐
    32 │ ruler: 1 compra/100 ≈ 36 conv = 18 punts finals · +1 pp on-time ≈ 0,41 · A1 · badge legend          │
    56 ├ V0 VERDICT: 3 lines (15px), each = action · numbers · → V# · badge                                   ┤
   168 ├──────────────── cols 1–7 (812) ──────────────────┬──────────── cols 8–12 (580) ────────────────────┤
       │ V1 FIELD: on-time × served-model q, 42 teams,    │ V6 DECISION LEDGER D1–D6                         │
       │ iso-score curves, team_37 path  (plot 780×330)   │ text │ points at stake │ prediction→final │ ✓✗~   │
   576 ├──────────────────────────────────────────────────┴──────────────────────────────────────────────────┤
       │ V2 RELIABILITY: (a) on-time 15 min (b) final pts lost (c) identity residual │ Pràc ║ Final │ box │
   888 ╞═════════════ fold, screen 1 ═══════════════════════════════════════════════════════════════════════╡
   900 ├ V3 MODEL: strip + box of q per window │ cold ×  (812)  ┬ V5 POWER & decision rule (580)               ┤
  1268 ├ V4 WHAT SELLS: 7 relation panels × slot 1–10, fit (median polish) + observed + residual (1408×340)   ┤
  1656 ├ FOOTER: formulas, assumptions A1–A3, sources (table.field), CA↔EN glossary, commit, build time        ┤
  1800 └────────────────────────────────────────────────────────────────────────────────────────────────────┘
```
Order follows the Mantra and the focal point (W2 p37-40, P1 p95). Screen 1 shows the overview and the D1 evidence. Screen 2 shows "why" and "how sure". Gestalt proximity groups D1 views together (V1, V2) and D2/D6 views together (V3, V5) (PR p4).

### 2.3 Views (7 = 1 text band + 6 charts)

**V0 Verdict band** (HTML, 1408×112). *Decision:* what to do now (all decisions). *Badge:* PRE-REGISTRAT 09:45.
- **H1 template:** "El model ja és de podi, la fiabilitat no: model servit #{rank_m} de {N} ({m:.2f}), però l'on-time {s} % ens deixa #{rank}".
  - Example: #2 de 42 (2,33), 39,8 %, #20.
- **L1 (D1):** "Un sol writer + standby en una altra xarxa, objectiu ≥ 98 % per finestra: cada pp d'on-time val 0,41 punts finals; passar de 39,8 % a 99 % val ≈ 24,5 → V1 V2".
- **L2 (D2/D6):** "Servir fz-v9a-xcat1.0 congelat a les 09:30, sense split: un 50/50 a la final només detecta Δ ≥ 0,19/100 (mètrica esperada); fz-v9a vs nocorr (Δ 0,04) demanaria ≈ 0,5 M peticions → V3 V5".
- **L3 (D3/D4/D5):** "Slot 1 = 44 % de les compres: vist a la sessió al capdamunt (×2,2 sobre l'ajust additiu), mai re-compres; explorar només als slots 9–10 (≤ 0,4 punts); sense ruta freda pròpia → V4 V3".
- **Data:** every number is read from the `numbers` dict produced by V1–V6. There are no free-typed numbers.
- **Rules applied:** a text-only variant that stands alone (Stokes & Hearst G4); the takeaway as title (P2 p70, W2 p5); the page's single entry point (P1 p95).

**V1 Field: on-time × served-model score** (plot 780×330). *Decision:* D1 vs D2 — which axis moves us up?
- **Title (template):** "Mateixa alçada que el #1, columna equivocada: model servit {m:.2f}/100 (q {q}, #{rank_m} de {N}), però amb on-time {s} % puntuem {score} i som #{rank}".
  - Example: 2,33, q 63, #2, 39,8 %, score 25, #20. The example uses o = 3,37; the pipeline uses that hour's o.
- **Data:**
  - `field_hourly` (team_id, t0, requests, on_time, conversion, served_conv, score, rank).
  - The baseline and reference rows from the same table.
  - `progress` → o_h (G3).
  - `arms15` → the measured served q for team_37.
  - Cross-section shown: in Pràctica, the latest complete hour (the G1 window, with its bounds printed); in Final, both final hours (pooling is valid because q and s are hour-normalised).
- **Transform:**
  - s = on_time/100; m̂ = (conv − (1−s)·b_h)/s; q̂ = 100(m̂−b_h)/(o_h−b_h).
  - Teams with s < 0.20 are dropped, and their count is printed. Teams with s < 0.50 are hollow (m̂ is unstable).
  - Whisker on team_37: ±100·0.05/(s·(o_h−b_h)), the identity residual bound (G1). That is ±4,5 q at s = 0.398.
  - Assert s·q̂ = published score. This is a build check, not evidence.
- **Marks and encodings:**
  - point: x = on-time % (Q, domain 0–100, zero shown); y = q (Q, 0–100; the axis note reads "0 = llista baseline · 100 = oracle").
  - The 41 other teams are grey dots (r 4). The top 6 are labelled directly. team_37's selected hour is a filled blue dot (r 7) with its whisker, plus a blue "×" tick at the **measured** arm q.
  - team_37's hourly path, ordered by t0: a thin light-blue line with hollow dots, with end labels "ds 10h" and "dg 00h".
  - The reference is a black "+".
  - Iso-curves q = C/s for C = 20/40/60/80: grey #bdbdbd, 1 px, labelled at s = 100 % as "conv 40 = 20 punts finals".
  - Projection: a blue dashed rule from our dot to s = 99 %.
- **Annotations:**
  - On the projection: "mateix model a 99 % → conv 62 (+37 conv = +18,6 punts finals, +5,9 fiabilitat)".
  - On the right axis: "q 0 = {b} · referència q {qref} = {ref} · q 100 = {o} compres/100".
- **Honesty footnote:** "Les corbes són àlgebra exacta (score = s·q: totes les fallades reben la mateixa llista baseline, i b i o són iguals per a tothom dins l'hora). El que és model és q̂ dels rivals: suposa que les seves peticions perdudes convertirien com la baseline. Les corbes no inclouen la fiabilitat (10 punts), així que moure's a la dreta val més del que mostren."
- **Tooltip:** team, hour, requests, on-time, conversion, m̂ ± bound, q̂, published score, API rank.
- **Interaction:** I1 highlights the path dots of the brushed hours.
- **Rules applied:** scatter for a relationship (W3 p71); position on a common scale (P2 p35-37); one hue over grey (P1 p61-64); connectedness for the path (P1 p88); 3 layers with care (field, guides, path; MV p14-24); labelled line ranges (AV p42); direct labels (CB p14); check the statistical model, measured vs m̂ (W1 p66).

**V2 Reliability timeline with points lost** (1250×206 plot + 130 px margin; 304 px in total). *Decision:* D1 (target; is a standby needed?) and D6 (freeze far from incidents).
- **Title:** "L'on-time ens ha costat de mitjana {X} punts finals (equivalent final); la caiguda del writer dg 01:00–01:40 en costa {Y}. Mediana horària {med} % (frontisses {h1}–{h2}) vs {t_lo}–{t_hi} % del top-6".
  - Example: 84 %, 73–90, 93–100.
- **Data:**
  - `windows15` (t0, requests, on_time, conversion, served_conv m_w, baseline b_w, pred, resid).
  - `field_hourly`: the top-6 on-time range per hour.
  - `progress` → o_h.
  - The `final` block is appended.
- **Transform:**
  - q_w as in §2.1. lost_w = (1−s_w)·(0.5·q_w + 10).
  - If m_w cannot be observed (s_w < 0.05), use the arm's median for that hour and flag it `imputat`.
  - Period X = Σ(n_w·lost_w)/Σn_w (never a sum).
- **Marks and encodings:** three rows share x = time (CET). The column facet is Pràctica | Final, with **equal px per hour** and a gap label "8 h sense dades".
  - (a) on-time 0–100 %: a blue line with dots. A grey band #ececec shows the top-6 min–max as a step per hour. A black dotted rule at 90 % reads "llum d'estat (organització)". A blue dashed rule at 98 % reads "objectiu D1".
  - (b) final points lost: vermillion bars from 0. Imputed windows are vermillion outlines with a hatch.
  - (c) identity residual, actual − predicted: grey dots with a ±0,05 band, labelled "{k}/{K} finestres dins ±0,05".
  - Right margin: a Tukey box + strip of team_37's hourly on-time next to the top-6 teams (pooled). Whiskers end at the adjacent values. The point outside is labelled "40 % fora (tanca 47,5)".
- **Annotations (L4, at most 4):** "15:05 DNS 53,7 %", "18:49 writer aturat", "00:19 fz-v9a", "01:00–01:40 writer caigut".
- **Subtitle:** "Latència p95 1,8–2,9 s/h, i el rànquing del model triga 10–45 ms: el retard és xarxa/polling (G8) · n = {N} finestres de 15 min".
- **Tooltip:** t0, requests, on-time, m_w, q_w, lost (conversion part and reliability part), resid.
- **Interaction:** I1 is defined here (an x interval brush).
- **Rules applied:** a line for time (W3 p90); juxtaposed aligned panels, not a dual axis (MV p10-13, P2 p54-59); bars from zero (W3 p6); explicit difference encoding (MV p25-29); equal time intervals (W1 p53-54, W2 p65-68); box + strip (W3 p29, p37), with fences (MV p104); imputed ≠ observed (AV p69); L4 context (Stokes & Hearst).

**V3 Model choice: distributions over windows, normalised** (812×352). *Decision:* D2 (which model) and D5 (a separate cold route?).
- **Title:** "fz-v9a-xcat1.0 puntua q {med} per finestra (k {k}, n {n}), {Δ:+} sobre la referència de la mateixa finestra; cf-rot {Δ2:+}, lgbm-recent {Δ3:+} → servir fz-v9a. En fred ×{r} sobre la baseline freda (referència ×{rr}) → sense ruta pròpia".
- **Data:**
  - `arms15` (model_version, t0, requests, conversion, cold_requests, cold_conversion).
  - `windows15` and the API's 15-min rows: b_w, ref_w, cold baseline, cold reference.
  - `progress` → o_h.
- **Transform:**
  - q_vw; paired Δ_vw = q_vw − q_ref,w; cold ratio r_vw = cold_conv_vw / cold_baseline_w.
  - Keep rows with k ≥ 2 windows of ≥ 100 requests: fz-v9a, fz-v10-nocorr (if present), cf-rot, lgbm-recent, then the reference.
  - Hinges come from Python. Draw the box only if k ≥ 5.
- **Marks and encodings:** hconcat [All 480 | Cold 190 | text 110], with a shared y = model (nominal → spatial region, P2 p35), sorted by median, reference last.
  - All: one tick per window (blue; black for the reference). Ticks are hollow outlines if the window had < 300 requests.
  - The box is drawn as an outline from the hinges, with a thick median tick and whiskers to the adjacent values (labelled "1,5·H"). **No mean, no bars.** x = q 0–100, with zero at the same-window baseline.
  - Cold: the same marks, x on a log2 scale from ×0,5 to ×4, with a black rule at ×1 (the cold baseline). Ticks are hollow if cold_requests < 100.
  - Text column: "k · n · Δ mediana".
- **Badge:** EXPLORATORI, "finestres diferents: no és A/B; 22,6 % de peticions multi-versió".
- **Tooltip:** version, t0, requests, conversion, q, the reference's q in the same window, Δ, cold n, r.
- **Interaction:** I1 lights the brushed windows.
- **Rules applied:** distributions, not summaries (W3 p26-37); a box hides data, so add a strip (W3 p29); a strip rather than jitter, with labelled whiskers (raincloud VOTD); no mean bars (Wilmer & Kerns); normalise (PR p4); avoid averaging out the signal (MV p101); order by median (MV p48-62); aligned rows (MV p45-47).

**V4 What sells: relation × slot, median polish shown as fit + residual** (1408×340). *Decision:* D3 (what goes in slot 1; ban re-buys) and D4 (where exploration is cheap).
- **Title:** "Al slot 1 un article vist abans a la sessió es ven {r1}/1.000 (×{res} sobre l'ajust additiu) i un ja comprat {r7}: slot 1 per a vistos a la sessió, carret just després, mai re-compres".
  - Example: 16,6, ×2,2, 0,4.
- **Data:**
  - `practice.relation_slot` (sb, slot, relation, impressions, buys), from team-served impressions 12:09→03:07.
  - `practice.relation_polish`: overall 0,60; slot effects +1,29/+0,32/−0,32/−0,44; relation effects. The scale is the natural log of per-1,000 + 0,5.
- **Transform:**
  - For each (relation, band): rate = 1000·buys/impressions, with a Garwood CI on buys.
  - fit = exp(overall + row + column) − 0,5; residual factor = exp(resid).
  - The pipeline re-runs the polish and asserts it matches within 0.01.
- **Marks and encodings:**
  - Facet column = relation: 7 panels of 168 px, sorted by relation effect. Panel order is: carret ×1,49, vist abans ×1,17, nou ×1,09, últim vist ×1,00, altre ×0,84, home ×0,39, ja comprat ×0,27.
  - x = slot 1–10, quantitative, so bands keep their true span: 1 | 2–3 | 4–6 | 7–10.
  - Shared y on a log scale of (rate + 0,5), labelled 0,5 1 2 5 10 20.
  - Fit: a grey step segment spanning each band.
  - Observed: a blue dot at the band centre with its CI rule. Dots are hollow if buys < 10.
  - A thin grey connector joins fit and dot (the residual). It is labelled "×2,2" when |ln res| ≥ 0,4.
- **Annotations:**
  - Panel header: "carret no comprat · ×1,49 · 24,3 % dels slots · n slot 1 = 51.265".
  - On "ja comprat": "l'historial deia 1,66 %; en directe 0,08/1.000 → vetar".
  - Subtitle: "slot 1 ×5,6 vs slots 7–10; slot 1 = 44 % de les compres; explorar el slot 10 en el 30 % de peticions costa ≤ 0,4 punts finals; escala log".
- **Tooltip:** relation, band, impressions, buys, rate [CI], fit, residual ×.
- **Interaction:** none.
- **Why this encoding:** a decision-maker reads levels: panel height = relation, step shape = slot, dot off the step = interaction. A heatmap was rejected because luminance ranks 7th (P2 p35-37) and would spend a hue.
- **Rules applied:** small multiples on one scale (MV p45-47); a dot plot may skip zero, with the log labelled (W3 p16-17); unequal bands drawn honestly (W1 p53-54); original + difference (MV p25-29); intervals (AV p42); relations encoded by region, not hue (CB p11-14).

**V5 Power and decision rule (G4)** (560×300 plot; 580×352 in total). *Decision:* D6 (freeze and the switching rule); it also guards D2.
- **Title:** "A la final (21.600 pet.) un 50/50 només detecta Δ ≥ 0,19/100 amb la mètrica esperada (≥ 0,56 amb compres reals): fz-v9a vs nocorr (Δ 0,04) demanaria ≈ 0,5 M peticions → congelar fz-v9a, sense split".
- **Data:**
  - The `power` block: per-request variance 0,00256 (expected) and 0,0215 (realised); between-window SD 0,13–0,28.
  - Candidate Δ: the paired medians from V3, converted to compres/100.
  - The outage effect from V2.
- **Transform:**
  - n on a log grid from 500 to 1e6. MDE(n) = 2,80·√(4σ²/n)·100. n*(Δ) = 31,4·σ²/(Δ/100)². minutes = n/180.
  - Check values: cf-rot (Δ≈0,30) needs 8,9 k requests (50 min) on the expected metric and 75 k (6,9 h) on realised purchases. nocorr (Δ 0,04) needs 502 k (46 h). lgbm (Δ≈0,70) needs 1,6 k.
- **Marks and encodings:**
  - Lines, with x = n (log) and y = MDE in compres/100 (log, 0,02–2; labelled).
  - Expected metric: solid #3a3a3a. Realised purchases: dashed #8c8c8c. Both labelled directly.
  - Horizontal blue rules mark our candidate gaps. A vermillion rule marks "caiguda dg 01h 0,93".
  - Vertical grey rules: "1 h = 10.800" and "final = 21.600".
  - Intersection dots carry n* labels.
- **Decision-rule text (PRE-REGISTRAT):** "Canviar de model només si un 50/50 concurrent abans de les 09:30 dona Δ̂ > MDE(n) en mètrica esperada; si no, fz-v9a congelat. A la final, un sol model (≥ 95 % de peticions)."
- **Footnote:** the curves assume independent requests. The between-window SD (G4) shows extra heterogeneity, so the curves are lower bounds; pair arms within the same window.
- **Tooltip:** n, both MDE values, minutes at 3 req/s.
- **Rules applied:** uncertainty communicated (AV p41-43); a line for a continuous dependence (W3 p90); log axes labelled (W3 p16-17); expressiveness, with just 2 lines (W1 p20).

**V6 Decision ledger with outcome slots** (580×408). *Decision:* the 09:45 triage, then the post-final audit (EDA → registered rule → confirmation).
- **Title:** "La fiabilitat (D1) val fins a 24,5 punts finals; el model (D2) ≈ 5 si tornéssim a cf-rot; l'exploració (D4) ≤ 0,4 · final: {ok}/6 prediccions confirmades".
- **Data:**
  - `manual.decisions` (id, text, decided_at, registered_at, pred_lo, pred_hi, unit, outcome_source).
  - Stakes come from V1–V5 numbers. Outcomes come from the `final` block.
- **Layout:** rows D1–D6, sorted by stake. hconcat of 4 columns with a shared y:
  - (1) Text, 220 px: e.g. "D1 Un sol writer + standby · 09:45", with a badge.
  - (2) Points at stake, 150 px: x = punts finals 0–25 on a common scale, from zero; dots and line ranges.
    - D1: 6,2–24,5. Anchors: practice median 84 % → 99 %, and the worst hour 39,8 % → 99 %.
    - D2: one tick per alternative: nocorr 0,7 · cf-rot 5,3 · lgbm 11,5–13,7.
    - D3: re-buy ban ≈ 12, banked, drawn hollow (before/after).
    - D4: ≤ 0,4, drawn as an open arrow (upper bound).
    - D5: the text "sense estimació".
    - D6: cost of a split ≈ 2,7 (vs cf-rot) / 0,4 (vs nocorr).
  - (3) Prediction → final, 140 px: each row has its own labelled mini-axis. A grey bar is the registered range; a blue diamond is the final value.
    - D1: on-time per window ≥ 98 %.
    - D2: fz-v9a q within its practice hinges.
    - D3: slot-1 share of purchases ≥ 40 % and re-buys = 0 %.
    - D4: exploration ≤ 5 % of slots. Measured only if the feedback table has an exploration flag; otherwise the cell reads "no mesurable".
    - D5: cold ratio ≥ ×2,0.
    - D6: one version serves ≥ 95 % of requests.
    - Before the final, the cell reads "pendent: re-executar el pipeline després de les 12:00". Never a number.
  - (4) Verdict, 60 px: glyph + word in ink: ✓ confirmat · ✗ refutat · ~ no concloent · … pendent.
- **Tooltip:** the formula and inputs behind each stake; the source table behind each outcome.
- **Rules applied:** a bullet-like length instead of a gauge (W3 p19-21); sorted rows (W3 p5-6); line ranges (AV p42); missing ≠ 0 (AV p69); status shown by glyph + word (CB p11-14); confirm the expected (W1 p66).
- The history of decisions (14:50 engine, 15:50 re-buy ban, 00:19 fz-v9a, 01:00 outage) lives as L4 marks on V2's time axis. The ledger rows cite them. Together they satisfy the "decisions log/timeline" requirement without adding a view.

### 2.4 Palette (one colour = one meaning; checked by CVD simulation, Machado 2009, CIE76 ΔE)
| Meaning (only this) | Hex | Mark types | Redundant cue |
|---|---|---|---|
| team_37 observed | `#2a78d6` | dots, lines, ticks, final diamonds | filled/thick, direct label |
| team_37 path, target, projection | `#9ec5f0` path; `#2a78d6` dashed | thin line, hollow dots, dashed rules | dash, "objectiu" label |
| points lost / harm | `#D55E00` | bars and rules only (hatched if imputed) | "perduts" label |
| external benchmarks (baseline, reference, oracle, status light) | `#1f1f1f` | rules, "+" | dotted/dashed + label |
| other teams | `#8c8c8c` | dots (only for marks: 3.4:1 on white) | label for top 6 only |
| guides, fits, realised-metric line | `#bdbdbd` / `#8c8c8c` | thin lines, step segments | text label |
| expected-metric line | `#3a3a3a` | solid line | label |
| bands (top-6 range, predictions, final period) | `#ececec` / `#d4d4d4` | areas, bars | label |
| text | `#222222`; secondary `#595959` | — | — |

- **Measured ΔE76** (normal / protan / deutan / tritan):
  - blue–vermillion 123 / 106 / 122 / 103
  - blue–black ≥ 52; vermillion–black ≥ 65
  - blue–grey ≥ 32 (tritan is the minimum), always backed by a shape or label
  - light blue–light grey ≥ 24 (path only, always hollow)
- No green/yellow status colours. Linked selection uses opacity, not a colour. Re-check with Coblis at build time (CB p3).

### 2.5 Typography and text
- Source Sans 3 from Google Fonts, falling back to system-ui; `font-variant-numeric: tabular-nums`.
- Sizes: H1 24/30 semibold; verdict 15/22; view title 15 semibold (at most 2 lines); subtitle 12 #595959 (how to read + n + window); axis 11; annotations 11 #3a3a3a; badges 10 caps.
- Vega config: `formatLocale` ca-ES (decimal ",", thousands "."). A "%" with a preceding space is appended by labelExpr.
- No legends: direct labels only. At most 4 L4 notes per view. Never restate what is visible (Stokes & Hearst).

### 2.6 Coherence checklist (each one is an `assert` in build.py)
1. One `selected_hour` object (start/end CET) feeds V0, V1 and V6. On-time 39,8 %, conversion 1,27 and rank 20 come from it only.
2. One `norm` table holds b_w, ref_w and o_h. One `q()` function serves V1, V2 and V3. The header ruler = median over hours of 100/(o_h−b_h).
3. fz-v9a's median q and hinges (V3) = V6 D2's prediction = V0 L2.
4. team_37's m̂ (V1) vs the measured arm value for the same hour (V1 tick, V3): |Δm| ≤ 0.05/s, otherwise flag it on the page.
5. 0,41 per pp (header) = V1 projection = V6 D1 stake ÷ Δs = V0 L1.
6. A period's loss = the request-weighted mean of lost_w, never a sum. Its conversion part reconciles with 0.5·(q_h − score_h) from `api_progress` within 2 %.
7. On-time five-number summary (V2 margin; Tukey hinges) = the 84 % anchor in V0 and V6.
8. Slot-1 share 44 % and the relation effects (V4) = `relation_polish` = V0 L3 = V6 D3.
9. MDE 0,19 / 0,56 and n* (V5) = V0 L2 = V6 D6. The candidate Δ in V5 = V3's paired medians.
10. D4 ≤ 0,4 in V4's subtitle = V6 D4.
11. Ranks come only from the API `rank` field. The model rank is the order of q̂ among plotted teams (s ≥ 0,2), printed as "de {N_plotted}".
12. All times are CET (G7 UTC + 1 h). Denominators (n) appear in every subtitle, and they sum to the table totals.
13. Decimals: compres/100 → 2; q → 0; punts finals → 1; on-time → 1. The ca-ES locale applies everywhere.
14. Colour audit: a script lists every mark's hex per view; each hex maps to exactly one meaning in §2.4.
15. A title may only contain numbers from `numbers`. In Final mode, no placeholder appears: an empty slot reads "pendent".

### 2.7 The 5 jury questions most likely to be asked, and where the page answers
1. "How can your model be #2 when 60 % of requests fell back?" → V1: identity, whisker ±0,05/s, measured tick next to m̂. V2(c): residuals within ±0,05 in 50/51 windows. The footer gives the formula.
2. "Your model comparisons come from different hours. Isn't that confounded?" → V3: q per window against the same-window b and o, paired Δ vs the reference, and the "no és A/B" badge. V5 explains why no A/B was run.
3. "Are the lost points measured or modelled?" → V2(b): formula tooltip, measured m_w, the A1 badge. Checklist item 6 reconciles them with `api_progress`.
4. "Why not split traffic in the final to learn?" → V5's curves (G4) and the decision rule, plus V6 D6's cost of a split.
5. "Did the decisions work?" → V6 columns 3–4 in Final mode, the Final facet of V2, and V1 in Final mode.
   - A likely follow-up, "Where is Tukey?": V2's box with hinges and fences, V3's strip + box, V4's median polish as fit + residual, and V6's EDA → confirmatory chain.

### 2.8 Deliberately left out
- The live ops monitor (team_36's ground) and a rank race (spaghetti, W1 p45).
- The revenue tie-break: a footnote only (€0,95 when fz-v9a serves vs team_06 €1,22).
- The F3–F6 doc tables: G5 supersedes them, and they have no n. The session × history polish (F6) goes for the same reason.
- G6 segments: a footnote in V4 (home + returning user 0,40, n = 14.902).
- G7 prices and the Pets trend: material for the main jury talk.
- A latency letter-value plot: G8 gets one sentence in V2 instead.
- The what-if slider and rank simulation (§2.1); gauges, pies, status lights and colour heatmaps.

**Open risks:**
- R1: G1's window bounds must be printed from the data.
- R2: A1 (the reliability formula) must be checked against the final ranking.
- R3: fz-v9a only served from 00:19, so k is about 7 windows. The box draws, but its hinges are coarse; say so in the tooltip.
- R4: if the final per-version table is missing, V6 shows "pendent", never an estimate.
