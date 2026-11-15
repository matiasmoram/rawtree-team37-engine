# Concept C: "Points ledger & what-if" (Premi Tukey, team_37, RawTree)

Sources: brief_v1.md (F1–F9, D1–D6), notion_github.md (§4–§5), vi_theory.md (cited as deck p.N). One currency everywhere:
**LB pts** = the leaderboard's normalised score /100 (≈71.4 conversion + 14.3 cold + 14.3 reliability). "≈" = derived by
arithmetic from real numbers. Assumptions A1/A2 appear as badges on the page.

## 1. Thesis and headline
The final is ranked in points, not purchases, so every chart speaks points. In score units the verified dilution identity
becomes a product: (team − b)/(o − b) = s·(m − b)/(o − b): **conversion score = on-time share s × served-model score q**.
That one identity drives the ledger, field scatter (iso-score curves), what-if and timeline, so the views agree by
construction, and the page shows the identity's residuals. Exchange rate: 1 purchase/100 req ≈ 35 conversion-score pts
≈ 25 LB pts. With fz-v9a (2.25 vs baseline 0.59 → q ≈ 58): +1 pp on-time ≈ +0.41 (conversion) + 0.14 (reliability, A1)
≈ **+0.56 LB pts**. At 09:45 the team picks fixes from a list sorted by points at stake. After 12:00 the same views get
black "realised" marks (decisions vs outcome).

**Headline:** "Our points leak through the pipe, not the model: same model, on-time 98.7 % → 24–37 %, rank 3 → 21."
**09:45 line:** "Fix the writer first (D1 ≈ +7…+19 pts), keep fz-v9a (D2), no traffic split (D6); exploration ≤ 0.6 pts."

