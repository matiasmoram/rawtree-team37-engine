# Concept A — "Decision cockpit" (team_37 · RawTree · Premi Tukey)

Sources: brief_v1.md (F1–F9, D1–D6), notion_github.md (§4–5), vi_theory.md (rules cited as `deck p.N`).
"Derived" = computed here from documented numbers (formula given); the pipeline recomputes it from data/tidy.
Unit convention used everywhere: **purchases per 100 requests** (the official conversion metric). Its score translation is
**pts = conversion-component points (0–100)**, with 1 purchase/100 ≈ 35 pts (brief §2; 30–43 across hours, from the hourly
oracle 3.09–3.73 and baseline 0.45–0.79).

## 1. Thesis and headline

The page is organised by decisions, not by data sources. Each of D1–D6 is one card with a fixed anatomy: question →
evidence view(s) → takeaway title with the real number → decision and status → points at stake → a prediction
registered before 10:00 → the outcome in the final, filled by re-running the pipeline after 12:00. The top band answers
two questions in 30 s: where do we stand (the day in one chart), and which decision is worth the most points now (a board
ranked by points at stake). At 09:45 the lead reads the board top-down and commits. Afterwards the jury reads the same page
as an audit trail: exploratory evidence → registered prediction → confirmatory outcome. That is Tukey's EDA →
confirmatory sequence, made visible.
**Headline (H1):** *"Answer every request first: the Sun 01:00 on-time collapse cost ≈ 33 pts with the same model serving;
our best model upgrade (cf-rot → fz-v9a) gained ≈ 10–12."*
Derived: (2.23 − 1.30) × 35 = 32.6; (2.25 − 1.92) × 35 = 11.6 and (2.25 − 1.95) × 35 = 10.5. These are adjacent hours, not an A/B test.

## 2. Layout at 1440×900 (2 screens; 16 px gutters; card = 260 | 860 | 260 px columns)

```
SCREEN 1 (0–900) ─────────────────────────────────────────────────────────────────────────────────────────
│H1 headline (22px) ·  as-of: Sun 02:00 practice data · [Practice | Final] toggle · inline legend chips   │ 64
│KPI text: last clean hour Sun 00–01: 2.23/100 · rank 3/42 · on-time 98.7 %  |  Sun 01–02: 1.30 · 21/42 │
├──────────────────────────────────────────────────────┬──────────────────────────────────────────────────┤
│ V0 THE DAY IN ONE CHART (840×330)                    │ V1 DECISION BOARD (560×330)    pts at stake 0–35 │
│ purchases/100 · Sat 10:00 → Sun 02:00 · hourly       │ D1 Reliability     ●══════════33  ○ PENDING      │
│  oracle band ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ 3.1–3.7   │ D2 Model           ├─┼──┼─────27  ◐ REVISIT      │
│  reference - - - - - - - - - - - - - - - 1.84–2.20   │ D3 Top-3 rules     ●═════════23   ● TAKEN banked │
│  served model ──────╱‾‾‾‾‾‾╲___╱‾‾‾‾‾‾‾‾‾‾╲‾‾        │ D4 Exploration     ●1.5            ○ PENDING      │
│  team scored  ─────╱ ▒▒gap▒▒ = lost to fallback      │ D5 Cold start      ◌ no estimate   ● TAKEN        │
│  baseline ·········································  │ D6 Freeze & rule   guards D2 ↑     ○ PENDING      │
│  L4 notes: 14:50 engine · 15:50 re-buy ban · 18:49   │ each row: one-line decision + "→ card"           │
│  writer stopped · 00:19 fz-v9a · 01:00 collapse      │                                                  │ 330
├────────────┬─────────────────────────────────────────┴──────────────────────────┬───────────────────────┤
│ D1 card    │ V2 RELIABILITY: on-time × conversion, 15-min windows (860×420)      │ FINAL OUTCOME         │
│ question   │  marginal top: box+strip of practice on-time (n=13 h) vs top-6      │ registered 09:45:     │
│ status chip│  scatter: team_37 windows, loss segments, resistant line, identity  │ s≥98 % → conv ≈ 2.22  │
│ decision   │  orange rules: 90 % light, 98 % target                              │ final: ___ ✓/✗/~      │ 490
SCREEN 2 (900–1800) ──────────────────────────────────────────────────────────────────────────────────────
│ D2 card    │ V3 MODEL CHOICE: strip + jackknife interval · facets All | Cold     │ outcome slot          │ 280
│ D3 card    │ V4 what sells (280) │ V5 where it sells (320) │ V6 median polish (260) │ outcome slot          │ 320
│ D4 half-card (text, points to V5 slot 10)    │ D5 half-card (text, points to V3 Cold facet)             │ 110
│ D6 card    │ V7 DETECTABILITY RULER: observed gaps vs MDE band 26–40 %           │ outcome slot          │ 160
│ footer: sources, pipeline commit, "derived" formulas, glossary CA/ES                                    │ 30
```

