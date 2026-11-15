# Concept B: "Descobrir → Interpretar → Decidir" (a Tukey EDA story in three acts)

Sources: `docs/brief_v1.md` (F1–F9, D1–D6), `docs/notion_github.md` (§N.N), `docs/vi_theory.md` (rule numbers, "deck p.N").
Numbers marked *derived* were computed for this spec from those sources. The computation is given next to each one.

## 1. Thesis and headline

The page tells the challenge slogan as three acts, one per screen, and each act has a different epistemic status.
**Act I, Descobrir**, shows the surprises we found by looking, labelled EXPLORATORY: the reliability collapse, "the history lied", the position curve, the relation × slot interaction.
**Act II, Interpretar**, separates signal from noise with resistant statistics, labelled CHECKED: paired distributions over 15-minute windows (not single means), five-number summaries, median polish with residuals, bootstrap/jackknife intervals, and a power curve.
**Act III, Decidir**, turns the evidence into rules with thresholds, labelled PRE-REGISTERED (or POST-HOC if committed after 10:00). It checks them against the final's outcome.
A pinned ledger at the top gives the answer first, so a decision-maker never has to read the EDA to act. The statistician can audit every rule down to its denominator.
Statistical honesty is the selling point: (a) the practice leaderboard reports *expected* purchases (hidden P(buy), "no luck"), so the rival's Wilson intervals model a coin flip that is not there; the real noise is between-window heterogeneity. (b) During the final only *realized* buys exist (about 190), so Poisson power applies. (c) Two-way tables come as fit + residual, never a bare heatmap of means.

**Headline (page title):** *Reliability, not the model, decides the final: fz-v9a at 80 % on-time scores the same as cf-rot at 100 % (1.92 purchases/100).*
*Derived* from the F1 identity, team = s·m + (1−s)·b, with m = 2.25 and b = 0.6 (baseline midpoint 0.45–0.79): 0.8·2.25 + 0.2·0.6 = 1.92.

## 2. Layout at 1440×900 (12-column grid, 96 px columns, 24 px gutters; at 1280 the columns shrink, nothing reflows)

```
y=0    ┌────────────────────────────────────────────────────────────────────────────────────┐
       │ RELIABILITY, NOT THE MODEL, DECIDES THE FINAL                team_37 · RawTree final │
       │ fz-v9a at 80 % on-time = cf-rot at 100 % (1.92/100) · data Sat 10:00–Sun 02:00 CET   │
       │ [I Descobrir] [II Interpretar] [III Decidir]   ruler: 1 purchase/100 ≈ 35 conv. pts  │
y=96   ├──────────────┬──────────────┬──────────────┬──────────────┬─────────────┬─────────────┤
       │D1 Reliability│D2 Model      │D3 Top-3 rules│D4 Exploration│D5 Cold start│D6 Freeze    │ LEDGER
       │1 writer +    │fz-v9a @100 % │no re-buys;   │slots 7–10    │no own route │09:30–09:55; │ (text +
       │standby <90 % │              │viewed → 1–3  │only, ≤30 %   │             │no conv swap │ stake bar)
       │███████ 33 pt │██▌ 12 pt     │█████ 23 pt   │▏ ≤0.3 pt     │ n/a         │ —           │
       │CHECKED → V1,7│EXPLOR. → V4  │CHECKED → V2,5│CHECKED → V3  │EXPLOR. → V4 │CHECKED → V6 │
y=210  ├──────────────┴──────────────┴──────────────┴──────────────┴─────────────┴─────────────┤
       │ I · DESCOBRIR   (exploratory: found by looking)                                       │
       │ V1 Sun 01:00: the model still sold 1.87–2.37, on-time fell to 24–37 %, team 2.23→1.30 │
       │ ┌ conv/100: team ● · served model ○ · orange gap = fallback cost · base/ref/oracle ┐┌───┐│
       │ ├ on-time %: ● per 15 min · 90 % status rule · grey band = top-6 (93–100 %)        ┤│box││
       │ └ Sat 10:00 ······································································ Sun 02:00 ┘└───┘│
y=580  ├──────────────────────────────────────────┬───────────────────────────────────────────┤
       │ V2 What sells: dot plot, log x, Wilson CI │ V3 Position: (a) buys/1,000 + Poisson CI   │
       │ 8 relations, n shown + buys per row       │          (b) attention index, raw vs adj.  │
y=900  ╞═══════════════════════════════ fold (screen 1) ════════════════════════════════════╡
       │ II · INTERPRETAR  (checked: resistant statistics, intervals, power)                │
       │ V4 Paired vs reference per 15-min window (raincloud per model) │ V6 Power / MDE curve │
       │   [All | Cold ÷ cold baseline]                                  │   [50/50 | 80/20]    │
y=1340 │ V5a Median polish: slot band × relation │ V5b Median polish: session × history share │
y=1800 ╞═══════════════════════════════ screen 2 ═══════════════════════════════════════════╡
       │ III · DECIDIR  (pre-registered rules, checked after 12:00)                          │
       │ V7 On-time × model trade-off (isolines)  │ V8 Prediction vs outcome (final check)    │
y=2350 │ Footer: data provenance, pipeline commit, rule timestamps, method notes, glossary  │
       └────────────────────────────────────────────────────────────────────────────────────┘
```
Above the fold: headline, the full ledger, all of V1, and the titles and top halves of V2 and V3. Total height about 2.6 screens.
Mantra (rule 48): the ledger and V1 give the overview → model click and time brush filter → hover gives details on demand.