## 2. Layout (1440×900, 2 screens; at 1280 the columns scale and V2 moves under V3)
Screen 1 (above the fold): overview → decide → manipulate (Mantra W2 p.37–40). Entry point = V1 top-left (P1 p.95).
```
+---------------------------------------------------------------------------------------------------------------+
| H  Our points leak through the pipe, not the model  ·  score = on-time x model quality      [Pre-final|Final]  | 64px
|    1 buy/100 req ~ 25 LB pts · +1 pp on-time ~ +0.56 pts · 09:45: D1 > D2 > D6 >> D4 · A1 A2 badges            |
+------------------------------------------------------+--------------------------------------------------------+
| V1 POINTS LEDGER (LB pts, axis 0-100)       720x360  | V4 POINTS AT STAKE D1-D6 (delta LB pts)      720x360   |
| Sun 00-01 |#### model ####|=rel=|.cold.| TOTAL  :100 | D1 single writer+standby  |      *==============| 7-19 |
| Sun 01-02 |#### model ####|<<fallback<<|=|.|TOT :    | D2 keep fz-v9a (vs cf-rot)|     *===|            ~7-8  |
|           0     20     40     60     80    100       | D6 no 50/50 in final      |   *==|             0.5-4 |
| identity check: residuals . .: .:. . [-0.05|+0.05]   | D5 dedicated cold route  |=o=|                  ~0   |
| ghost dashed box to 100 = oracle ("left on table")   | D3 slot-1 rules           |  o - - - - - >   <=23*f ? |
|                                                      | D4 explore slot 10        |o                  <=0.6  |
|                                                      | [] banked: re-buy ban +17 (ev-v1 0.69 -> ev-v2 1.36)   |
|                                                      |        -5    0    5    10    15    20                |
+---------------------+--------------------------------+----------+---------------------------------------------+
| V3 WHAT-IF controls | V3 OUTCOME                    600x440     | V2 FIELD: on-time x served quality  520x440 |
| Model (live n)      | Expected LB pts (bullet, 0-100)           | q |       C=80   .      .  team_06 .         |
| (o) fz-v9a 2.25 2657| [lightgrey|midgrey|darkgrey]  field bands | ^ |  .    C=60   .   .  .                    |
| ( ) fz-v10-nocorr   | ########[--|--]  median, box = 10-90 %    |   | (o)<=================(*) team_37 01-02   |
| ( ) cf-rot 1.92  479| 0    20    40    60    80   100   | leader |   |   .  C=40  .   (@) your scenario       |
| ( ) lgbm-rec 1.48-60|                                           |   | .   C=20  .   .  [ top-6 band 93-100 ]  |
| On-time --*----- 84%| Rank: 20 dots, each = 5 % of 2,000 sims   |   +-------------------------------> s %    |
|  rug = 13 Sat hours | oo                                        |     40    55    70    85    100            |
|  shade 93-100 top-6 | oooo o o    ^3 obs       ^21 obs          | ghost: team_37 00-01; hollow = s<50 %      |
| Cold (o)same ( )tier| 1    5    10   15   20   25   30   42     |                                            |
| [D1 target 97 %]    | "P(top 3) = k/20"                         |                                            |
+---------------------+-------------------------------------------+--------------------------------------------+
```
Screen 2 (evidence, "why", details on demand):
```
+---------------------------------------------------------------------------------------------------------------+
| V7 RELIABILITY TIMELINE  x: Sat 10:00 -> Sun 02:00 || Final 10:00-12:00 (appended)      1440x330 | Tukey box  |
| on-time% 100 [######## grey band = top-6 min-max ########################################]     |  99 T      |
|           90 - - - - - - - status-light line - - - - - - - - - - - - - - - - - - - - - - -     |  90 +-+    |
|              *-*-*  *-*-*-*-*    *-*-*-*-*-*   *-*-*-*-*-*-*-*   *                             |  84 |-|    |
|                   \/   "15:05 DNS 53.7 %"  "18:46 writer timeouts"   "Sun 01:00 24-37 %"       |  73 +-+    |
| pts lost  |  || |||   |    | ||     |   ||          |||||   (vermillion bars from 0)          |  o 40 out  |
+------------------------------------------------------+--------------------------------------------------------+
| V5 MODEL EVIDENCE: score per 15-min window  720x540  | V6 WHAT SELLS: why fz-v9a works            720x540     |
| fz-v9a-xcat1.0  2.25  n=2,657 |   . .[.|.]. .        | (a) buys/1,000 by slot: 3.70 1.33 1.15 0.65 ... 0.31   |
| reference       1.94          |  . [.|.] .           |     slot 10 outlined vermillion = exploration slot     |
| cf-rot          1.92  n=479   |  .[ | ].             | (b) relation x slot: viewed-earlier 12.5 / last 11.3 / |
| lgbm-recent     1.48-1.60     | .[.|.].              |     other 3.3 at slot 1; all ~0.5 at slots 4-6         |
| ev-v2 ...       1.36          |[.|.]                 | (c) purchase % per item, sorted, from 0:               |
| 0 = baseline -----------------+----------- 100=oracle|     last viewed 0.40 ... already bought 0.007          |
| [conversion | cold] toggle                           |                                                        |
+------------------------------------------------------+--------------------------------------------------------+
```

## 3. Views (7)
Per window: s = on_time/100; b = baseline conversion; o = implied oracle = b + 100(team − b)/score (api_teams.csv 1-h rows
+ api_progress.csv `score`; identical for every team per hour, verified); m = served conversion (api_versions.csv,
request-weighted); q = 100(m − b)/(o − b). LB: conversion 0.714·s·q; reliability 14.3·s (A1); cold
14.3·clip(s·(m_c − b_c)/(o_c − b_c)) with o_c unknown (A2).

### V1 Points ledger (waterfall, two juxtaposed hours)
- **Decision:** D1, and "where do our points go?". The overview everything else zooms into.
- **Data:** api_teams.csv (team_37 + baseline rows, span_s=3600, t0 = Sun 00:00 / 01:00: conversion, cold_conversion,
  on_time); api_versions.csv (m); api_progress.csv (score → o). Steps: +model if always served (0.714·q) → −lost to fallback
  (0.714·(1−s)·q) → +reliability (14.3·s; unearned 14.3·(1−s) as a vermillion stub) → +cold → = TOTAL.
- **Marks/channels:** horizontal bars. x = LB pts (rank-1 channel, P2 p.35–37). Hue = gain vs loss (2 values). Lightness
  within blue = component (ordered by weight 71/14/14). The 2 hours are rows on one 0–100 axis (small multiples,
  MV p.45–47). A dashed ghost box from TOTAL to 100 = oracle ceiling.