## 3. Views (8)

**V0 · The day in one chart** — supports all decisions (context); overview first (`W2 p37-40`).
- Data: `api_teams.csv` rows with span_s=3600: team_37, baseline, reference `conversion`. Top team = max `conversion` per `t0`.
  Served model = `api_versions.csv` aggregated hourly by request-weighted mean, best version per hour with ≥ 300 requests.
  Hours with 100–299 requests are drawn hollow; this mirrors the leaderboard greying (notion §1.2). Oracle = implied from
  `api_progress.csv`: b + 100·(team − b)/score, identical across teams (brief §2).
- Marks/channels: x = time (hourly, uniform), y = purchases/100 from 0 to 3.8. Lines: team scored (thick blue), served model
  (thin sky blue), reference (black dashed), baseline (grey dotted), top team (thin dark grey). Oracle = light grey band.
  The area between served model and team scored is filled vermillion with a hatch = points lost to fallback. This is
  explicit difference encoding (`MV p25-29`). Gaps before 13:02 stay gaps, not zeros (anti-pattern 26, `AV p69`).
- Why: a line fits ordered time (`W3 p6, p90`); 5 lines is far under "a dozen" (`MV p21`); y from 0 so the climb is not
  exaggerated (`P2 p62-65`). One focus hue over grey context (`P1 p61-64`). L4 event annotations (Stokes & Hearst VOTD; `W1 p53`).
- Title: *"Our models climbed from 0.72 to 2.27 purchases/100 and passed the reference (1.84–2.20); the largest drop
  (Sun 01:00, 2.23 → 1.30) is a reliability gap: the served model still converted 1.87–2.37."*
- Interaction: brush an hour range → linked highlight (black outline) of the same windows in V2 and V3 (`MV p64-69`).
  Default: no brush; Sun 00:00 and 01:00 annotated. Uncertainty: hollow = small-n hour; no fake bands.

**V1 · Decision board** — supports choosing which decision to work on now; the page's focal point (`P1 p95`).
- Data: `decisions.csv` built by the pipeline. Columns: id, question, at_stake_lo, at_stake_hi, basis_formula, status,
  decision, prediction, outcome. Values (all derived, in pts):
  D1 9–33. Low: practice median on-time 84 % → 99 %: 0.15 × (2.25 − 0.59) × 35 = 8.7. High: observed 01:00 drop 32.6.
  This is a lower bound, because it excludes the reliability component itself.
  D2 1–27. Ticks per alternative: nocorr 1 (ablation 2.21 vs 2.17), cf-rot 10–12, lgbm-recent 22–27 (2.25 − 1.48…1.63).
  D3 23 banked: re-buy ban ev-v1 0.69 → ev-v2 1.36. D4 ≤ 0.8–1.5 (see V5). D5: no estimate (hollow ◌). D6: guards D2.
- Marks: one row per decision, sorted by points at stake. The D1–D6 order of the brief already matches this ranking.
  x = pts 0–35 on a common scale (`P2 p35`). Point estimate = dot; range = line range (`AV p42`). Missing = hollow ◌
  "no estimate", never 0. Status = chip with glyph + word (● TAKEN, ○ PENDING, ◐ REVISIT AFTER FINAL).
- Why: this is a bullet-like, length/position KPI instead of gauges or lights (`W3 p19-21`, anti-pattern 16). Ordered by
  value (`W3 p5-6`). The rival shows a status light; we show the points behind each choice (brief §1).
- Title: *"Reliability (D1) is worth up to 33 pts and is still pending; exploration (D4) is worth ≤ 1.5 pts — do not touch
  code for it at 09:45."*
- Interaction: click a row → scroll to its card (linked navigation, `MV p64`). Default: D1 row emphasised (the largest
  pending stake).

**V2 · Reliability: on-time × conversion** (D1).
- Data: `api_teams.csv` span_s=900, team_37 `on_time`, `conversion`. Served-model value per window comes from
  `api_versions.csv` (request-weighted). Context: other 41 teams at span_s=3600 (~650 grey dots, opacity 0.3, static layer).
  Marginal: hourly on-time of team_37 in Sat practice (n = 13: 63, 90, 81, 93, 84, 91, 88, 78, 55, 87, 73, 99, 40 %), plus
  a top-6 strip (93–100 %).