## 3. Views

### V1 · Reliability collapse (Act I) → D1
- **Data:** `api_teams.csv`, rows with span_s = 900 and team_id ∈ {team_37, baseline, reference}: t0, conversion, on_time, rank, n_teams. `api_versions.csv`: per window w, the served-model conversion m_w = Σ requests·conversion / Σ requests over versions.
- **Implied oracle O_h:** the median over teams with 5 < score < 95 of b_h + 100·(c_h − b_h)/score_h, from `api_progress.csv` and the hourly `api_teams` rows. The median resists outlier teams; the brief verified that it is identical across teams.
- **Marks, top panel (purchases/100, y from 0, position on a common scale, rule 17):** team ● (ink); served model m_w ○ (ink, hollow); a vertical orange segment between them = conversion lost to fallback; baseline thin orange line, reference grey dashed, O_h grey dotted.
- **Marks, bottom panel (on-time %, y from 0, aligned x):** on-time ● with a light line; a rule at 90 % (status light); a grey ribbon = 10th–90th percentile of the top-6 teams per window (93–100 %).
- **Right margin:** Tukey box + strip of team_37's 15-min on-time values beside the top-6 box, with whiskers at 1.5·IQR labelled "1.5·IQR" (raincloud VOTD on ambiguous whiskers).
  - Five-number label, hourly practice data: 40 · 73 · 84 · 90 · 99 % (*derived* hinges of the 13 hourly values in F1). 40 % lies below the inner fence (47.5 %).
- **Why this form:** time is ordered, so dots + line, not bars (rule 42). Juxtaposed aligned panels avoid a dual axis (rule 35, P2 p54-59): share is not conversion. The orange gap is explicit difference encoding, "original + difference" (MV p25-29). The marginal box shows the distribution, not one mean (rule 46). On-time bars were rejected: 64 bars would be clutter (rule 40).
- **Title:** "Sun 01:00: the served model still converted 1.87–2.37, but on-time fell to 24–37 % and team_37 dropped from 2.23 (rank 3/42) to 1.30 (rank 21/42)".
  - Subtitle: "Gap ≈ 0.93 purchases/100 ≈ 33 conversion pts. Top-6 teams never left 93–100 %."