- **Why:** a waterfall is the honest form for an additive decomposition. TOTALs start at 0, every step is a length on the
  common axis, and the axis is not truncated (W3 p.6; Correll CHI 2020). Rejected: stacked bars (only the base layer is
  comparable, W3 p.11–12), pie (W3 p.39–45), gauge (W3 p.19–21).
- **Title:** "Same model family, two hours: on-time 98.7 % → 24–37 % took team conversion 2.23 → 1.30 and rank 3 → 21,
  while the served model still converted 1.87–2.37".
- **Interaction:** default = 00–01 vs 01–02. A dropdown offers any 1-h window Sat 10:00–Sun 02:00, plus "Final 10–12"
  after 12:00. Hover = formula and inputs (s, m, b, o, n, source). Clicking the fallback step outlines the loss windows in
  V7 (linked highlighting, MV p.64–69).
- **Uncertainty:** model-step whisker = min–max q over the hour's four 15-min windows; fallback step uses the s range
  (e.g. 24–37 %), labelled "range across 15-min windows". Below: Tukey residual strip (actual − predicted team conversion
  per 15-min window, ±0.05 band), which is why the ledger can be trusted.

### V2 Field: on-time × served-model quality (42 teams)
- **Decision:** D1 vs D2. Which axis moves us toward the top 6?
- **Data:** api_teams.csv, all teams, selected 1-h window. x = on_time. y = q̂ = 100(m̂ − b)/(o − b), where
  m̂ = (conversion − (1−s)·b)/s (the identity; every team falls back to the same baseline). Tooltip: model_version,
  conversion, cold_conversion, requests, rank.
- **Marks/channels:** points; both axes are positions on common scales. Iso-score curves C = s·q at 20/40/60/80 in thin
  grey with direct labels. team_37 is blue: 01–02 filled (default), 00–01 a faded ghost joined by an arrow (connectedness,
  P1 p.88). Other teams grey; the top 6 directly labelled. Reference = black cross at s = 100. Teams with s < 50 % are
  hollow (m̂ is unstable when the denominator s is small).
- **Why:** a scatter for a relationship between 2 quantities (W3 p.71). Rejected: dual-axis bars per team (P2 p.54–59) and
  42 time series (spaghetti, W1 p.45–46). The iso-curves make the product geometric: moving right is worth as much as up.
- **Title:** "Same height, different column: at 98.7 % on-time we were 3/42; at 24–37 % the same model sat at 21/42.
  The top 6 all run at 93–100 %."
- **Interaction:** the hour toggle is shared with V1. The what-if scenario is a blue ring "@" at (slider s, median q of the
  chosen model) and moves with the controls (dynamic layer, MV p.14–24). Hover = details on demand.
  **Uncertainty:** team_37 has a vertical whisker (q range over its 15-min windows); other teams' only on hover.

### V3 What-if: model × on-time × cold → score and rank
- **Decision:** D1 × D2 × D5: "what do we get if…". Bertin: the decision-maker manipulates the graphic (W1 p.78).
- **Controls (scented widgets, MV p.99):** model radio with live n: fz-v9a-xcat1.0 2.25 (n=2,657); fz-v10-nocorr ≈ README
  ablation "correction off" (2.17 vs 2.21); cf-rot 1.92 (n=479); lgbm-recent 1.48–1.60. On-time slider 40–100 %, default
  **84 %** (Tukey median of 13 Saturday hours); rug = those hours, grey band = top-6 93–100 %, tick = our best hour 98.7 %.
  Cold radio: same model (fz-v9a cold 2.74–2.88), cf-rot (2.78), ev-v2-tier (1.90, "cold reserve").
- **Engine:** 2,000 draws, recomputed in JS in < 100 ms (W2 p.13). q = request-weighted bootstrap of the chosen model's
  15-min window scores (V5). Each of the 41 rivals draws one of its last 4 hourly LB proxies (api_progress
  `score`·0.714 + 14.3·on_time + cold proxy). Ours = 0.714·s·q + 14.3·s + cold term. Rank = 1 + rivals scoring higher.
