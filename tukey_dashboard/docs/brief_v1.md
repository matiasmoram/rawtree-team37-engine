# Brief v1 — Tukey side-challenge dashboard (team_37, RawTree challenge)

Read with: docs/vi_theory.md (course theory, cite as "deck p.N"), docs/notion_github.md (team history, numbers, rival dashboard).

## 1. Competition
Side Challenge Tukey (Datathon FME 2026): "Un dashboard que ajudi a prendre decisions sobre el vostre repte principal".
Select relevant information, show which conclusions it brings and which decisions it grounds. Free tool.
Criteria: (1) usefulness for deciding, (2) adequacy of charts for data & comparisons, (3) coherence of indicators,
charts, conclusions with each other and with the data. One finalist per main challenge (we compete vs other RawTree
teams), then the Tukey prize among 3 finalists. Jury = FME statisticians. Theme: Tukey (EDA, boxplot), "visualitzar per
descobrir, interpretar i decidir".

Rival to beat (team_36): a live ops monitor (status light, on-time per minute, p95 latency, conversion by model with
Wilson 95 % CIs, fallback reasons, trending subcats, last shoppers feed, SQL twins). Gaps: frames no decisions, no score
translation (baseline/reference/oracle), no "what sells" evidence (position curve, relation × slot), no history-vs-live,
no cost of fallback in points, no power analysis.

## 2. Main challenge (RawTree) — rules that matter for encoding
- ~3 requests/s; per request we must write exactly 10 distinct active product IDs within 3 s of request ts.
  Late/missing/invalid -> organisers substitute the FALLBACK = baseline list (all-time best sellers in stock).