- **L4 annotations (max 3):** "18:49 local writer stopped: 787 late of 1,102", "Sun 00:19 fz-v9a pushed", "15:05–15:20 DNS failures, 53.7 %".
- **Interaction:** brush on x filters V4 (linked filtering, MV p69). Default = full range. Toggle 15 min / 1 h. Hover gives requests, on-time, m_w, predicted − actual.
- **Uncertainty:** identity residual (actual − predicted) as a rug under the top panel, ±0.05 band shaded. Windows with < 300 team requests are drawn hollow (tentative).
- **After the final:** the pipeline appends 10:00–12:00, shaded warm grey and labelled "FINAL".

### V2 · What sells, and "the history lied" (Act I) → D3
- **Data:** notion_github §5.3 table (16k requests: relation, purchase % per shown item, shown), plus F3 history re-buy 1.66 %.
  - Buys are reconstructed as k = round(rate·shown/100): 4, 17, 2, 19, 57, 18, 8, 1. The footnote says so.
- **Marks:** horizontal dot plot, rows sorted by rate, x = purchase % per shown item on log10; line range = 95 % Wilson; row label "n shown · ≈k buys"; hollow dot if k < 10. For "already bought": a hollow diamond at 1.66 % (history) with a grey arrow to the live dot.
- **Why this form:** rates span 57× (0.007–0.40) and the decision quantity is a *ratio* (lift), so log axis. A dot plot may drop zero (rule 33, truncation VOTD); a log bar chart would break rule 32. Bars of means + error bars rejected (Wilmer & Kerns VOTD: bar-tip limit error). Sorted rows for lookup (rule 42).
- **Title:** "The history lied: re-buys sold 1.66 % in the 60-day log but 0.007 % live (≈1 buy in 15,252 shown; 95 % CI 0.001–0.037 %), so ban them".
  - Subtitle: "Banning re-buys took ev-v1 0.69 → ev-v2 1.36 (before/after, not A/B)".
- **Honesty annotation:** "last viewed 0.40 % [0.16, 1.03] and viewed earlier 0.19 % [0.05, 0.68] rest on ≈4 and ≈2 buys: their order is NOT established. Viewed in history 0.39 % [0.24, 0.62] (≈17 buys) is."
- **Uncertainty:** the Wilson intervals are *derived* from the reconstructed k. A footnote says they treat impressions as independent; within-request clustering makes them too narrow. Default: no interaction, hover only.

### V3 · Position curve (Act I) → D3, D4
- **Data:** notion_github §5.4 (36.5k requests): buys/1,000 per slot, clicks, item-adjusted attention, and the fit e_k = 0.27 + 0.73/k.
- **Marks:** two vertically aligned panels share x = slot 1–10 (ordinal).
  - **(a)** dots + light line for buys/1,000, y from 0, 95 % exact Poisson (Garwood) line range on k = rate·36.5 (*derived*): slot 1 135 buys [3.10, 4.38], slot 2 49 [0.99, 1.77], slot 7 9 [0.11, 0.47], slot 10 11 [0.15, 0.54].
  - **(b)** index with slot 1 = 1: raw buys (grey hollow) vs item-adjusted attention (ink: 1, .65, .51, … .29) vs the fit e_k (thin line), with residuals ≤ 0.02.
- **Why this form:** small multiples with shared x and aligned axes (rule 51) avoid a dual axis for two units. The index panel's known issue (P2 p58) is covered because (a) keeps the absolute scale. (b) shows fit + residual explicitly, which is Tukey.
- **Title:** "Slots 1–3 earn 66 % of buys (3.70, 1.33, 1.15 per 1,000); slots 7–10 are a flat floor (0.25–0.34, CIs overlap), the cheap place to explore".
  - Subtitle: "Attention falls 3.5× from slot 1 to slot 10; the raw 6× includes better items on top. P(buy|click) ≈ 0.33, flat for slots 1–6."