- **Outputs:** (a) bullet chart of LB pts, axis 0–100 (W3 p.19–21: length, not angle; compact): grey bands = field
  quantiles (median team / top-6 cut / leader), blue bar = our median, thin unfilled box = our 10–90 %, black tick = leader
  median. (b) Quantile dot plot of rank: 20 blue dots (each 5 % of draws) on a 1–42 axis; black triangles = observed ranks
  3 (00–01) and 21 (01–02) as a back-test (run with those hours' s and field, the engine must land near them).
- **Why:** quantile dots frame an ordinal forecast as counts ("4 of 20 → 20 %") (AV p.43; Wilmer & Kerns). Rejected:
  hypothetical outcome plots (need motion, P1 p.65) and a single expected number (hides spread; bar-tip error).
- **Title (live template):** "At {s} % on-time, {model} → {median} pts, rank {p10}–{p90} (median {m}); +1 pp ≈ +0.56 pts".
- **Default/interaction:** fz-v9a, 84 %, same-model cold = reliability left unfixed. The "D1 target 97 %" button sets the
  slider. After the final, the realised score and rank are drawn as black marks.
  **Uncertainty label:** "box/dots = 10–90 % of 2,000 simulated finals from Sat windows; field as of Sun 02:00; not a CI."

### V4 Points at stake per decision (the 09:45 triage)
- **Decision:** the order of fixes for D1–D6.
- **Data:** the V3 engine plus the doc tables; decisions.yaml stores each row's inputs with a source column.

  | Row | Options compared | Δ LB pts | Evidence |
  |---|---|---|---|
  | D1 | s 84 → 97 % (+13 pp); avoid a 01–02-type hour (mean ≈ 63.5 % vs 97 %) | ≈ +7…+19 | live, F1 |
  | D2 | fz-v9a vs cf-rot: Δ0.33 conv (×25, ×s) | ≈ +7…+8 | live; windows differ |
  | D2 | vs lgbm-recent: Δ0.65–0.77 · vs nocorr: Δ0.04 | ≈ +16…+19 · ≈ +1 (tie) | live · ablation |
  | D6 | 50/50 split with cf-rot costs half of D2 · with nocorr | ≈ 4 · ≈ 0.5 | F7 power |
  | D5 | best alternative cold 2.78 vs fz-v9a 2.74–2.88 | ≈ 0 | team_19 cold 3.83 = headroom |
  | D3 | slot 1 "viewed earlier" 12.5 vs "other" 3.3 /1,000 | ≤ 23·f | descriptive; f unknown |
  | D4 | slot 10 0.31/1,000 × 30 % of requests | ≤ 0.2 (≤ 0.6) | F4 |
  | Banked | re-buy ban: ev-v1 0.69 → ev-v2 1.36, same window | ≈ +17 realised | live |

  Notes: D6 power = ~190 purchases detect only >26–40 % lifts, and fz-v9a vs cf-rot is +17 % relative. D3 f = share of
  slot-1 impressions that could be swapped, unknown until team_37.feedback. D4 ≤ 0.6 holds if fz-v9a's slot 10 sells 2.4×
  the mixed sample.
- **Marks/channels:** one row per decision, sorted by median (W3 p.5–6). Dot = central estimate, line = range, zero line
  drawn, x from −5 to 20. Filled = live leaderboard evidence; hollow = offline/descriptive; dashed open arrow = upper bound
  only. Fill and shape carry evidence type, not hue (CB p.11–14). Right margin: action + n. **Why:** dot + interval on a
  common scale; bars of means rejected (bar-tip error, hide ranges); sorting makes the triage order preattentive.
- **Title:** "Reliability is worth more than any model switch on the table: D1 ≈ +7…+19 pts; D2 matters only if we regress
  to cf-rot; D4 ≤ 0.6".
- **Interaction:** clicking a row loads it into V3 (D1 → slider 97 %; D2 → fz-v9a ↔ cf-rot toggle) and outlines its
  evidence view in black (V7 for D1; V5 for D2/D5/D6; V6 for D3/D4). After the final, black ticks show realised values.

### V5 Model evidence: score per 15-min window
- **Decision:** D2, D6: is the gap real across windows, or an artefact of the hour? **Data:** api_versions.csv (model_version,
  t0, requests, conversion, cold_requests, cold_conversion) joined to the window's baseline and o; q per window removes
  hour effects (reference 1.84–2.20 by hour; baseline 0.45–0.79).
- **Marks/channels:** rows = models, sorted by median. One tick per window; windows < 300 requests are hollow (the
  leaderboard greys out 100–299). Black bar = median; thin box = Tukey hinges; small diamond = request-weighted mean.
  Reference = black row. Shared x: 0 = baseline, 100 = oracle. **Why:** distribution, not summary (W3 p.26–37); boxplot
  alone hides data (W3 p.29); defensive raincloud = strip, not jitter, labelled intervals (Correll VOTD).
- **Title:** "fz-v9a 2.25 (n=2,657) vs reference 1.94 in the same window; cf-rot's 1.92 rests on n=479; lgbm-recent
  1.48–1.60. Windows, not A/B wins."
- **Interaction:** conversion | cold toggle; cold is relative to the cold baseline (cold converts higher even for the
  baseline: 0.91–1.30 vs 0.45–0.79). Hover a tick → same window lit in V7; the V3 model gets a black outline.

### V6 What sells: why fz-v9a works (evidence for D3/D4; opens the "q" black box)
- **Data:** doc tables F3, F4, F5 (notion_github §5.3–5.5); team_37.feedback once the DB inventory lands.
- **(a) Position curve:** dots + line, buys/1,000 for slots 1–10 = 3.70, 1.33, 1.15, 0.65, 0.78, 0.47, 0.25, 0.34, 0.34,
  0.31. Slots are ordered, so a line is allowed (W3 p.6). Slot 10 outlined vermillion = exploration slot. Annotation:
  "slots 1–3 = 66 % of purchases; item-adjusted slot1/slot10 = 3.5× (raw 6×)". Attention values stay in text, not on a
  second axis (P2 p.54–59).
- **(b) Relation × slot** over slot groups 1, 2–3, 4–6, 7–10: last viewed 11.3/3.4/0.5/0.0; viewed earlier
  12.5/6.2/0.5/0.8; other 3.3/1.1/0.6/0.3. All ink-grey, told apart by shape and direct labels (CB p.14).
- **(c) Relation bars:** purchase % per shown item, sorted, from zero (W3 p.6). "Already bought 0.007 % (15,252
  impressions)" annotated "history said 1.66 %".