- Final round Sun 15 Nov 10:00–12:00 CET (~21.6k requests, ~190 purchases). Practice does not count.
- Points: conversion 50 (expected purchases per 100 requests, from the simulator's hidden P(buy), no luck),
  cold start 10 (same on cold requests: new user or recent_views include a product added during the event),
  reliability 10 (share answered validly & on time), jury 30. Tie-break: revenue/request.
- score_component = 100 × (team − baseline) / (oracle − baseline), clipped [0,100].
  VERIFIED from the public API: the implied oracle is identical for every team within each hour
  (e.g. 3.46 for 00:00–01:00, 3.09–3.73 across hours); baseline 0.45–0.79 by hour. So 1 conversion point
  (1 purchase/100 req) ≈ 35 score points of the conversion component.
- Leaderboard normalises the 70 automatic pts to /100 (≈71 conversion, 14 cold, 14 reliability).

## 3. Data available
A. Public leaderboard API (downloaded, tidy): data/tidy/api_teams.csv (42 teams + baseline + reference, 15-min and 1-h
   windows, Sat 10:00 -> Sun ~02:00 CET: requests, conversion, cold_conversion, on_time %, revenue/request, best model,
   rank), data/tidy/api_versions.csv (team_37 per model_version per window: requests, conversion, cold n & conv,
   revenue), data/tidy/api_progress.csv (hourly score 0–100 per team).
B. RawTree DB (SQL; inventory pending): shop.requests, shop.events (~50/s), shop.catalog_updates (stock, price, new
   products), team_37.feedback (per request: fallback reason missing/late/invalid, model_version), history tables.
C. Team docs (Notion + repo) with tables: relation × purchase rate, slot curve, viewed × slot, session-category ×
   history-share, history-vs-live contrasts, experiment registry, reliability incidents, decision log with times.

## 4. Facts already established (use as headlines; all numbers real)
F1 Reliability dominates. Identity verified per 15-min window:
   team_conv ≈ served_share × model_conv + (1 − served_share) × baseline_conv (pred vs actual within ±0.05).
   Sun 00:00–01:00: on-time 98.7 % -> team 2.23, rank 3/42 (top team 2.43). Sun 01:00–02:00: on-time 24–37 % ->
   team 1.30, rank 21/42, while the served model (fz-v9a-xcat1.0) still converted 1.87–2.37.
   Sat practice on-time per hour: 63, 90, 81, 93, 84, 91, 88, 78, 55, 87, 73, 99, 40 %. Top-6 teams are at 93–100 %.
F2 Model progress over the day (team_37 best served model per hour, purchases/100): content-session-popularity 0.72
   -> ev-v2/ev-v3 1.36–1.46 (15:00) -> lgbm-recent 1.46–1.63 -> cf-rot 1.95 (n=523) -> fz-v4…v9 2.1–2.27 (Sun 00:00).
   Reference 1.84–2.20 by hour; baseline 0.45–0.79; top team 1.13 (13h) -> 2.43 (00h).
F3 What sells (live feedback, purchase % per shown item): last viewed 0.40, viewed in history 0.39, viewed earlier in
   session 0.19, same session category 0.18, same subcategory 0.09, unrelated 0.05, unrelated on home 0.03,
   ALREADY BOUGHT 0.007 (15,252 impressions) — in the 60-day history re-buys converted 1.66 % ("the history lied").
   Banning re-buys took ev-v1 0.69 -> ev-v2 1.36.
F4 Position curve (buys per 1,000 impressions, 36.5k requests): 3.70, 1.33, 1.15, 0.65, 0.78, 0.47, 0.25, 0.34, 0.34,
   0.31 for slots 1–10; slots 1–3 = 66 % of purchases; P(buy|click) ≈ 0.33 flat across slots 1–6; item-adjusted
   attention 1, .65, .51, .42, .37, .35, .33, .32, .30, .29 (slot1/slot10 = 3.5×, raw curve says 6×).
F5 Viewed × slot (buys per 1,000): slot1 last-viewed 11.3 / viewed-earlier 12.5 / other 3.3; slots 2–3 3.4 / 6.2 / 1.1;
   slots 4–6 ≈ 0.5 for all; 7–10 0.0 / 0.8 / 0.3. -> interaction: relation matters only at the top.
F6 Session category × history share (slots 1–3, buys/1,000): 0.60 … 6.89 (session's category & >30 % history share).
F7 Power: ~190 purchases in the final; a 50/50 split only detects >26–40 % relative lifts. Offline replay ΔNDCG
   intervals mostly include 0 (cycle log). Decision rule needed before 10:00.
F8 Cold start: cold requests convert higher even for the baseline (0.91–1.30 vs 0.45–0.79) -> compare cold to cold
   baseline. fz-v9a cold 2.74–2.88 vs reference cold 1.86.
F9 Revenue tie-break: team_06 €1.22/request vs our €0.49 (last hour) / €0.95 (fz-v9a when served).

## 5. Decisions the dashboard must support (before, during and after the final)
D1 Reliability: single writer? standby on other network? what on-time is needed? -> points at stake.
D2 Which model serves the final (fz-v9a vs fz-v10-nocorr vs cf-rot vs lgbm-recent) and with which evidence/uncertainty.
D3 Slot-1/top-3 rules (what relation goes on top; ban re-buys; where exploration is cheap).
D4 Exploration budget: fz-v9a explores last slot on ~30 % of requests vs plan ≤5 % in slots 9–10.
D5 Cold-start route.
D6 Freeze timing & decision rule (power).
The dashboard is judged after the final: it must also show the final's outcome vs the decisions (re-run pipeline).

## 6. Constraints
- Deliverable: one web page (static HTML, Vega-Lite via CDN or similar), data embedded, re-buildable by a Python
  pipeline; optionally served live. Must work offline for the jury, desktop first (1440×900), also readable at 1280.
- Course rules: one color = one meaning everywhere, CVD-safe, titles = takeaways, bars from zero, show distributions not
  only means, uncertainty labelled, Shneiderman mantra, linked highlighting, few interactions with meaningful defaults,
  ≤ ~2 screens per main view, related things together (Gestalt proximity).
- Language: Catalan or Spanish or English? FME jury: Catalan/Spanish speakers; organiser material in English+Catalan.

## 7. Addendum — facts computed after the concepts were written (03:10 CET, data/dashboard_data.json)
G1 Served-model decomposition for every team (current 60-min API window, baseline 0.577, reference 1.96):
   m = (team − (1−o)·b)/o. team_06 2.36 (on-time 99.9 %), **team_37 2.33 (on-time 39.8 %, team conv 1.27, rank ~20)**,
   team_14 2.30, team_17 2.29, team_03 2.22, team_42 2.18 … => our served model is #2 of 42; our reliability is near the bottom.
   (Identity validated on our own 15-min windows: predicted vs actual team conversion within ±0.05 in 50/51 windows.)
G2 Writer outage Sun 01:00–01:40 CET (0–94 served per 10 min); recovered 01:40, 100 % served since (DB buckets10m).
G3 Oracle implied by API progress, per hour: 3.09–3.73 (median ≈3.37); identical for all teams within an hour (exact).
G4 Noise of the official expected metric: between-15-min-window SD of the same arm 0.13–0.28 vs binomial SD 0.38–0.59 for
   realised purchases; per-request variance 0.00256 vs 0.0215 => A/B on the API per-version expected metric needs ~8.4×
   fewer requests than on realised purchases (data/dashboard_data.json power).
G5 Relation × slot recomputed in SQL on all team-served impressions (12:09 → 03:07 CET), buys per 1,000:
   relation (share of slots, overall, slot-1 rate, slot-1 n): session_earlier_view (2.4 %, 2.72, 16.6, 2,944) ·
   session_last_view (2.4 %, 2.47, 9.8, 4,795) · carted_not_bought (24.3 %, 3.19, 9.4, 51,265) · new_product_other
   (4.6 %, 1.58, 6.7, 4,450) · other (49.8 %, 1.04, 4.0, 42,957) · no_session_views/home (14.4 %, 0.23, 1.0, 12,204) ·
   bought_before (2.1 %, 0.08, 0.4, 2,856). Live slot curve (team, non-new items) 6.08, 2.22, 1.46, 0.96, 0.87, 0.73, 0.48,
   0.46, 0.42, 0.40 per 1,000; slot 1 = 44 % of purchases.
   Median polish (log(per1000+0.5), rows relation, cols slot band 1/2-3/4-6/7-10): overall 0.60; slot effects +1.29,
   +0.32, −0.32, −0.44; relation effects carted +0.40, earlier view +0.16, last view 0.00, new product +0.09, other −0.18,
   home −0.95, bought_before −1.30.
G6 Segments (team-served realised purchases/100; fallback in brackets): cold 1.93 (1.10), warm 1.15 (0.39), home 0.48
   (0.27), product page 1.69 (0.73). Home + returning user weakest (0.40, n=14,902).
G7 Price changes are category-wide −18 % sales lasting 2 h (Pets 10h, Home&Garden 13h, Sports 16h & 19h, Electronics 22h,
   Sports 01h UTC); the discounted category's purchase share rises 15–50 %. Pets purchase share jumped to 16 % at 02h UTC
   with no price change (new trend). New products: 100 at 10, 14, 18, 22 UTC.
G8 Latency (team-served): p50 1.1–1.4 s, p95 1.8–2.9 s per hour, max 3.5 s; model ranking itself 10–45 ms -> latency is
   network/polling. Late answers are recorded as "missing" (2,638 rows had a submission).
Data available to the builder (single JSON): windows15 (team_37 decomposition), field_hourly (42 teams × hour incl.
served-model conv & score), arms15 (team_37 versions × 15-min windows, normalised), progress, power, practice.{buckets10m,
latency_hourly (quantiles), latency_sample (~3k raw), relation_slot (sb×slot×relation), relation_polish, segments,
model_hourly (realised per arm), writers_hourly, events_category_hourly, price_changes_hourly}, history_slots,
manual.{decisions, history_vs_live, fz_ablation}. Re-run after 12:00 adds a `final` block with the same tables.