- **Decision annotation (*derived*, upper bound if an explored item never sells):** exploring slot 10 on 30 % of requests costs ≤ 0.30·0.31/1,000 = 0.0093 purchases/100 ≈ 0.3 pts; in slot 1 it would cost ≤ 0.30·3.70/1,000 ≈ 3.9 pts (12×).
- **Uncertainty:** Garwood intervals as above; slots 7–10 are drawn hollow because k ≤ 12.

### V4 · Model comparison, paired within window (Act II) → D2, D5
- **Data:** `api_versions.csv` (model_version, t0, requests, conversion, cold_requests, cold_conversion) joined to the reference and baseline rows of `api_teams.csv` on t0.
- **Computation:**
  - Paired difference Δ_v,w = conv_v,w − conv_ref,w. The reference serves 2,700 requests at 100 % on-time in every window, so pairing removes the hour-to-hour drift (baseline 0.45–0.79, oracle 3.09–3.73).
  - Rows: versions with ≥ 2 windows of ≥ 100 requests, sorted by median Δ. Windows with 100–299 requests are drawn hollow (they are the ones the leaderboard greys out).
- **Marks:** horizontal raincloud of variant (b), Boxplot-Strip-Mean (W3 p37).
  - Rain = a strip of ticks, one per window, not jittered (Teru Teru Bōzu VOTD).
  - Box = five-number summary with 1.5·IQR whiskers, drawn only when k ≥ 5 windows.
  - Lightning = requests-weighted mean Δ. Interval by window count k: k ≥ 5 → 95 % bootstrap percentile (B = 2,000 resamples of windows), label "bootstrap over windows"; k = 3–4 → jackknife ±2·SE, "jackknife, rough"; k < 3 → none, "too few windows".
  - x = 0 is the reference line. A ruler under the axis converts to points (1 purchase/100 ≈ 35 pts).
  - Text column: k windows · n requests · median Δ.
- **Toggle [All | Cold]:** Cold shows the ratio cold_conv_v,w / cold_conv_baseline,w on a log2 axis. Cold must be compared with the cold baseline (F8), and the cold oracle is not public.
- **Why this form:** distributions over windows, not a single mean or a bar of means (rule 46; MV p101 "avoid averaging out signal"). Pairing is the textbook removal of a nuisance factor. Wilson/binomial CIs rejected: leaderboard conversion is already an expectation, so between-window spread *is* the uncertainty.
- **Title (pipeline fills k; brief numbers as default):** "fz-v9a-xcat1.0 beats the reference by ≈ +0.31 purchases/100 (2.25 vs 1.94, n=2,657; served windows 1.87–2.37); cf-rot 1.92 (n=479) is not separable from the reference".
  - Cold title: "fz-v9a cold 2.74–2.88 vs reference cold 1.86, with cold baseline 0.91–1.30".
- **Caveat badge:** "Not A/B: several emitters at once, 22.6 % multi-version requests".
- **Interaction:** click a row → that model turns blue in V1, V7 and V8 (linked highlighting, rule 50). Default selection = fz-v9a-xcat1.0. The brush from V1 restricts the windows.

### V5 · Median polish of the two "what sells" tables (Act II) → D3
Two small multiples with an identical encoding and a common scale (rule 51).
- **Computation:** Tukey median polish, alternating row and column median sweeps until every change < 0.01 (≤ 20 iterations) → overall + row effects + column effects + residuals. Log scale because effects multiply; at p ≤ 1.25 % log-odds ≈ log within 1.3 %, so plain log2 is reported (1 unit = ×2).
- **V5a.** Data: notion_github §5.5. Rows = slot band (1, 2–3, 4–6, 7–10), columns = relation (last viewed, viewed earlier, other), y = log2(buys/1,000 + 0.1). The started log handles the one 0.0 cell.
  - Result (*derived*): overall 0.58 (≈1.4/1,000); rows +2.58, +1.23, −1.32, −1.23; columns 0, +0.50, −1.03.
  - Residuals: [+0.35, 0, −0.36 / 0, +0.35, −0.51 / 0, −0.50, **+1.26** / −2.67*, 0, +0.36].
  - The "other" residuals flip sign from top to bottom: the relation lift is ×3.4–3.8 in slot 1, ×3.1–5.6 in slots 2–3 and ×0.83 in slots 4–6. This is a genuine interaction.
  - Tukey's diagnostic slope (residual vs row·col/overall, excluding the 0 cell) = 0.17 ≈ 0, so no re-expression removes it.
  - −2.67* is the 0.0 cell with unknown n: a started-log artefact. It is drawn hollow and labelled "0 buys, not evidence".