- **Title:** "Relation matters only at the top: slot 1 'viewed earlier' 12.5 vs other 3.3 per 1,000; by slots 4–6 every
  relation ≈ 0.5; re-buys sell at 0.007 %."

### V7 Reliability timeline + points lost
- **Decision:** D1 (on-time target; is a standby needed?) and D6 (freeze timing near incidents).
- **Data:** api_teams.csv, team_37 15-min on_time. Top-6 band = min–max on_time of ranks 1–6 per window. Pts lost per
  window = 0.714·(1−s)·q_w + 14.3·(1−s). Final windows are appended after 12:00 by re-running the pipeline.
- **Marks/channels:** top: line + dots of on-time on a full 0–100 axis, grey top-6 band, dashed 90 % status-light line.
  Bottom, same x: vermillion bars from 0 = LB pts lost. Right margin: Tukey box of hourly on-time. Event notes (L4):
  "Sat 15:05–15:20 DNS failures, 53.7 %", "18:46–18:49 writer transport timeouts", "Sun 00:19 fz-v9a pushed",
  "Sun 01:00 24–37 %". **Why:** time as a line (W3 p.90); juxtaposed panels on a shared x, not a dual axis (MV p.10–13;
  P2 p.54–59); event text = external context (Stokes & Hearst).
- **Title:** "Saturday hours: median on-time 84 % (hinges 73–90); the top 6 run at 93–100 %. Every hour below the band costs
  points the model cannot win back."

## 4. Color system and text
| Color | Single meaning | Where |
|---|---|---|
| Blue #0072B2 | team_37 / our choice / model points earned | V1 model step, V2 our dot, V3 bar+dots, V5 selected |
| Mid blue #56B4E9, pale blue #B9DDF3 | reliability pts, cold pts (earned; lightness = weight) | V1 only |
| Vermillion #D55E00 | points lost (fallback, late, missing; exploration cost) | V1 stubs, V7 bars, V6 slot 10 |
| Greys #8C8C8C / #D4D4D4; bands #E6E6E6/#CCCCCC/#B3B3B3 | field, context; ordered qualitative ranges | V2, V3, V7 |
| Black #1F1F1F | benchmarks (baseline 0, reference dotted, oracle 100), selection outline, realised marks | all |