- Marks: x = on-time % from 0 to 100; y = purchases/100 from 0. Team windows: filled blue = fz era (Sun 00–02), hollow blue
  = earlier eras (fill, not hue: `CB p11-14`). In the fz era, a sky-blue tick marks the served-model value and a vermillion
  segment joins it to the scored point (loss). Lines: identity `s·2.25 + (1−s)·0.59` (thin black, brief F1) and the Tukey
  resistant line on fz-era windows (dashed blue). Orange verticals: 90 % (status light) and 98 % (target).
  Top marginal: Tukey box (hinges 73 | median 84 | 90; fences at 1.5 H-spread = 47.5 / 115.5) with a strip. The 40 % hour
  is labelled "outside" and the adjacent value is 55.
- Why: this is a relationship task, so a scatter fits (`W3 p71`). Superposition kept at 2 data layers + reference lines
  (`MV p17`). Box + strip, not a box alone (`W3 p29`, raincloud VOTD).
- Title: *"Same model, rank 3 → 21: on-time fell from 98.7 % to 24–37 % and conversion from 2.23 to 1.30. Each 10 pp of
  on-time ≈ 0.17/100 ≈ 6 pts."* (Derived: 0.10 × (2.25 − 0.59) = 0.166.) Subtitle: "our median practice hour 84 %; top-6 teams 93–100 %".
- Interaction: hover → window, model_version, n requests. Linked to V0 brush. Uncertainty: the gap between the resistant
  line and the identity line is shown, not hidden. Agreement within ±0.05 is stated (brief F1).

**V3 · Model choice: rain + lightning, small multiples All | Cold** (D2, D5).
- Data: `api_versions.csv`, one point per (model_version, 15-min window): `conversion` and `cold_conversion`, with
  `requests` and `cold_requests` as denominators. Rows: fz-v9a-xcat1.0, fz-v10-nocorr (if present in the csv), cf-rot,
  lgbm-recent. Bands: baseline (0.45–0.79; cold 0.91–1.30) and reference (1.84–2.20; cold 1.86) from `api_teams.csv`.
- Marks: y = model (nominal → spatial region, `P2 p35`), x = purchases/100 from 0 to 3.8, with the same x in both facets
  (`MV p45-47`). Rain = window values as a strip with hollow circles, no jitter (Correll VOTD). Lightning = request-weighted
  mean ± jackknife 95 % interval, leaving one window out. A box is drawn only if k ≥ 5 windows. Right text column:
  "n = 2,657 req · k windows". A thin secondary scale under the All facet maps purchases/100 to pts for the Sun 00–01 anchors.
  It is a linear relabel of the same axis, not a second quantity (`P2 p54-59`).
- Why: the task is to compare a few distributions on a common position scale. This avoids mean bars (Wilmer & Kerns VOTD).
  Cold is faceted with its own baseline, because cold converts higher even for the baseline (brief F8).
- Title: *"fz-v9a converts 2.25/100 (n = 2,657), above the reference band 1.84–2.20 and +0.30–0.33 over cf-rot; on cold
  traffic 2.74–2.88 vs reference 1.86 — serve it, no separate cold route."* Footnote: the windows differ, so this is not an
  A/B test (notion §5.1). Tie-break context in the card text: €0.95/request when fz-v9a serves vs team_06 €1.22.
- Interaction: hover a window → details; linked to V0 brush. Default: all candidates shown, sorted by median.

**V4 · What sells: purchase % by relation of the shown item** (D3).
- Data: notion §5.3 / brief F3. There are 8 relations with purchase % and impressions (994 … 63,353). Purchases are derived
  as % × shown, for example last viewed ≈ 4 and viewed-in-history ≈ 17.
- Marks: dot plot sorted by value (`W3 p16`). x = purchase % from 0 to 0.45, with Wilson 95 % line ranges (labelled).
  Denominators are right-aligned. "Already bought" 0.007 % has an off-scale hollow marker "▶ history said 1.66 % (×237)".
  The axis is not stretched to fit it (`P2 p62-65`).
- Why: positions beat bars when intervals are shown; the intervals expose that the top two rows rest on 4 and 17 purchases.
- Title: *"Items the shopper already viewed sell 8× more than unrelated ones (0.39–0.40 % vs 0.05 %); already-bought items
  sell 0.007 % live although history said 1.66 % → keep the re-buy ban (+0.67/100 banked)."*
- Interaction: none (static evidence). Uncertainty: Wilson intervals.