- **V5b.** Data: notion_github §5.6. Rows = session relation, columns = history share, y = log2(buys/1,000).
  - Result (*derived*): overall 0.50 (1.41/1,000); rows −0.65, 0, +0.71; columns −0.93, 0, +1.58.
  - Residuals: [+0.35, −0.10, 0 / 0, 0, **−0.76** / −0.19, 0, 0].
  - The 6.89 corner is fitted exactly by the main effects: 1.41 × 1.64 × 2.99 ≈ 6.9. There is no synergy.
- **Marks:** grid cell = residual as a horizontal bar from a centred zero, number printed; positive filled ink, negative hollow outline, |res| < 0.25 faint grey ("noise"). Row effects = dots on a left strip, column effects = dots on a top strip, overall in the corner; all on the same log2 axis, ticks ×0.5, ×1, ×2, ×4. Hover: raw, fit, residual, ratio.
- **Why this form:** median polish resists the single 0 and the extreme 12.5 that would drag means. Separating fit from residual makes "interaction" visible as a residual pattern. Colour heatmap rejected: luminance ranks 7th for magnitude (P2 p35-37), length/position 1st–3rd, and no hue is spent.
- **Titles:**
  - (a) "Relation pays only at the top: viewed items sell 3.4–3.8× 'other' in slot 1 but 0.8× in slots 4–6; the additive fit fails exactly there".
  - (b) "No synergy: session category (×1.6) and history share > 30 % (×3.0) multiply; 6.89/1,000 is their product, residual 0".
- **Uncertainty:** cell counts are absent from the source, so the badge reads EXPLORATORY and no intervals are drawn. If the `team_37.feedback` inventory lands, the pipeline recomputes from raw counts and adds Poisson intervals per cell.

### V6 · Power: what ~190 buys can and cannot see (Act II) → D6, D2
- **Computation (*derived*):** relative MDE δ = (z₀.₉₇₅ + z_power)·√(1/E_A + 1/E_B), E = expected realized purchases per arm, two-sided α = 0.05 (normal approximation to the Poisson rate test, p < 1 %). At 190 total, 50/50: 28 % (power 0.5) to 41 % (power 0.8), consistent with the brief's 26–40 %; 80/20 gives 51 %.
- **Marks:**
  - Line chart, x = total purchases (log, 50–800), y = MDE %; ink line for power 0.8, grey for 0.5.
  - Grey hatch below the 0.8 curve, labelled "invisible in the final".
  - Vertical rule at 190, labelled "final ≈ 21.6k requests".
  - Horizontal labelled effect markers: re-buy ban +97 % (0.69→1.36); reliability collapse −42 % (2.23→1.30); fz-v9a vs cf-rot +17 %; fz-v9a vs reference +16 %; online correction +2 % (2.21 vs 2.17); combo ranker live ×1.07 [0.90, 1.22] drawn as a range.
  - Point estimates from non-A/B windows are hollow.