- **CVD:** blue vs vermillion differ in hue and lightness (CB p.9); no red-green pair. Losses also carry a "−" sign and
  point left; evidence type uses fill/shape; relations use shape. Checked in Coblis (CB p.3). Uncertainty is never a
  fill: whiskers, unfilled boxes and dots, so it cannot collide with pale-blue cold.
- **Text:** titles = takeaways with real numbers (P2 p.70), generated from the data so they update after the final.
  Subtitles say how to read and give units ("LB pts /100", "purchases/100 requests", "%"). Direct labels, no legends.
  Tooltips give formula, n, window, source; derived values carry "≈"; A1/A2 badges link to footnotes. The header has a
  3-sentence text-only brief (Stokes & Hearst G4). Language: English (organisers' working language) plus the Catalan tagline
  "visualitzar per descobrir, interpretar i decidir".

## 5. Tukey touches (only where they carry a decision)
- **Five-number summary with Tukey hinges** of the 13 Saturday hourly on-time values: 40 / 73 / 84 / 90 / 99. H-spread 17;
  inner fence 73 − 25.5 = 47.5, so the 40 % hour is "outside"; mean 78.6. Used as the slider default and the V7 box.
- **Stem-and-leaf** as the slider's legend: 4|0 · 5|5 · 6|3 · 7|38 · 8|1478 · 9|0139.
- **Resistant estimates:** V5 headlines the median of window scores (weighted mean = secondary diamond): one hot window
  cannot crown a model. **Residuals:** V1's identity strip shows what the model leaves unexplained before we trust it.
- **Re-expression:** conversion in score units per window, 100(m − b)/(o − b), so hours with different oracles
  (3.09–3.73) and baselines become comparable.

## 6. Left out on purpose
- **Live ops panels** (status light, p95 latency/min, last-shoppers feed, trending subcats) = team_36's monitor; in the final
  the leaderboard is hidden and decisions are frozen, so they drive nothing. Latency only as a cause in V7 tooltips.
- **Revenue tie-break (F9):** exact ties only → footnote (€0.49 last hour, €0.95 fz-v9a, team_06 €1.22). **Offline metrics**
  (NDCG, AUC, replay): evaluators rewarded re-buys; popularity judge Pearson 0.43 (0.82 without). D6 note only.
- **F6 heatmap:** redundant with V6b for D3, and would add an ordered colormap (a new color meaning). **Per-team time series**
  (spaghetti) → V2 + V3 field bands. **Experiment registry** → V5 hover. **Gauges, pies, dual axes, 3D, maps, animation.**

## 7. Self-assessment
1. **Usefulness for deciding (strong).** One currency; V4 ranks D1–D6 by points with ranges. The 09:45 action is explicit:
   single writer + standby, freeze fz-v9a, no split, ignore exploration. After 12:00 the same views carry realised marks,
   so decisions face their outcome.
2. **Adequacy of charts (strong).** Positions on common scales throughout; scatter for the relationship; juxtaposition, not
   dual axes; bullet, not gauge; dot + interval, not bars of means; quantile dots for rank; strip + hinges for
   distributions; waterfall totals from zero.
3. **Coherence (strongest).** One identity, C = s·q, feeds V1, V2, V3 and V7, so numbers reconcile by construction;
   identity residuals shown; engine back-tested on observed ranks 3 and 21; titles generated from the same data.

**Main risk (R1):** the points abstraction treats model quality as a black-box q, so the what-if can hide *why* the model
works, and statisticians may read the page as accounting rather than EDA. Mitigation: V5 + V6 (screen 2), linked from
every V4 row, plus the Tukey touches.
**Other risks:** R2: q̂ for other teams assumes the identity (verified only for team_37; unstable at small s) → hollow below
50 % + footnote. R3: A1 (reliability pts = 14.3·on-time share) and A2 (cold oracle unknown; proxy = best team's cold
conversion in the window, drawn as a band), both re-checked against the final ranking after 12:00. R4: the field is frozen
at Sun 02:00, so rank dots may be optimistic if rivals improved overnight (stated on the page). R5: "≈" values read as
precise → always shown as ranges, derivation in the tooltip.