**V5 · Where it sells: slot × relation** (D3, D4).
- Data: F4 per-slot buys/1,000 (36.5k requests) and F5 viewed × slot table (notion §5.5).
- Marks: x = slot 1–10 (equal spacing). y = buys per 1,000 impressions, from 0 to 13. Layer 1: the raw per-slot curve in
  grey, with Poisson 95 % line ranges (≈ 135 buys in slot 1, ≈ 11 in slot 10). Layer 2: the F5 relations drawn as step
  segments across their true slot spans (1 | 2–3 | 4–6 | 7–10). Relations are told apart by lightness and dash plus direct
  labels, not hue: viewed earlier = black, last viewed = dark grey, other = light grey dashed. Groups of unequal width are
  never drawn as equal ticks (`W1 p53-54`, `W2 p68`). F5 has no denominators, so its segments carry the text "n not in
  source" (rule 7, `W2 p3`).
- Annotations: "slots 1–3 = 66 % of purchases"; "slot 10 = 0.31/1,000 = 3.3 % of purchases → exploring it on 30 % of
  requests costs ≤ 0.8 pts (raw) – 1.5 pts (item-adjusted attention 0.285/4.53 = 6.3 %)". Derived:
  0.30 × 0.033 × 2.25 × 35 = 0.78. Subtitle: "after item adjustment slot 1 / slot 10 = 3.5×, not the raw 6×".
- Title: *"Relation matters only at the top: in slot 1 a viewed item sells 11.3–12.5 per 1,000 vs 3.3 for others; from slot
  4 on everything sells ≈ 0.5 → viewed items in slots 1–3, exploration only in 7–10."*

**V6 · Session × history share, median-polished** (D3: what goes on top).
- Data: F6 3×3 table (slots 1–3, buys/1,000; notion §5.6).
- Marks: heatmap of observed values (single-hue luminance ramp, ordered colormap `W3 p73`, value printed in each cell).
  Marginal bars show the row and column effects of a median polish on log rates. The residual is printed as ×factor per
  cell; the 6.89 cell is outlined.
- Result (computed): grand 1.41. Rows ×0.64 / ×1.00 / ×1.64 (not / partly / session category). Columns ×0.52 / ×1.00 /
  ×2.98 (<10 / 10–30 / >30 % share). All residuals are within ×0.59–×1.27, and the 6.89 cell has residual ×1.00 =
  1.41 × 1.64 × 2.98. On the raw scale the same polish leaves +2.74 in that cell; re-expression removes the apparent interaction.
- Why: a two-way table of rates is exactly what median polish is for. It is resistant to the one extreme cell.
- Title: *"History share (×5.7 from <10 % to >30 %) outweighs session match (×2.6); the 6.89 peak is the product of both, not
  an interaction → rank top slots by session factor × history factor."*

**V7 · Detectability ruler** (D6, guards D2).
- Data: F7 documented MDE band 26–40 % relative lift for a 50/50 split with ~190 purchases (Notion Estrategias). Candidate
  gaps (derived from V3 values): fz-v9a vs nocorr +2 % (2.21/2.17), vs cf-rot +15–17 %, vs lgbm-recent +38–52 %. The
  pipeline replaces these ranges with jackknife intervals of the ratio when k ≥ 3.
- Marks: x = relative lift %, 0–60; orange band = MDE; one row per comparison with a dot or line range. Card text adds
  the offline evidence: ΔNDCG intervals mostly include 0. Example: lgbm-cart-v2 −0.0445 [−0.1065, +0.0152], combo live
  holdout ×1.07 [0.90, 1.22].
- Title: *"With ~190 purchases the final can only detect gaps above 26–40 %; fz-v9a vs cf-rot (+15–17 %) is invisible →
  no split, freeze one model."*

## 4. Color and text system

| Meaning (only this, everywhere) | Color | Redundant cue |
|---|---|---|
| team_37 scored / our windows | blue `#0072B2` | thick line, filled dot |
| team_37 served model (before fallback) | sky blue `#56B4E9` | thin line, tick |
| Points lost to fallback / outage | vermillion `#D55E00` | 45° hatch, "lost" label |
| Reference (organisers) | near-black `#1F1F1F` | dashed |
| Baseline (= fallback list, score 0) | grey `#8C8C8C` | dotted |
| Oracle (score 100) | light grey band `#D4D4D4` | band label |
| Other teams / context | `#C8C8C8`, opacity 0.3; top team `#595959` thin | no label unless hovered |
| Thresholds and rules (90 % light, 98 % target, MDE) | orange `#E69F00` | thin rule plus text label |
| Linked selection | black 2 px outline; the rest fades to 30 % | — |
| Status (cards and board only; never in charts) | TAKEN `#009E73` fill · PENDING `#F0E442` fill · REVISIT white + outline | glyph ● ○ ◐ + word |
| Verdict in the outcome slot | same chips | ✓ confirmed · ✗ refuted · ~ inconclusive |