- **Why this form:** the canonical sample-size curve shows the dependence on n, which a single p-value table hides. Intervals and line ranges follow AV p42-43.
- **Title:** "With ~190 buys the final sees only lifts ≥ 28–41 %: the re-buy ban (+97 %) or a reliability collapse (−42 %) would show, a model swap (+2–17 %) would not. Choose the model before 10:00."
- **Interaction:** toggle 50/50 (default) / 80/20. Hover reads δ at any n.
- **Note:** buys cluster by shopper, so the true MDE is larger. The confirmatory version bootstraps by user_id.

### V7 · On-time × model trade-off (Act III) → D1, D2
- **Model:** the F1 identity, verified to ±0.05 per window: conv = s·m + (1−s)·b.
- **Marks:**
  - x = on-time s (20–100 %, axis starts at 20, labelled; observed 24–100 %); y = expected team conversion (purchases/100, from 0).
  - One straight line per candidate: fz-v9a m = 2.25, cf-rot 1.92, lgbm-recent 1.48–1.60 (drawn as a band).
  - Each line has a ribbon for b ∈ [0.45, 0.79] (orange tint = baseline/fallback). At s = 100 % a line range shows m's V4 interval.
  - Observed team_37 15-min windows are grey dots; the selected model's windows are blue.
  - Horizontal references: reference 1.94 (dashed grey), "rank 3 level 2.23", "top team 2.43". Vertical: the 90 % status rule and the top-6 band 93–100 %.
- **Threshold labels (*derived*, b = 0.6):** fz-v9a needs s ≥ 81 % to beat the reference and s ≥ 99 % to repeat 2.23; each 10 pp of s is worth 0.1·(2.25 − 0.6) = 0.165 purchases/100 ≈ 6 pts.
- **Why this form:** an isoline (nomogram-like) chart answers "what on-time do we need" and "is a better model worth it" in one comparison on common position scales. The dots double as a visual check of the model (W1 p66 "assess validity of statistical model").
- **Title:** "fz-v9a at 80 % on-time scores the same as cf-rot at 100 % (1.92): each 10 pp of on-time is worth ≈ 6 conversion pts. Spend the effort on the writer, not the model."
- **Badge:** "MODEL-BASED, residual ±0.05 on N windows". The interaction is linked from V4.

### V8 · Prediction vs outcome: did the decisions hold? (Act III, filled by `build.py --final`) → D1–D6
- **Rows (fixed before 10:00):** on-time (target ≥ 93 %, top-6 floor; alarm < 90 %); conversion (predicted interval from V7 given realized s: m from V4 bootstrap, b band); cold conversion ÷ cold baseline; fallback reasons missing/late/invalid (counts, `team_37.feedback`); rank; revenue/request, tie-break only (ours €0.49–0.95 vs team_06 €1.22).
- **Marks:** grey line range = pre-registered prediction or target; ink dot = actual; ✓/✗/– glyph + text in the decision column (D#). Denominators printed: requests ≈ 21.6k, buys ≈ 190.
- **Pending state:** the intervals show and the actual reads "pending re-run". No placeholder number is ever drawn, because missing ≠ 0 (rule 26).
- **Why this form:** dot + interval on each metric's own axis, one row per question. A bullet chart (rule 45) was considered but has no interval and loses the prediction semantics. This view turns the page from exploratory to confirmatory: the prediction is fixed before the data exists.
- **Title (template):** "Final: on-time {s} % → predicted {p̂} [{lo}, {hi}], observed {c}; D1 {✓/✗}, D6 {✓/✗}".
- **Timestamp:** each rule carries its commit time. A rule committed after 10:00 CET is badged POST-HOC.

## 4. Colour system and text strategy

| Colour | Hex | One meaning, everywhere |
|---|---|---|
| Ink | `#1f1f1f` | team_37 / the focus series / positive residual fill |
| Grey | `#8c8c8c` | context: other teams, reference (dashed), oracle (dotted), intervals |
| Faded grey | `#d4d4d4` | noise (abs residual < 0.25), hatch for "undetectable", top-6 band |
| Orange | `#E69F00` | baseline = fallback = points lost (V1 gap, V7 b-band, ledger "lost") |
| Blue | `#0072B2` | the selected model, linked across V1, V4, V7, V8 (rule 50) |

- Only two hues, the Okabe-Ito blue and orange, which differ in lightness (CB p9 "safe bet"). Coblis check at build time (rule 52).
- The sign of residuals and the tentative status are coded by **fill vs hollow**, never by hue. Hollow means n small or not A/B in every view, so the convention is learned once.
- Status badges use the border, not colour: dashed = EXPLORATORY, thin solid = CHECKED, thick solid = PRE-REGISTERED, strike = POST-HOC.
- **Text, per view:** title = takeaway with real numbers (P2 p70); subtitle = how to read + denominator + method (L1/L2); ≤ 3 L4 event annotations; footer = badge, n, source, "→ D#" link to the ledger. No annotation restates what is visible (Stokes & Hearst).
- The ledger is the stand-alone text variant (Stokes & Hearst guideline 4).
- **Language:** act headings in Catalan, echoing the slogan "descobrir, interpretar i decidir". The body is in English, as are the organiser material and the data names.
- **Units:** purchases/100 to 2 decimals; points = conversion-component pts (0–100), with "×0.71 → leaderboard pts" in the ruler tooltip; expected (leaderboard) vs realized (feedback) always named.

## 5. Deliberately left out
- **Live ops monitor** (p95 latency per minute, last-shoppers feed, trending subcategories, SQL twins). This is team_36's ground. It supports firefighting, not D1–D6, and is useless to a jury after 12:00.
- **Offline ΔNDCG forest.** Our offline judges were rejected: Pearson vs leaderboard 0.43–0.51, 0.82 only without popularity. Showing them would invite trust in a judge we dropped. Only the combo ranker's history ×1.40 vs live ×1.07 appears, inside V6.
- **Price promos, new-product Spearman, subcategory pulses.** They are learning-from-stream material for the main jury presentation, not inputs to D1–D6.
- **Leaderboard race (bump chart of 42 teams).** It would be spaghetti (W1 p45). Rank appears only as text in V1 and V8.
- **Wilson CIs on expected conversion** (see §1). Also excluded: pies, gauges, colour heatmaps of means, stacked bars of fallback reasons (a table is enough), 3D, and animation.

## 6. Self-assessment and main risk

| Criterion | Assessment |
|---|---|
| 1 · Usefulness for deciding | Strong. The answer-first ledger, a threshold for every rule, and points at stake on one ruler. V7 answers D1 and D2 in one glance. V8 closes the loop after the final. Weakest spot: D5 has no score translation, because the cold oracle is not public. |
| 2 · Adequacy of charts | Strong. Position/length for every key quantity. Log scales only on dot plots. Distributions over windows. Every interval is named by method (Wilson, Garwood, bootstrap, jackknife). Residual displays replace heatmaps. The power curve is the canonical form. |
| 3 · Coherence | Strong by construction. One identity (F1) links V1, V7 and V8. One points ruler. One colour meaning each. Act = status (EXPLORATORY → CHECKED → PRE-REGISTERED). |

Known incoherences, disclosed rather than hidden: V2, V3 and V5 come from different log windows (16k, 36.5k and an unstated number of requests); the team tables lack cell counts; model attribution is contaminated by multi-version requests.

**Main risk: too academic for a decision tool.** Median polish, jackknife and an MDE curve can read as a statistics exam. Mitigation: the ledger answers first; each Tukey view ends with a plain "→ so we…" line; Act II sits below the fold as optional depth.

**Second risk: thin evidence where the jury will probe.** V5 has no counts; V4 has few windows for fz-v9a (served only from Sun 00:19); V8 depends on a re-run after 12:00. Mitigation: hollow / EXPLORATORY / "too few windows" states are first-class outputs, not error states. Honesty about weakness is itself the argument for the Tukey prize.