- Okabe-Ito subset. Reddish purple is unused because it collides with blue (`CB p8`). Orange and vermillion differ in
  lightness and never share a mark type: orange is thin rules, vermillion is a hatched fill. Every hue pair also has a
  shape, dash or label cue (`CB p11-14`). The build is checked with Coblis (`CB p3`). Relations and eras are told apart by
  lightness and fill, not by new hues (prior-project rule, vi_theory §5c).
- Text: every title is the takeaway with its number (`P2 p70`, `W2 p5`). The subtitle says how to read the chart plus its
  denominator ("n = …, window …"). L4 annotations mark causes (re-buy ban, writer stopped). Redundant L1 labels are not
  added (Stokes & Hearst). Every derived number shows its formula in a tooltip or footnote, which counters suspicion of bias.
  Font: Source Sans 3 with tabular figures. Sizes: H1 22 px, card title 15 px semibold, subtitle 12 px, annotations 11 px.
- Language: English (organiser language) with a one-line Catalan subtitle under H1 and a CA/ES glossary in the footer.

## 5. Tukey touches (only where the data fit)

- **Five-number summary + boxplot with fences**: V2 marginal. Practice on-time 40 | 73 | 84 | 90 | 99. The 40 % hour is
  flagged outside (inner fence 47.5). Always drawn with its strip.
- **Strip + box ("raincloud b")**: V3. The box appears only if k ≥ 5 windows; otherwise strip + interval.
- **Jackknife**: V3 intervals (leave one 15-min window out), reused for the lift ratios in V7. This fits the "no luck"
  metric, where the uncertainty comes from window-to-window traffic mix, not from coin flips.
- **Resistant line** (median of thirds): V2, fz-era windows. Its slope is checked against the identity slope m − b ≈ 1.66.
  The outage windows are leverage points that a least-squares line would over-weight.
- **Median polish + re-expression (log)**: V6. The log scale turns the apparent interaction into two main effects.
- **EDA → confirmatory**: the outcome column. Predictions are registered at 09:45 and checked against the final. V7 shows
  which exploratory gaps the final can confirm.
- **Letter-value plot**: optional swap for the V2 marginal, only if per-request latency (team_37.feedback, 21.6k requests,
  heavy tail: p99 2.8 s, worst p95 13.5 s) is loaded. Large-n tails versus the 3 s deadline are its exact use case.
- Not used: **Tukey HSD** (no replicated, balanced groups; windows overlap and several emitters ran at once, notion §5.1).
  **Rootograms** (no count-distribution model is being fitted).

## 6. Deliberately left out

- Live ops panels (latency per minute, last-shoppers feed, trending subcategories, SQL twins): team_36 already does this. It
  answers "is it running", not "what do we choose", and it is useless to the jury after 12:00.
- A rank race or 42-team spaghetti chart (anti-pattern 10): other teams appear only as grey context.
- Revenue view: tie-break only, so it is a sentence in D2. Status lights, gauges, pies (`W3 p19-21, p39-45`).
- The full 18-version registry: only the D2 candidates are shown (expressiveness, `W1 p20`).
- Popularity curve, price promotions, new-product priors, subcategory pulses (notion §5.7–5.8): real findings, but no
  pending decision depends on them. They can go in a jury appendix.
- A score-over-time chart from `api_progress.csv`: it is redundant with V0 and adds hourly clipping artefacts.

## 7. Self-assessment

1. **Usefulness for deciding (strong).** Each view has one decision, a points-at-stake number and a registered prediction.
   The 09:45 path takes three reads: board → D1 → D6. The board also says what not to spend time on (D4 ≤ 1.5 pts).
2. **Adequacy (strong).** Position on common scales, bars and axes from 0, unequal slot groups drawn honestly, and labelled
   uncertainty (Wilson, Poisson, jackknife). Missing data is shown as missing. Distributions are shown, not means.
   Risk: V2 is the densest view, so the default caps it at 2 data layers + rules.
3. **Coherence (strong by construction).** One unit (purchases/100 ↔ pts), one color = one meaning, the same numbers in
   the H1, board, titles and cards (the pipeline generates all of them from one table), and a final-vs-prediction verdict
   per decision.
- **Main risk:** the points at stake are derived from non-A/B windows (adjacent hours, overlapping emitters). The board can
  look more precise than the evidence. Mitigation: ranges only, a formula tooltip on every number, and a "derived" tag.
  Second risk: the final's per-window data may only be available after 12:00, so the outcome slots stay empty until the
  re-run. A placeholder text says exactly that, never an estimate.
