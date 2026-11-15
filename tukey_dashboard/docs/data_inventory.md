# Data inventory · team_37 · RawTree challenge (for the Tukey decision dashboard)

Built 2026-11-15 ~01:40–01:55 CET (00:40–00:55 UTC), resumed ~03:00 CET for relation×slot and price data (4 more queries, 30 total). The public API standings are already in `C:\Users\matia\Documents\DATATHON\tukey_dashboard\data\raw\api` (hourly + 15-min per-model); §4.1–4.2/4.9 only summarise them. READ-ONLY: 26 light SQL queries in the first pass (6 failed on syntax, no writes), 17 GETs to the public leaderboard API, local file reads. **All DB/API timestamps are UTC; CET = UTC+1.** Final = 09:00–11:00 UTC.

Raw query outputs (JSON, reusable by the pipeline) are in
`C:\Users\matia\AppData\Local\Temp\claude\6f885107d0f7416d\ff291749-32fa-4b27-97bb-183b65d18933\scratchpad\inv\out\` (one file per query name below; `lb_*.json` = public leaderboard pulls). Query helper: `...\scratchpad\inv\q.py` (run from repo root with the repo venv; it rejects non-SELECT statements and logs to `inv\qlog.jsonl`).

---

## 1. Rules & scoring

No official statement file exists locally. The rules are restated in `helm_harness/brief.md` (most complete), `ESTRATEGIAS.md`, `rawtree_team37_engine/README.md` and `fz_standby/README.md`. They match the API fields.

| Item | Definition (source) |
|---|---|
| Task | 10 distinct, active, in-stock product IDs per request in `shop.requests`, written to `team_37.submissions` within the deadline. Late, missing or invalid answers get the **fallback** (all-time best sellers in stock). One out-of-stock item invalidates the whole list. (brief.md) |
| Deadline | Stated as **3 s** from request `ts`. Observed: `latency_ms` up to 3499 ms is still `served_by='team'` (1,116 team rows > 3000 ms). The effective cutoff looks like ~3.5 s. This is an inference. |
| Conversion (50 pts) | Expected purchases per 100 requests: the simulator's purchase **probability** for the shown list, not the realised coin flip. Normalised as `100 × (team − baseline) / (oracle − baseline)`. (brief.md) |
| Cold start (10 pts) | Same metric, only on cold requests: `is_new_user` OR `recent_views` contains a product added during the event (`catalog_updates.change='new_product'`). (brief.md; same as `engine/eval/replay.py:94`) |
| Reliability (10 pts) | Share of valid on-time answers = API `on_time` (%). |
| Tie-break | Expected revenue per request (`revenue_per_request`). |
| Jury (30 pts) | Method, offline validation, learning from the stream, use of the DB, communication. |
| Final | Sun 15 Nov 10:00–12:00 CET. API: `final_start=1794733200` (09:00 UTC), `final_end=1794740400` (11:00 UTC). About 21,600 requests (3/s). New shoppers, new products, new trends, price changes, stock-outs. "Bought items lose appeal." |
| Practice | `practice_start=1794646800` (2026-11-14 09:00 UTC). Requests have been continuous since then at exactly 10,800/h. |

**Public leaderboard API (no auth):** `GET https://datathon.rawtree.dev/api/state?by=model[&from=<unix>&to=<unix>]`.
- Default window = the last 60 min, refreshed every 60 s. A custom window has `step=300`, min 900 s, max 10,800 s, earliest = practice start.
- Fields: `mode`, `updated_at`, `window`, `custom`, `hidden` (true), `min_requests` (300), `teams[]`, `baseline`, `reference`, `progress{team_id: [[hour_ts, value]...]}`, `limits`.
- Each team has `{team_id, requests, conversion, cold_conversion, on_time, revenue_per_request, model_version, best, more_versions, versions[]}`.
- Each version has `{model_version, requests, conversion, cold_requests, cold_conversion, revenue_per_request, first, last}`.
- `conversion` values are expected purchases per 100 (noise-free simulator probability). This is the cleanest arm comparison available.
- **`progress` (inferred):** per team and per UTC hour, `progress = 100·(conv − baseline)/(X − baseline)`. The ratio progress/normalised-vs-reference is identical across 4 teams to 4 decimals. This means X is a hidden "oracle" conversion: **≈3.19/100 for 22h and ≈3.46/100 for 23h**. So `progress` is most likely the 0–100 conversion score; ×0.5 gives the 50-pt component. This is an inference: confirm before stating it as fact. Reference ≈2.0, baseline ≈0.55–0.79.

Table names the organisers provide: `shop.catalog`, `shop.catalog_updates`, `shop.events`, `shop.history_events`, `shop.history_sessions`, `shop.requests`, `team_37.feedback`, `team_37.submissions`, `team_37.scratch`. Nothing else exists: `system.tables` lists only these 9 non-system tables.

---

## 2. DB tables (RawTree = ClickHouse 26.8, SQL over HTTP)

Access notes:
- `POST {API}/v1/query {"sql": ...}` with a bearer key from `.env`. Client: `engine/rt.py`.
- `SHOW ...` is **not supported**. Use `system.tables` and `system.columns`.
- Every table has one physical column `__raw_data JSON`. Read fields as `field::Type` (e.g. `ts::DateTime64(3)`, `context.page::String`).
- `recent_views` is `Array(JSON)`. Parse it with `JSONExtract(toJSONString(__raw_data), 'recent_views', 'Array(Tuple(product_id String, ts String))')`.
- 30 s limit per query. Add `SETTINGS max_execution_time = 25`.
- All counts below are as of 00:40–00:52 UTC. Requests and events are still flowing.

| Table | Rows | Time range (UTC) | Fields (JSON paths : type) | Measures |
|---|---|---|---|---|
| `shop.requests` | 169,263 | 2026-11-14 09:00:00 → 2026-11-15 00:40 (live) | `request_id:String, ts:DateTime64, user_id:String, is_new_user:Bool, context.device(web/ios/android), context.region(Spanish regions), context.page(home/product/category), recent_views:Array({product_id, ts})` | Live demand. Exactly 10,800/h (3/s). New users ≈30%, cold 30→40% (rises as new products accumulate), home ≈20%. Home has 0 views. |
| `team_37.feedback` | 135,153 (+1 `__init__` row) | 2026-11-14 12:09:24 → live | `request_id, ts, served_by('team'/'fallback'), fallback_reason(''/'missing'/'invalid'), latency_ms:Int64 (absent when missing), shown:Array(String)[10], clicked:String (product id or ''), purchased:String, revenue_eur:Float64` | One row per request after team start. The simulator outcome is **realised**: at most 1 click and 1 purchase per request, and the purchase is always the clicked item. `ts` ≈ request ts + 4.23 s (written after the deadline). `'late'` never appears: **2,638 'missing' rows had a submission (late arrivals are labelled missing)**. 26,604 missing rows had no submission. |
| `team_37.submissions` | 131,846 | **no ts field** | `request_id, items:Array(String), model_version:String` | Our writes. 108,577 distinct requests, **70 distinct model_versions**. **Arm attribution:** join to feedback on `request_id` AND `items = shown` (exact list). Requests with >1 submission (many emitters) are common 14–21 UTC (up to 5,377/h with multiple). |
| `team_37.scratch` | 1 | — | `ckpt_id, key, kind, n, payload, saved_at, schema, seq, wm, writer` | One round-trip test checkpoint. Free table for our own use. |
| `shop.events` | 3,758,390 | 2026-11-14 09:00 → live | `ts, user_id, session_id, product_id, event_type(view/add_to_cart/purchase), price_eur, device, region` | Organic stream. ≈236k/h, steady: views ≈207k, carts ≈21.8k, purchases ≈10.9k per hour. |
| `shop.catalog_updates` | 7,350 | 2026-11-14 09:00 → live | full product row + `change(new_product/price_change/out_of_stock/back_in_stock)`, `ts` | Per hour: 36 out_of_stock + 36 back_in_stock. Price changes 500–665 in most hours. **new_product: 100 each at 10, 14, 18, 22 UTC (400 total)**. |
| `shop.catalog` | 5,000 | created 2024-05-29 → 2026-09-15 | `product_id, category(10), subcategory(89), brand(8/cat), price_eur, description, created_at, is_active` | Static snapshot, all active. Median price per category: €18.99 (Sports) to €41.99 (Fashion). Range €1.99–643.99. |
| `shop.history_sessions` | 2,000,000 | 2026-09-15 07:00 → 2026-11-14 07:00 | `request_id, ts, user_id, context.*, recent_views, shown[10], propensity[10], clicked, purchased, revenue_eur` | Old carousel log. 74,915 clicks (3.75%), 28,053 purchases (1.40/100), purchase/click 37.4%, revenue €982k. Includes per-slot Plackett-Luce propensities, so IPS is possible. |
| `shop.history_events` | 11,996,560 | 2026-09-15 07:00 → 2026-11-14 07:08 | same as events | 60-day organic events: 10.35M views (59.8k users), 1.09M carts, 548k purchases (51.8k users). |

Specific answers:
- **Feedback attribution per served request:** `feedback.clicked/purchased` hold product ids, so the slot is `indexOf(shown, clicked)`. Arm = `submissions.model_version` where `items = feedback.shown`. Repo pattern: `scripts/monitor.py FEEDBACK_SQL`, `scripts/check_emitters.py`, `scripts/live_attribution.py`.
- **Per-team leaderboard / score:** NOT in the DB. Only the public API above. Local history: `logs/leaderboard*.csv`, `fresh_strategy/leaderboard_snapshots/`.
- **served_by / arm:** `served_by` + `fallback_reason` are in feedback. The arm is only in submissions (`model_version`), or per arm in the API `versions[]`.
- **Latency / deadline:** `feedback.latency_ms` for team and invalid rows only. Team p50 1,245 ms, p99 3,014, max 3,499. Invalid rows (37) have 2,291–3,484 ms.
- **Cold-start flags:** `requests.is_new_user`. New products come from `catalog_updates.change='new_product'`. There is no explicit cold flag: compute it.

---

## 3. Local files

Paths are relative to `C:\Users\matia\Documents\DATATHON\` (engine = `rawtree_team37_engine\`).

### Engine logs (`engine\logs\`)

| File | Schema | Rows / range (UTC) | What it measures |
|---|---|---|---|
| `leaderboard.csv` | fetched_at, mode, updated_at, window_start/end, team_id, requests, conversion, cold_conversion, on_time, revenue_per_request, model_version, baseline_*, reference_*, rank, n_teams, progress_latest | 63 rows, 13:42→18:58 | Our rolling-60-min official numbers + rank (written by `scripts/monitor.py`). |
| `leaderboard_models.csv` | fetched_at, updated_at, window, model_version, requests, conversion, cold_requests, cold_conversion, revenue_per_request, baseline/reference_conversion, lift_vs_baseline_pct, normalized_score_vs_reference | 429 rows, 19 versions, 14:10→18:58 | Per-arm official expected conversion (rolling windows overlap). |
| `feedback.csv` | fetched_at, minutes, model_version, requests, served_team, late, invalid, missing, clicks, purchases, revenue, p50_ms, p95_ms, conv_per100, conv_lo/hi (Wilson), ctr_per100, revenue_per_request, on_time_share | 651 rows (mostly 60-min windows), 13:42→18:58 | Realised per-arm feedback snapshots. |
| `exposure_metadata.jsonl` | request_id, ts, items, model_version, metadata{model_id, base_probabilities[10], subcategories[10], propensity_valid, online_calibration_built_at}, proposal_only | 10,137 rows, all `t37-lgbm-recent`, 15:39→17:49 | Model-predicted P(buy) per slot. Usable for calibration (expected vs observed). |
| `iteration_20261114T{1523,1645,1702,1717}.json` | iteration{champion, challengers, deadline_ms,...}, verdicts{all, cold_request}, replay_report{...} | 4 offline gate runs | Paired ΔNDCG verdicts per challenger (see cycle_log). |
| `policy_replay_20261114T1523.json`, `recent_evaluation_20261114T1523.json` | replay/eval reports | 15:00–15:23 / 13:45–15:23 | Offline diagnostics (section 4). |
| `competitor_audit.json`, `competitor_canary_initial.json` | same-window team_06 vs team_37 comparisons, emitter counts, feedback diagnostics (relation, slot, relation×slot band, segments) | as_of 15:33 / 15:44 | Same-window competitor comparison. |
| `emitter_audit*.json`, `emitters_*.json` | {team, as_of, windows{5,15:{counts, per-version}}} | 15:26→19:04 | Multi-writer overlap audits. |
| `window_audit_{1794668700,1794679500}.{json,csv}` | full API state + 8 windows (last 15/30/60/120/180 min, previous 3×15) | at 16:05 and 19:05 | Per-arm conversion by window. |
| `runner_health*.json` | host, pid, shard, arms, stats{answered, pushed, push_fail, late, errors} | point in time | Writer health. |
| `eval_results.jsonl` | timestamp, T, window, evaluator(logged/live/organic/organic_reshow), policy, segment, metric, value, ci_low/high, n | 432 rows, 13:58–14:02 | Early offline evaluation (IPS/SNIPS slot1, recall@10, θ-hit). Mostly superseded. |
| `live.log`, `*_stderr.log` | text | to 19:45 | Writer logs (timeouts, DNS errors). |

### Engine cache / models

- `cache\live_ds_v{1,3_recent,4_cart}_*.pkl` contain dicts `{df, meta}`. `df` = one row per shown item (≈10 per request) with 41–45 PIT features, plus slot, click, purchase, served_by, fallback_reason, model_version, request_id, ts, user_id, pid. v4 adds `item_in_cart, cart_rank, cart_age_hours, log_user_cart_n, subcategory, cold_request, device, region`.

  | File | Window | Requests | Clicks | Purchases |
  |---|---|---|---|---|
  | v1 | 12:10–14:25 | 24,342 | 636 | 198 |
  | v3 | 13:45–15:23 | 17,640 | 660 | 195 |
  | v4 | 15:30–18:02 | 27,331 | 1,047 | 335 |

  These are the best source for **relation × slot** tables and slot curves with features. They contain user_ids: aggregate them before display.
- `cache\policy_replay_v1_*.pkl` (5 files) contain dicts `{rows[list of {request_id, shown, clicked, purchased,...}], buys{user: (ts list, pid list)}, updates[catalog updates], request_audit, feedback_audit}`. Windows run 13:45–17:17; 2.8k–16.5k requests each. They are inputs for offline replay.
- `cache\snapshot_*.pkl` (8 files, 128–162 MB): PIT feature snapshots. Not loaded.
- Other cache files:
  - `cache\online_calibration.json`: expected 22.88 vs observed 15 purchases over 1,232 requests (2 h to 15:39).
  - `contextual.json`: device/region priors.
  - `recent_covis*.json`: 6 h co-visitation.
  - `new_product_neighbors.json`: top-20 content neighbours per new product.
  - `embeddings.npz`: qwen3-embedding, 5,200 × 4096.
  - `lgbm_*.json` and `models\lgbm_cart_v2_*.json`: training sidecars with split, AUC and gains.
- `t37m4\data\`:

  | File | Contents |
  |---|---|
  | `purchases.pkl` | 548,160 historical purchases (user, product, ts), 09-15→11-14 |
  | `item_stats.pkl` | 10,000 × [product_id, pre, v, c, p, buyers] |
  | `user_cat.pkl` | 691k × [user_id, category, pre, v, c, p, spend] |
  | `coview.pkl` | 150k pairs [p, q, n] |

### Other folders

- `fresh_strategy\`: an independent CatBoost/"autoweights" track (shadow mostly). Files:
  - `leaderboard_snapshots\*.json`: 4 full API states, 17:56–18:57 UTC.
  - `leaderboard_initial.json`: full API state at the start of the track.
  - `adaptive_leaderboard.jsonl`: 9 rows of per-version official numbers for t37-cf-rot vs t37-m4, ~18:49–19:18.
  - `live.jsonl`: 213 rows, shadow run with deadline / catalog skip counters.
  - `shadow_*.jsonl`: 100 decisions. Delay p95 12.5 s, 0% within 3 s, on the old transport.
  - `five_shard_controller.jsonl`: shard occupancy.
  - `shard_audit.json`: submissions by model × hash shard, 19:28–19:32.
  - `offline_comparison\{decisions,validation_decisions}.jsonl`: per request, the slate of each model + observed labels. 3,000 requests 18:43–19:00; 1,500 requests 19:07–19:16.
  - `offline_comparison\RESULTS.md`, `report.json`, `tuning_report.json`, `validation_report.json`.
  - `recent_benchmark.json`: 10,000 mature requests 16:52–17:48. 133 purchases (1.33%, Wilson 1.12–1.57), 406 clicks, 260 missing, cold 60/3,579.
  - `artifacts\report.json`: CatBoost training split.
  - `data\*.json`: raw extracts of every table at 17:48.
  - SQLite: `auto_weights.sqlite` (89 decisions), `auto_weights_shadow.sqlite` (255), `adaptive_submissions.sqlite` (88 attempts).
- `fz_standby\` (new, 01:41 CET): the **currently live model `fz-v9a-xcat1.0`** (+ `fz-v10-nocorr` split). Self-contained (serve.py, ranker.py, learn.py, data/*.parquet, model.pkl, cfg.json). `README.md` has a live A/B table (section 4). `results\ablation.txt` and `results\model_size.txt` hold offline AUC/MRR by feature group.
- `helm_harness\reports\*.md`: 17 research reports (cold start, bandits, simulators, competitor scan). `ESTRATEGIAS.md` synthesises them; its §4 lists tests A–J.
- `t37_sim\`: git worktree, branch `sim/judge`, at the same commit as main (f048535), clean, no extra data. It is a copy of the engine.
- `t37_review\`: detached worktree at 1ad8670 (old review checkout).
- `rawtree_team37_launcher\`: old standalone writer (`content-session-popularity-v1`). `recent_submissions.json` holds its last submissions.

---

## 4. Key findings with numbers

### 4.1 Hourly practice timeline (DB, `out/hourly.json` + `out/model_by_hour.json` + API `out/lb_hourly_all_teams.json`)

| Hour UTC | Req | Team served | Missing | Purch. (realised) | Official conv | Cold conv | On-time % | Rank /42 | Main arms |
|---|---|---|---|---|---|---|---|---|---|
| 12 | 10,800 | 5,766 | 3,341 | 82 | 0.713 | 1.259 | 63.2 | 24/39 | content-session-popularity-v1 |
| 13 | 10,800 | 9,703 | 1,073 | 77 | 0.739 | 1.245 | 89.8 | 20/41 | content-session-pop, ev-v1 |
| 14 | 10,800 | 8,776 | 2,023 | 124 | 1.236 | 1.699 | 81.3 | 7 | ev-v2 family |
| 15 | 10,783 | 10,042 | 729 | 136 | 1.289 | 1.537 | 93.2 | 10 | ev-v2-nocovis, ev-v3, m1–m3, lgbm-recent |
| 16 | 10,800 | 9,068 | 1,732 | 138 | 1.262 | 1.669 | 84.0 | 11 | lgbm-recent, cf-v1, cf-rot |
| 17 | 10,800 | 9,831 | 969 | 136 | 1.210 | 1.572 | 91.0 | 17 | nocovis, skibidy, lgbm, ev-v3 |
| 18 | 10,800 | 9,475 | 1,325 | 127 | 1.057 | 1.328 | 87.7 | 17 | nocovis, ev-v3, skibidy, m4 |
| 19 | 10,800 | 8,404 | 2,396 | 136 | 1.207 | 1.666 | 77.8 | 20 | t37j-v2, brainrot, m4 |
| 20 | 10,800 | 5,966 | 4,834 | 115 | 1.074 | 1.519 | 55.2 | 21 | brainrot, t37j-v2 |
| 21 | 10,800 | 9,443 | 1,357 | 166 | 1.517 | 1.745 | 87.4 | 15 | brainrot-bk + 13 fz-* variants |
| 22 | 10,800 | 7,931 | 2,869 | 172 | 1.576 | 1.942 | 73.4 | 13 | fz-v7c-xcat2.5, fz-v9a |
| **23** | 10,800 | 10,660 | **140** | **243** | **2.234** | **2.764** | **98.7** | **3** | fz-v9a-xcat1.0 + fz-v10-nocorr |
| 00 (partial) | 7,401 | 933 | 6,453 | 54 | — | — | — | — | **outage 00:05–00:38 UTC** (0 served 00:20–00:30); back at 00:40 |

- Practice totals (12:09→00:41): 106,165 team-served (78.6%), **29,241 fallback-missing (21.6%)**, 37 invalid.
- Realised purchase rates: team 1,525 purchases = **1.436/100** (CTR 4.60/100, buy|click 31%). Fallback 191 = **0.653/100** (≈ baseline).
- Official `progress` (our normalised conversion score, by hour 12→23): 0.6, 1.5, 16.2, 21.9, 25.7, 22.7, 23.0, 17.5, 18.7, 35.6, 38.9, **57.9**. Leader team_06: 64.7 at 23h.
- Current API windows:
  - Last 60 min at 00:44: conv 1.347, on_time 39.8%, rank 20.
  - Last 3 h: conv 1.605, on_time 67.4%, rank 13.
- **The missing share is the biggest swing factor.** With on-time o and baseline b, the served-only conversion is `(conv − (1−o)·b)/o`. For 20h: (1.074 − 0.448·0.532)/0.552 ≈ **1.51** served vs 1.07 reported.

### 4.2 Arm comparison, official expected conversion (API hourly windows, request-weighted, `out/lb_team37_versions_hourly_agg.json`)

| Arm | Requests | Exp. conv/100 | Cold conv | Rev/req | Same-hours baseline | Same-hours reference | Hours UTC |
|---|---|---|---|---|---|---|---|
| **fz-v9a-xcat1.0** (live) | 11,219 | **2.235** | 2.730 | 1.002 | 0.550 | 2.044 | 22–23 |
| fz-v10-nocorr (no online correction) | 2,187 | 2.210 | **2.891** | 0.883 | 0.550 | 2.073 | 23 |
| fz-v4-cart-live | 613 | 2.197 | 2.422 | 1.033 | 0.578 | 1.990 | 21 |
| fz-v6a-xcat1.0 | 497 | 2.089 | 2.594 | 0.821 | 0.578 | 1.990 | 21 |
| fz-v7c-xcat2.5 | 5,012 | 1.884 | 2.212 | 0.893 | 0.554 | 1.958 | 21–22 |
| t37_brainrot / -bk | 2,677 / 3,492 | 1.721 / 1.622 | 2.207 / 1.963 | 0.63 | 0.58 / 0.57 | 2.04 / 1.99 | 19–21 |
| t37-lgbm-recent | 5,756 | 1.501 | 2.085 | 0.732 | 0.571 | 2.014 | 15–17 |
| t37-cf-rot | 2,285 | 1.419 | 1.956 | 0.860 | 0.521 | 1.948 | 16–18 |
| t37-cf-v1 | 3,385 | 1.371 | 1.762 | 0.652 | 0.553 | 1.998 | 16–17 |
| t37j-v2 | 7,132 | 1.330 | 1.824 | 0.830 | 0.640 | 2.120 | 19–20 |
| t37-ev-v2-nocovis | 14,880 | 1.323 | 1.527 | 0.562 | 0.599 | 2.014 | 14–18 |
| t37-ev-v3 | 6,323 | 1.221 | 1.328 | 0.548 | 0.584 | 2.000 | 14–18 |
| t37-skibidy-v1 / v1g | 3,356 / 1,531 | 1.073 / 1.109 | 1.37 / 1.69 | 0.80 / 0.40 | 0.53 / 0.51 | 1.96 / 1.93 | 16–18 |
| fz-v0-heur | 1,054 | 1.023 | 1.325 | 0.469 | 0.572 | 1.988 | 20–21 |
| t37-m4 (Thompson) | 1,207 | 0.892 | 1.024 | 0.334 | 0.578 | 2.028 | 18–19 |
| content-session-popularity-v1 | 14,395 | 0.732 | 1.196 | 0.222 | 0.699 | 2.037 | 12–13 |
| t37-ev-v1 | 2,288 | 0.690 | 1.527 | 0.220 | 0.747 | 2.102 | 13–14 |

All 38 arms with n are in the JSON. The baseline varies by hour (0.45–0.79), so compare arms with the **same-hour normalised score `(conv−base)/(ref−base)`**, not raw conversion.

- **Caveat:** arms ran in different hours and under multi-writer contamination 14–21 UTC (`out/emitter_overlap_hourly.json`: up to 5,377 requests/h with >1 submission, 4,862 with >1 version). Only the 22–23h fz runs are single-writer.
- Realised DB per arm is in `out/per_model.json`. Example: fz-v9a 275 purchases / 11,884 = 2.31/100; nocovis 1.34; lgbm-recent 1.41.

### 4.3 fz live A/B (from `fz_standby/README.md`, official conversion %)

| Comparison | Result |
|---|---|
| Same category only vs all categories | 1.38 vs 2.09 |
| ×0.5 penalty on other categories vs none | 1.84 vs 2.09 |
| ×2.5 boost on other categories vs none | 1.86 vs 2.49 |
| Diversity cap (max 2 per subcategory) vs none | 1.42 vs 1.85 |
| Online correction on vs off | 2.21 vs 2.17 (tie) |
| Retrain with live rows ×4 vs history only | click AUC 0.83 vs 0.86 |

Final config fz-v9a: 2.25% conversion, 2.88% cold, n = 2,657 (baseline 0.59, reference 1.94). Offline purchase AUC ≈0.958.

### 4.4 Slot / position curve

**Live team-served** (DB, purchases per 1,000 impressions, non-new items, slots 1→10): **6.08**, 2.22, 1.46, 0.96, 0.87, 0.73, 0.48, 0.46, 0.42, 0.40.
- Purchases by slot: 671, 236, 155, 101, 95, 77, 50, 49, 45, 47. **Slot 1 = 44% of all purchases.**
- Clicks by slot: 1,784, 749, 504, 379, 317, 291, 218, 213, 226, 209.

**Fallback list** (fixed best sellers) purchases per 1,000 by slot: 2.36, 0.48, 1.06, 0.68, 0.31, 0.31, 0.38, 0.51, 0.24, 0.21.

**History (old carousel, 2M impressions):**
- Clicks by slot: 21,483, 12,015, 8,805, 6,836, 5,629, 5,043, 4,438, 3,923, 3,483, 3,260.
- Purchases by slot: 8,982, 4,679, 3,443, 2,525, 2,004, 1,695, 1,400, 1,273, 1,058, 994.
- This curve is confounded: the old policy put its best items on top. De-bias it with `propensity[]`.

**Model-implied examination** (`docs/live_ranker.md`, relative to slot 1):
- Purchase model: 1.00, .65, .57, .43, .42, .32, .21, .21, .19, .19.
- Raw CTR: 1.00, .39, .37, .19, .27, .22, .16, .12, .18, .18.

### 4.5 Relation × slot (purchase rates per shown item)

From `helm_harness/brief.md` / `ESTRATEGIAS.md`, about 18.5k team-served requests (d1):

| Relation | Slot 1 | Overall |
|---|---|---|
| Session view, not the last | **2.08%** (n = 672) | 0.24% |
| Carted in history, not bought | 0.91% | 0.29% |
| Discovery / unrelated | 0.75% (home 0.46%) | — |
| Last session view | 0.66% | 0.14% |
| Viewed in history, never carted or bought | 0.03% (took 24% of slots in one arm) | 0.027% |
| Bought before | ≈0 | — |

From `docs/t37m4_thompson.md` (51,486 requests, 549 purchases, to 17:55 CET), buys per 1,000 shown:

| Fact | Buys per 1,000 |
|---|---|
| Already bought | 1 in 24.5k |
| Slot 1: viewed earlier / last viewed / other | 19.4 / 10.2 / 4.2 |
| Same subcategory as a past purchase, slot 1 | 7.2 vs 3.7 |
| Popularity inside the last-viewed category | 0.4 → 13.1 (slot 1) |
| Price > €100 vs €10–100 | 1.48 vs 0.86–0.94 |
| New products, slot 1 | 7.2 vs 4.7 |

From `docs/live_ranker.md` (relation table, rows / observed buy %):

| Relation | Rows | Observed buy % |
|---|---|---|
| viewed_last | 2,598 | 0.23 |
| viewed_earlier | 2,701 | 0.33 |
| user_viewed | 13,291 | 0.29 |
| same_cat | 17,354 | 0.19 |
| same_sub | 68,391 | 0.09 |
| other | 76,719 | 0.05 |
| other_home | 40,613 | 0.03 |
| user_bought | 21,753 | 0.005 |

- Cart: an unbought carted item converts ≈6.3/1,000 shown vs 0.7 for ordinary items (`docs/cartfirst.md`). fz README: ≈18× in the historical log.

### 4.5b Relation × slot recomputed from the DB (realised outcomes, team-served)

Source: `out/relation_full_by_slot_all.json` (12:09 → ~02:00 UTC, by served_by × era × slot × relation) and `out/relation_full_by_slot_fz.json` (fz era 22:00–00:05 UTC). The SQL is in §7.

Relation precedence, first match wins:
1. **bought_before**: purchase in history_events or events before the request ts.
2. **carted_not_bought**: add_to_cart before the request ts, no purchase.
3. **no_session_views**: empty recent_views.
4. **session_last_view**.
5. **session_earlier_view**.
6. **new_product_other**.
7. **other**.

"Viewed in history but never carted" is folded into `other`. It is not computed, because it would need a join over 10M view events.

Full period, team rows (purchases per 1,000 impressions):

| Relation | Share of team slots | Impressions | Clicks | Purchases | Overall /1,000 | Slot-1 /1,000 (n) |
|---|---|---|---|---|---|---|
| session_earlier_view | 2.4% | 29,015 | 180 | 78 | 2.69 | **16.7** (2,936) |
| session_last_view | 2.4% | 29,136 | 169 | 72 | 2.47 | 9.8 (4,785) |
| carted_not_bought | **24.3%** | 292,975 | 2,792 | 935 | **3.19** | 9.4 (50,850) |
| new_product_other | 4.6% | 55,145 | 314 | 86 | 1.56 | 6.8 (4,392) |
| other | 49.9% | 601,674 | 2,189 | 626 | 1.04 | 4.0 (42,722) |
| no_session_views (home) | 14.4% | 173,408 | 258 | 41 | 0.24 | 1.0 (12,123) |
| bought_before | 2.1% | 25,277 | 15 | **2** | 0.08 | 0.35 (2,855) |

fz era, slot 1 per 1,000:

| Relation | Slot-1 /1,000 (purchases / impressions) |
|---|---|
| session_last_view | 36.4 (9/247) |
| session_earlier_view | 20.9 (5/239) |
| new_product_other | 13.3 (17/1,283) |
| carted | 9.4 (84/8,941) |
| other | 7.0 (45/6,406) |
| no_session_views | 0.5 (1/1,896) |

- In the fz era, carted items take 27.7% of slots. Bought-before items still take 1.2% of slots and produced 1 purchase.
- Fallback lists: bought_before is 16,337 impressions with 3 purchases, so wasted slots exist in the baseline too.
- The full per-slot curve (slots 1–10) for each relation is in the JSON.

### 4.6 Segments / cold start (DB, team-served, realised purchases/100; fallback in parentheses)

| Segment | Team (fallback) |
|---|---|
| Cold | **1.926** (1.102) |
| Warm | 1.149 (0.386) |
| New user | **2.006** (1.270) |
| Returning user | 1.192 (0.393) |
| Home | **0.475** (0.271) |
| Product page | 1.688 (0.733) |
| Category page | 1.647 (0.788) |
| 0 views | 0.475 |
| 1 view | **1.968** |
| 2–3 views | 1.583 |
| 4+ views | 1.472 |
| Android / iOS / web | 1.579 / 1.327 / 1.402 |
| Revenue/request, cold vs warm | €0.83 vs €0.53 |

- Home + returning user is the weakest cell: 0.403 (n = 14,902). Product page + new user is the strongest: 2.405 (n = 17,798).
- **New products in our lists:** slot 1 converts **10.5/1,000** (n = 6,104 impressions) vs 6.1 for established items. Slots 2–10 are similar or lower. New items get about 6–9k impressions per slot.
- Official cold conversion is above overall conversion for nearly all arms. The API cold metric is a separate 10-pt component.

### 4.7 Reliability / latency

- Missing by hour: 140 (23h, 1.3%) up to 4,834 (20h, 45%). Outage 00:05–00:38 UTC: 6,453 missing in partial hour 00.
- Earlier review (13:15–16:25): 27,507 answers, 4,841 missing (~15%). Causes: host DNS/network drops and restarts (`docs/review_20261114.md` P1-3), backlog ranking after outages, push retries.
- Latency (team): p50 1.10–1.40 s by hour, p95 1.79–2.94 s. Ranking alone takes about 10–45 ms (`recent_serving_benchmark.json`: p95 17 ms; fz ~45 ms). **Latency is dominated by network and polling, not the model.**
- Network probe (`fresh_strategy/network_probe.json`): RTT 212–1,595 ms to the API.
- Multi-writer: up to 50% of requests got >1 submission in 15–17 UTC. 2,638 late submissions were scored as missing.

### 4.8 Offline evaluation results (diagnostics, not simulator conversion)

**`recent_evaluation.md`:** LGBM recent, test 15:08–15:23, 2,646 requests, 35 purchases.

| Metric | Model | Logged order |
|---|---|---|
| Purchase NDCG | 0.7319 | 0.6952 |
| Top-3 | 0.800 | 0.686 |

Paired Δ +0.0367, CI [−0.062, +0.154]. The gate is **not** passed. Serving p95 is 17 ms.

**`policy_replay.md`:** 3,000 requests at 15:00–15:23, 36 purchases.

| Policy | Purchase NDCG | Cold NDCG |
|---|---|---|
| nocovis | 0.640 | 0.682 |
| v3 | 0.628 | 0.662 |
| content | 0.628 | 0.662 |
| v4-session | 0.619 | 0.666 |

v4 − nocovis = −0.021, CI [−0.061, +0.010].

**`lgbm_cart_v2`:** 6,833 requests, 81 purchases. AUC 0.904 but NDCG −0.0445 vs logged order, CI [−0.107, +0.015]. Not promoted.

**`cycle_log.md`:** 4 cycles with paired ΔNDCG vs ev-v3.
- ev-context +0.042 [+0.006, +0.089], n = 40 (cycle 1). It did not replicate in cycles 2–4 (+0.017, +0.023, +0.003).
- ev-recent-covis −0.038: killed.
- ev-v2-tier −0.026: parked.

**`fresh_strategy/offline_comparison`** (3,000 requests, 40 purchases):

| Model | Purchases recovered in top 10 | NDCG |
|---|---|---|
| cf-rot | 27/40 | 0.543 |
| ev-v2-nocovis | 26/40 | 0.451 |
| skibidy | 17/40 | 0.256 |
| CatBoost | 15/40 | 0.235 |

Validation (1,500 requests, 18 purchases): tuned cf-cart18-session15 0.511 (11/18) vs 0.472 (10/18).

**fz ablation** (`fz_standby/results/ablation.txt`, buy AUC by removed group):

| Removed group | Buy AUC |
|---|---|
| none | 0.9065 |
| user counts | **0.842** |
| pop | 0.901 |
| user attr | 0.901 |

User counts and popularity matter most. MRR buy drops most without pop (0.475) and user sub/cat (0.497).

### 4.8b Price changes and organic stream (DB, `out/price_changes_hourly.json`, `out/events_category_hourly.json`, `out/live_streams_hourly.json`)

**Price changes are category-wide sales.** Every change in an hour hits a single category. Prices drop about 18% (p10 −20%, p90 −14 to −17%), then return to the catalog price 2 h later.

| Sale (UTC) | Category | Products | Revert |
|---|---|---|---|
| 10h | Pets | 612 | 12h |
| 13h | Home & Garden | 639 | 15h |
| 16h | Sports & Outdoors | 487 | 18h |
| 19h | Sports & Outdoors | 485 | 21h |
| 22h | Electronics | 576 | 00h |
| 01h | Sports & Outdoors | 486 | (pending) |

Organic purchase share of the discounted category rises during the sale:

| Category | Normal share | During sale |
|---|---|---|
| Pets | ≈5.5% | 6.9–8.0% |
| Home & Garden | 3.4% | 3.9–5.2% |
| Sports & Outdoors | ≈10.5% | 12.0–12.4% |
| Electronics | ≈10.5% | 12.0–12.7% |

Purchases per 1,000 views also rise, e.g. Pets 31 → 36 and Home & Garden 22 → 28.

- **Trend shift:** Pets purchase share jumped to 10.5% (01h) and 16.0% (02h) with no Pets price change. Purchases per 1,000 views went 31 → 61. This is a new-trend signal worth watching (the final announces "new trends").
- Stock: exactly 36 out_of_stock + 36 back_in_stock per hour.
- New products: 100 at 10, 14, 18 and 22 UTC.
- Event volume: steady ≈236k/h (≈207k views, ≈21.8k carts, ≈10.9k purchases), about 65 events/s.

### 4.9 Competitors (API)

- Last 60 min at 00:44 UTC, conversion (cold, on-time):

  | Rank | Team | Conv | Cold | On-time % |
  |---|---|---|---|---|
  | #1 | team_06 | 2.443 | 3.162 | 100 |
  | #2 | team_14 | 2.316 | — | 96.7 |
  | #3 | team_17 | 2.312 | — | 97.6 |
  | #4 | team_03 | 2.286 | — | 100 |
  | #5 | team_42 | 2.240 | — | 100 |
  | #20 | team_37 | 1.347 | — | 39.8 (outage) |

  Reference 2.008, baseline 0.601, 42 teams.
- At 23h our 2.234 was 3rd of 42 and 0.20 behind team_06 (2.434). team_06 has led every hour since 12h.
- 560 team-hour rows are in `out/lb_hourly_all_teams.json` (10h–23h, all 40–42 teams). The team `progress` series is in `out/lb_state_default.json`.

---

## 5. Candidate decision questions the data can answer

1. **Which config do we freeze for the final?** Compare fz-v9a vs fz-v10-nocorr vs earlier arms on same-hour normalised score (API versions) and cold score. fz-v9a and v10 are close: 2.235 vs 2.210, cold 2.73 vs 2.89.
2. **How many points does reliability cost?** Per hour: reported conversion vs served-only conversion. The gap equals (1−on_time)×(served−baseline). Add the 10-pt on-time component and the outage timeline. Headline: 23h (98.7% on time) = rank 3; 20h (55%) = rank 21.
3. **Is a standby writer worth it?** Count missing minutes: outage clusters at 12, 20, 22 and 00h, and expected points lost.
4. **Where should slot 1 go?** Slot curve (slot 1 = 44% of purchases) + relation × slot table. Session-view-earlier, cart and new-product-in-session versus last view and history-only views.
5. **Cold start:** cold vs warm conversion, new-user vs returning, new-product exposure and conversion by slot. Do new products deserve slot 1? (10.5 vs 6.1 per 1,000.)
6. **Weakest segment:** home / no-views requests (0.40–0.48/100, 20% of traffic). Context priors (device × region) are the candidate lever. Evidence is weak: ev-context did not replicate offline.
7. **Explore or exploit in the final?** About 190–300 purchases expected in 2 h. An A/B test detects only large lifts. Use the official per-version API metric and pre-registered rules.
8. **Gap to the leaders:** our hourly rank and conversion vs team_06 and the top 5. Split conversion and reliability gaps.
9. **Latency headroom:** p95 vs the 3 s / 3.5 s cutoff, by hour. Network vs model time.
10. **Online correction / learning:** fz-v9a (on) vs fz-v10 (off), calibration expected vs observed (online_calibration.json: 22.9 expected vs 15 observed).

---

## 6. Gaps / risks

- **Live writer state:** an outage from 00:05 to 00:38 UTC happened during this inventory: 0–94 team-served per 10 min, 1,800 missing per 10 min. Service resumed at 00:40 (375/389 served). The current 60-min API window shows on_time 39.8%. Whoever owns the writer should confirm it is stable.
- **No official rules file** locally. The scoring formula comes from team notes (brief.md). The oracle value is hidden. The `progress` = normalised-vs-oracle reading is an inference, implied oracle ≈3.2–3.5.
- **Deadline:** the stated 3 s vs observed team rows at up to 3,499 ms. Late submissions are labelled `missing`, never `late`.
- **Arm comparisons are confounded:**
  - Different hours with different baselines.
  - Multi-writer contamination 14–21 UTC.
  - The `(ambiguous)` and `(unmatched)` attribution buckets.
  - Small n per arm for purchases (often < 50).
  - Only the 22–23h fz runs are clean single-writer.
- **Realised vs expected:** DB feedback holds realised coin flips (noisy). The API holds the expected metric but only aggregates, no per-request probabilities. Per-request P(buy) exists only in `exposure_metadata.jsonl` (lgbm-recent, 15:39–17:49) and must be recomputed for other models.
- **Cold flag must be computed:** `is_new_user` OR a new product in recent_views. The DB has no flag, and the API gives cold aggregates only.
- **`submissions` has no timestamp:** send time and latency per arm come only via feedback.
- **Relation × slot:** recomputed in SQL in §4.5b for all hours, including the fz era. The "viewed in history, never carted" relation (0.03% in docs) is NOT separated: it sits inside `other`, because separating it needs a join over 10M history views. Docs and pickles (up to 18:02 UTC) hold the finer relation set.
- **Local logs end at about 19:58 UTC** (monitor stopped). After that only the DB and API cover the period.
- **Pickles contain user_ids:** aggregate them before any chart.
- **Snapshot staleness:** offline replays used snapshots 75–98 min old. All offline NDCG results are exposure-biased diagnostics, not conversion.
- **The final has new data:** practice-level per-arm numbers may not transfer, because 400 new products and new users arrive.

---

## 7. Reusable SQL (all verified to run, 1.7–7 s each)

Schemaless JSON: always cast. Add `SETTINGS max_execution_time = 25` (30 s hard limit). Team DB = `team_37`. The exact SQL of every query is also stored in `inv/out/<name>.json` under `"sql"`.

Live windows are hard-coded literals (`'2026-11-14 12:09:00'` = team start). Parametrise them in the pipeline. Feedback for a request matures ~4.3 s after request ts, so exclude the last ~10 s.

### A. Reliability / per-request

**`hourly`**: Per UTC hour: requests, new-user/cold/home requests, feedback coverage, team-served, missing/late/invalid, clicks, purchases, revenue, cold purchases, latency p50/p95 (team), feedback-ts minus request-ts. Cold flag computed inline. (output: `inv/out/hourly.json`, 16 rows)

```sql
SELECT toString(toStartOfHour(r.ts)) AS hour_utc,
       count() AS requests,
       countIf(r.nu) AS new_user_req,
       countIf(r.cold) AS cold_req,
       countIf(r.page = 'home') AS home_req,
       countIf(f.rid != '') AS with_feedback,
       countIf(f.sb = 'team') AS served_team,
       countIf(f.fr = 'missing') AS missing,
       countIf(f.fr = 'late') AS late,
       countIf(f.fr = 'invalid') AS invalid,
       countIf(f.clk != '') AS clicks,
       countIf(f.pur != '') AS purchases,
       round(sum(f.rev), 2) AS revenue,
       countIf(f.pur != '' AND r.cold) AS cold_purchases,
       quantileIf(0.5)(f.lat, f.sb = 'team') AS p50_ms,
       quantileIf(0.95)(f.lat, f.sb = 'team') AS p95_ms,
       round(avgIf(dateDiff('millisecond', r.ts, f.fts), f.rid != ''), 1) AS avg_fb_ts_minus_req_ts_ms
FROM (
  SELECT request_id::String AS rid, ts::DateTime64(3) AS ts, is_new_user::Bool AS nu, context.page::String AS page,
         nu OR hasAny(JSONExtract(toJSONString(__raw_data), 'recent_views', 'Array(Tuple(product_id String, ts String))').product_id,
                      (SELECT groupArray(product_id::String) FROM shop.catalog_updates WHERE change::String = 'new_product')) AS cold
  FROM shop.requests) AS r
LEFT JOIN (
  SELECT request_id::String AS rid, ts::DateTime64(3) AS fts, served_by::String AS sb, fallback_reason::String AS fr,
         clicked::String AS clk, purchased::String AS pur, revenue_eur::Float64 AS rev, latency_ms::Float64 AS lat
  FROM team_37.feedback WHERE request_id::String != '__init__') AS f ON f.rid = r.rid
GROUP BY hour_utc ORDER BY hour_utc
SETTINGS max_execution_time = 28
```

**`last3h_10min`**: Per 10-min bucket over the last 180 min: requests, served, missing, no-feedback-yet, purchases (outage detector). (output: `inv/out/last3h_10min.json`, 19 rows)

```sql
SELECT intDiv(toUnixTimestamp(r.ts), 600) * 600 AS bucket10m, toString(toDateTime(bucket10m)) AS t_utc, count() AS requests,
       countIf(f.sb = 'team') AS served_team, countIf(f.fr = 'missing') AS missing, countIf(f.rid = '') AS no_feedback_yet,
       countIf(f.pur != '') AS purchases
FROM (SELECT request_id::String AS rid, ts::DateTime64(3) AS ts FROM shop.requests WHERE ts::DateTime64(3) > now() - INTERVAL 180 MINUTE) AS r
LEFT JOIN (SELECT request_id::String AS rid, served_by::String AS sb, fallback_reason::String AS fr, purchased::String AS pur
           FROM team_37.feedback WHERE ts::DateTime64(3) > now() - INTERVAL 181 MINUTE) AS f ON f.rid = r.rid
GROUP BY bucket10m ORDER BY bucket10m
SETTINGS max_execution_time = 25
```

**`fallback_reasons`**: served_by x fallback_reason: counts, latency distribution, >3000 ms count, clicks, purchases, purchase-not-on-clicked-item check. (output: `inv/out/fallback_reasons.json`, 3 rows)

```sql
SELECT served_by::String AS served_by, fallback_reason::String AS fallback_reason, count() AS n,
       countIf(latency_ms::Nullable(Float64) IS NULL) AS latency_null,
       min(latency_ms::Nullable(Float64)) AS lat_min, quantile(0.5)(latency_ms::Nullable(Float64)) AS lat_p50, quantile(0.99)(latency_ms::Nullable(Float64)) AS lat_p99, max(latency_ms::Nullable(Float64)) AS lat_max,
       countIf(latency_ms::Nullable(Float64) > 3000) AS lat_gt_3000,
       countIf(clicked::String != '') AS clicks, countIf(purchased::String != '') AS purchases,
       countIf(purchased::String != '' AND clicked::String != purchased::String) AS purch_not_clicked_item
FROM team_37.feedback WHERE request_id::String != '__init__'
GROUP BY served_by, fallback_reason ORDER BY n DESC
SETTINGS max_execution_time = 25
```

**`missing_vs_submission`**: Whether fallback rows had a submission (late = 'missing' with submission) and whether shown == a submitted list. (output: `inv/out/missing_vs_submission.json`, 4 rows)

```sql
SELECT f.sb AS served_by, f.fr AS fallback_reason, s.rid != '' AS has_submission, count() AS n,
       countIf(has(s.lists, f.shown_items)) AS shown_equals_a_submitted_list
FROM (SELECT request_id::String AS rid, served_by::String AS sb, fallback_reason::String AS fr, shown::Array(String) AS shown_items
      FROM team_37.feedback WHERE request_id::String != '__init__') AS f
LEFT JOIN (SELECT request_id::String AS rid, groupArray(items::Array(String)) AS lists FROM team_37.submissions GROUP BY rid) AS s ON s.rid = f.rid
GROUP BY served_by, fallback_reason, has_submission ORDER BY n DESC
SETTINGS max_execution_time = 28
```

**`emitter_overlap_hourly`**: Per hour: requests with 0 / 1 / >1 submissions and >1 distinct model_version (multi-writer contamination). (output: `inv/out/emitter_overlap_hourly.json`, 13 rows)

```sql
SELECT toString(toStartOfHour(r.ts)) AS hour_utc, count() AS requests,
       countIf(s.n = 0) AS no_submission, countIf(s.n = 1) AS one_submission, countIf(s.n > 1) AS multi_submission,
       countIf(s.nv > 1) AS multi_version, round(avg(s.n), 3) AS avg_submissions
FROM (SELECT request_id::String AS rid, ts::DateTime64(3) AS ts FROM shop.requests WHERE ts::DateTime64(3) >= '2026-11-14 12:00:00') AS r
LEFT JOIN (SELECT request_id::String AS rid, count() AS n, uniqExact(model_version::String) AS nv FROM team_37.submissions GROUP BY rid) AS s ON s.rid = r.rid
GROUP BY hour_utc ORDER BY hour_utc
SETTINGS max_execution_time = 28
```

**`per_model`**: Arm attribution (submission items == feedback.shown): requests, clicks, purchases, revenue, rates, first/last ts, latency per model_version (fallbacks as '(fallback:reason)'). (output: `inv/out/per_model.json`, 72 rows)

```sql
SELECT if(f.sb != 'team', concat('(', f.sb, ':', f.fr, ')'), if(s.mv = '', '(unmatched)', s.mv)) AS model_version,
       count() AS requests, countIf(f.clk != '') AS clicks, countIf(f.pur != '') AS purchases, round(sum(f.rev), 2) AS revenue,
       round(100 * countIf(f.pur != '') / count(), 3) AS purch_per100, round(100 * countIf(f.clk != '') / count(), 3) AS clicks_per100,
       toString(min(f.fts)) AS first_ts, toString(max(f.fts)) AS last_ts,
       quantile(0.5)(f.lat) AS p50_ms, quantile(0.95)(f.lat) AS p95_ms, max(f.lat) AS max_ms
FROM (SELECT request_id::String AS rid, ts::DateTime64(3) AS fts, served_by::String AS sb, fallback_reason::String AS fr,
             clicked::String AS clk, purchased::String AS pur, revenue_eur::Float64 AS rev, latency_ms::Float64 AS lat, shown::Array(String) AS shown_items
      FROM team_37.feedback WHERE request_id::String != '__init__') AS f
LEFT JOIN (SELECT request_id::String AS rid, items::Array(String) AS sent_items,
                  if(uniqExact(model_version::String) = 1, any(model_version::String), '(ambiguous)') AS mv
           FROM team_37.submissions GROUP BY rid, sent_items) AS s ON s.rid = f.rid AND s.sent_items = f.shown_items
GROUP BY model_version ORDER BY requests DESC
SETTINGS max_execution_time = 28
```

**`model_by_hour`**: Same attribution per hour x model_version (arm time series). (output: `inv/out/model_by_hour.json`, 143 rows)

```sql
SELECT toString(toStartOfHour(f.fts)) AS hour_utc,
       if(f.sb != 'team', concat('(', f.sb, ':', f.fr, ')'), if(s.mv = '', '(unmatched)', s.mv)) AS model_version,
       count() AS requests, countIf(f.clk != '') AS clicks, countIf(f.pur != '') AS purchases, round(sum(f.rev), 2) AS revenue,
       quantile(0.95)(f.lat) AS p95_ms
FROM (SELECT request_id::String AS rid, ts::DateTime64(3) AS fts, served_by::String AS sb, fallback_reason::String AS fr,
             clicked::String AS clk, purchased::String AS pur, revenue_eur::Float64 AS rev, latency_ms::Float64 AS lat, shown::Array(String) AS shown_items
      FROM team_37.feedback WHERE request_id::String != '__init__') AS f
LEFT JOIN (SELECT request_id::String AS rid, items::Array(String) AS sent_items,
                  if(uniqExact(model_version::String) = 1, any(model_version::String), '(ambiguous)') AS mv
           FROM team_37.submissions GROUP BY rid, sent_items) AS s ON s.rid = f.rid AND s.sent_items = f.shown_items
GROUP BY hour_utc, model_version ORDER BY hour_utc, requests DESC
SETTINGS max_execution_time = 28
```

### B. Per-shown-item outcomes / position / relation

**`slot_curve`**: Clicks/purchases/revenue by slot of the clicked item (indexOf(shown, clicked)), team vs fallback. (output: `inv/out/slot_curve.json`, 20 rows)

```sql
SELECT served_by::String AS sb, indexOf(shown::Array(String), clicked::String) AS slot_1based,
       count() AS clicks, countIf(purchased::String != '') AS purchases, round(sum(revenue_eur::Float64), 2) AS revenue
FROM team_37.feedback WHERE request_id::String != '__init__' AND clicked::String != ''
GROUP BY sb, slot_1based ORDER BY sb, slot_1based
SETTINGS max_execution_time = 25
```

**`new_item_by_slot`**: Impressions, clicks, purchases per slot x is_new_product (ARRAY JOIN of shown with arrayEnumerate): position curve with exposure denominators. (output: `inv/out/new_item_by_slot.json`, 30 rows)

```sql
WITH (SELECT groupArray(product_id::String) FROM shop.catalog_updates WHERE change::String = 'new_product') AS newp
SELECT sb, slot, is_new_item, count() AS impressions, countIf(clk = pid) AS clicks, countIf(pur = pid) AS purchases,
       round(1000 * countIf(pur = pid) / count(), 3) AS purch_per_1000_impr
FROM (SELECT served_by::String AS sb, clicked::String AS clk, purchased::String AS pur, shown::Array(String) AS shown_items
      FROM team_37.feedback WHERE request_id::String != '__init__')
ARRAY JOIN shown_items AS pid, arrayEnumerate(shown_items) AS slot
LEFT ARRAY JOIN [has(newp, pid)] AS is_new_item
GROUP BY sb, slot, is_new_item ORDER BY sb, is_new_item, slot
SETTINGS max_execution_time = 28
```

**`relation_session_by_slot`**: Relation from recent_views only (last view / earlier view / new product / no views / other) x slot, all feedback. (output: `inv/out/relation_session_by_slot.json`, 90 rows)

```sql
WITH (SELECT groupArray(product_id::String) FROM shop.catalog_updates WHERE change::String = 'new_product') AS newp
SELECT f.sb AS served_by, slot,
       multiIf(length(r.rv) = 0, 'no_session_views', pid = r.rv[length(r.rv)], 'session_last_view', has(r.rv, pid), 'session_earlier_view', has(newp, pid), 'new_product_other', 'other') AS relation,
       count() AS impressions, countIf(f.clk = pid) AS clicks, countIf(f.pur = pid) AS purchases,
       round(1000 * countIf(f.pur = pid) / count(), 3) AS purch_per_1000
FROM (SELECT request_id::String AS rid, served_by::String AS sb, clicked::String AS clk, purchased::String AS pur, shown::Array(String) AS shown_items
      FROM team_37.feedback WHERE request_id::String != '__init__') AS f
INNER JOIN (SELECT request_id::String AS rid,
                   arrayMap(x -> x.1, arraySort(x -> x.2, JSONExtract(toJSONString(__raw_data), 'recent_views', 'Array(Tuple(product_id String, ts String))'))) AS rv
            FROM shop.requests WHERE ts::DateTime64(3) >= '2026-11-14 12:09:00') AS r ON r.rid = f.rid
ARRAY JOIN f.shown_items AS pid, arrayEnumerate(f.shown_items) AS slot
GROUP BY served_by, slot, relation ORDER BY served_by, relation, slot
SETTINGS max_execution_time = 28
```

**`relation_full_by_slot_all`**: Full relation (bought_before > carted_not_bought > session > new > other) x slot x served_by x era, joining history_events + events purchases/carts strictly before request ts. Edit the era multiIf and time literals to re-window. ~2.5 s. (output: `inv/out/relation_full_by_slot_all.json`, 516 rows)

```sql
WITH (SELECT groupArray(product_id::String) FROM shop.catalog_updates WHERE change::String = 'new_product') AS newp
SELECT sb, era, slot, relation, count() AS impressions, countIf(clk = pid) AS clicks, countIf(pur = pid) AS purchases,
       round(1000 * countIf(pur = pid) / count(), 3) AS purch_per_1000
FROM (
  SELECT s.sb AS sb, s.era AS era, s.slot AS slot, s.pid AS pid, s.clk AS clk, s.pur AS pur,
         multiIf(arrayExists(t -> t < s.rts, e.buys), 'bought_before',
                 arrayExists(t -> t < s.rts, e.carts), 'carted_not_bought',
                 length(s.rv) = 0, 'no_session_views',
                 s.pid = s.rv[length(s.rv)], 'session_last_view',
                 has(s.rv, s.pid), 'session_earlier_view',
                 has(newp, s.pid), 'new_product_other', 'other') AS relation
  FROM (
    SELECT f.sb AS sb, multiIf(r.rts < '2026-11-14 14:00:00', 'a_12-14', r.rts < '2026-11-14 19:00:00', 'b_14-19', r.rts < '2026-11-14 21:00:00', 'c_19-21', 'd_21+') AS era, f.rid AS rid, r.uid AS uid, r.rts AS rts, r.rv AS rv, f.clk AS clk, f.pur AS pur, pid, slot
    FROM (SELECT request_id::String AS rid, served_by::String AS sb, clicked::String AS clk, purchased::String AS pur, shown::Array(String) AS shown_items
          FROM team_37.feedback WHERE request_id::String != '__init__') AS f
    INNER JOIN (SELECT request_id::String AS rid, user_id::String AS uid, ts::DateTime64(3) AS rts,
                       arrayMap(x -> x.1, arraySort(x -> x.2, JSONExtract(toJSONString(__raw_data), 'recent_views', 'Array(Tuple(product_id String, ts String))'))) AS rv
                FROM shop.requests WHERE ts::DateTime64(3) >= '2026-11-14 12:09:00') AS r ON r.rid = f.rid
    ARRAY JOIN f.shown_items AS pid, arrayEnumerate(f.shown_items) AS slot
  ) AS s
  LEFT JOIN (
    SELECT u, p, groupArrayIf(t, et = 'purchase') AS buys, groupArrayIf(t, et = 'add_to_cart') AS carts
    FROM (
      SELECT user_id::String AS u, product_id::String AS p, ts::DateTime64(3) AS t, event_type::String AS et FROM shop.history_events
      WHERE event_type::String IN ('purchase', 'add_to_cart') AND user_id::String IN (SELECT user_id::String FROM shop.requests WHERE ts::DateTime64(3) >= '2026-11-14 12:09:00')
      UNION ALL
      SELECT user_id::String AS u, product_id::String AS p, ts::DateTime64(3) AS t, event_type::String AS et FROM shop.events
      WHERE event_type::String IN ('purchase', 'add_to_cart') AND user_id::String IN (SELECT user_id::String FROM shop.requests WHERE ts::DateTime64(3) >= '2026-11-14 12:09:00')
    ) GROUP BY u, p
  ) AS e ON e.u = s.uid AND e.p = s.pid
)
GROUP BY sb, era, slot, relation ORDER BY sb, era, relation, slot
SETTINGS max_execution_time = 28
```

### C. Cold start / segments

**`segments`**: Team vs fallback realised conversion by page, device, new_user, cold, n_views bucket, page x new_user (ARRAY JOIN over dimension names). (output: `inv/out/segments.json`, 40 rows)

```sql
WITH newp AS (SELECT groupArray(product_id::String) AS ids FROM shop.catalog_updates WHERE change::String = 'new_product')
SELECT dim, val, sb, count() AS requests, countIf(clk != '') AS clicks, countIf(pur != '') AS purchases,
       round(100 * countIf(pur != '') / count(), 3) AS purch_per100, round(sum(rev) / count(), 4) AS rev_per_req
FROM (
  SELECT r.page, r.device, r.nu, r.cold, r.nviews, f.sb, f.clk, f.pur, f.rev
  FROM (SELECT request_id::String AS rid, context.page::String AS page, context.device::String AS device, is_new_user::Bool AS nu,
               JSONExtract(toJSONString(__raw_data), 'recent_views', 'Array(Tuple(product_id String, ts String))').product_id AS rv,
               length(rv) AS nviews, nu OR hasAny(rv, (SELECT ids FROM newp)) AS cold
        FROM shop.requests WHERE ts::DateTime64(3) >= '2026-11-14 12:09:00') AS r
  INNER JOIN (SELECT request_id::String AS rid, served_by::String AS sb, clicked::String AS clk, purchased::String AS pur, revenue_eur::Float64 AS rev
              FROM team_37.feedback WHERE request_id::String != '__init__') AS f ON f.rid = r.rid
) ARRAY JOIN ['page', 'device', 'new_user', 'cold', 'n_views', 'page_x_new_user'] AS dim,
             [page, device, toString(nu), toString(cold), multiIf(nviews = 0, '0', nviews = 1, '1', nviews <= 3, '2-3', '4+'), concat(page, '|new=', toString(nu))] AS val
GROUP BY dim, val, sb ORDER BY dim, val, sb
SETTINGS max_execution_time = 28
```

### D. Streams, catalog, history

**`live_streams_hourly`**: catalog_updates by change type per hour + shop.events by event_type per hour. (output: `inv/out/live_streams_hourly.json`, 93 rows)

```sql
SELECT * FROM (
SELECT 'catalog_updates' AS src, toString(toStartOfHour(ts::DateTime64(3))) AS hour_utc, change::String AS kind, count() AS n FROM shop.catalog_updates GROUP BY hour_utc, kind
UNION ALL
SELECT 'events' AS src, toString(toStartOfHour(ts::DateTime64(3))) AS hour_utc, event_type::String AS kind, count() AS n FROM shop.events GROUP BY hour_utc, kind
) ORDER BY src, hour_utc, kind
SETTINGS max_execution_time = 28
```

**`price_changes_hourly`**: Price-change magnitude vs catalog price per hour (cuts/rises, percentiles, categories). (output: `inv/out/price_changes_hourly.json`, 11 rows)

```sql
SELECT toString(toStartOfHour(u.ts)) AS hour_utc, count() AS price_changes, uniqExact(u.pid) AS products,
       round(avg(u.price / c.price - 1) * 100, 2) AS avg_pct_vs_catalog,
       round(quantile(0.1)(u.price / c.price - 1) * 100, 1) AS p10_pct, round(quantile(0.5)(u.price / c.price - 1) * 100, 1) AS p50_pct, round(quantile(0.9)(u.price / c.price - 1) * 100, 1) AS p90_pct,
       countIf(u.price < c.price) AS cuts, countIf(u.price > c.price) AS rises, groupUniqArray(u.cat) AS categories
FROM (SELECT product_id::String AS pid, ts::DateTime64(3) AS ts, price_eur::Float64 AS price, category::String AS cat FROM shop.catalog_updates WHERE change::String = 'price_change') AS u
INNER JOIN (SELECT product_id::String AS pid, price_eur::Float64 AS price FROM shop.catalog) AS c ON c.pid = u.pid
GROUP BY hour_utc ORDER BY hour_utc
SETTINGS max_execution_time = 25
```

**`events_category_hourly`**: shop.events views/carts/purchases per hour x category (promo / trend effects). (output: `inv/out/events_category_hourly.json`, 180 rows)

```sql
SELECT toString(toStartOfHour(e.ts)) AS hour_utc, c.cat AS category,
       countIf(e.et = 'view') AS views, countIf(e.et = 'add_to_cart') AS carts, countIf(e.et = 'purchase') AS purchases
FROM (SELECT ts::DateTime64(3) AS ts, product_id::String AS pid, event_type::String AS et FROM shop.events) AS e
INNER JOIN (SELECT product_id::String AS pid, category::String AS cat FROM shop.catalog) AS c ON c.pid = e.pid
GROUP BY hour_utc, category ORDER BY hour_utc, category
SETTINGS max_execution_time = 28
```

**`history_sessions_slots`**: Old carousel: clicks/purchases/revenue by clicked slot, time range. (output: `inv/out/history_sessions_slots.json`, 11 rows)

```sql
SELECT indexOf(shown::Array(String), clicked::String) AS click_slot_1based, count() AS rows_, countIf(purchased::String != '') AS purchases,
       round(sum(revenue_eur::Float64), 2) AS revenue, toString(min(ts::DateTime64(3))) AS min_ts, toString(max(ts::DateTime64(3))) AS max_ts
FROM shop.history_sessions GROUP BY click_slot_1based ORDER BY click_slot_1based
SETTINGS max_execution_time = 28
```

**`history_events_summary`**: history_events counts, users, range per event_type. (output: `inv/out/history_events_summary.json`, 3 rows)

```sql
SELECT event_type::String AS event_type, count() AS n, uniqExact(user_id::String) AS users, toString(min(ts::DateTime64(3))) AS min_ts, toString(max(ts::DateTime64(3))) AS max_ts
FROM shop.history_events GROUP BY event_type
SETTINGS max_execution_time = 28
```

**`catalog_summary`**: Catalog per category: products, subcats, brands, active, price stats, created range. (output: `inv/out/catalog_summary.json`, 10 rows)

```sql
SELECT category::String AS category, count() AS products, uniqExact(subcategory::String) AS subcats, uniqExact(brand::String) AS brands,
       countIf(is_active::Bool) AS active, round(quantile(0.5)(price_eur::Float64), 2) AS median_price, round(min(price_eur::Float64),2) AS min_price, round(max(price_eur::Float64),2) AS max_price,
       toString(min(created_at::DateTime64(3))) AS min_created, toString(max(created_at::DateTime64(3))) AS max_created
FROM shop.catalog GROUP BY category WITH TOTALS ORDER BY products DESC
SETTINGS max_execution_time = 25
```

### E. Discovery

**`system_tables`**: Tables, engines, row counts (SHOW is unsupported). (output: `inv/out/system_tables.json`, 9 rows)

```sql
SELECT database, name, engine, total_rows, total_bytes FROM system.tables WHERE database NOT IN ('system','information_schema','INFORMATION_SCHEMA') ORDER BY database, name
```

**`json_paths`**: JSON paths and types per table (sample 5,000 rows). (output: `inv/out/json_paths.json`, 9 rows)

```sql
SELECT 'shop.catalog' AS t, arraySort(groupUniqArrayArray(arrayMap((k, v) -> concat(k, ':', v), mapKeys(m), mapValues(m)))) AS paths FROM (SELECT JSONAllPathsWithTypes(__raw_data) AS m FROM shop.catalog LIMIT 5000) UNION ALL  SELECT 'shop.catalog_updates' AS t, arraySort(groupUniqArrayArray(arrayMap((k, v) -> concat(k, ':', v), mapKeys(m), mapValues(m)))) AS paths FROM (SELECT JSONAllPathsWithTypes(__raw_data) AS m FROM shop.catalog_updates LIMIT 5000) UNION ALL  SELECT 'shop.events' AS t, arraySort(groupUniqArrayArray(arrayMap((k, v) -> concat(k, ':', v), mapKeys(m), mapValues(m)))) AS paths FROM (SELECT JSONAllPathsWithTypes(__raw_data) AS m FROM shop.events LIMIT 5000) UNION ALL  SELECT 'shop.history_events' AS t, arraySort(groupUniqArrayArray(arrayMap((k, v) -> concat(k, ':', v), mapKeys(m), mapValues(m)))) AS paths FROM (SELECT JSONAllPathsWithTypes(__raw_data) AS m FROM shop.history_events LIMIT 5000) UNION ALL  SELECT 'shop.history_sessions' AS t, arraySort(groupUniqArrayArray(arrayMap((k, v) -> concat(k, ':', v), mapKeys(m), mapValues(m)))) AS paths FROM (SELECT JSONAllPathsWithTypes(__raw_data) AS m FROM shop.history_sessions LIMIT 5000) UNION ALL  SELECT 'shop.requests' AS t, arraySort(groupUniqArrayArray(arrayMap((k, v) -> concat(k, ':', v), mapKeys(m), mapValues(m)))) AS paths FROM (SELECT JSONAllPathsWithTypes(__raw_data) AS m FROM shop.requests LIMIT 5000) UNION ALL  SELECT 'team_37.feedback' AS t, arraySort(groupUniqArrayArray(arrayMap((k, v) -> concat(k, ':', v), mapKeys(m), mapValues(m)))) AS paths FROM (SELECT JSONAllPathsWithTypes(__raw_data) AS m FROM team_37.feedback LIMIT 5000) UNION ALL  SELECT 'team_37.scratch' AS t, arraySort(groupUniqArrayArray(arrayMap((k, v) -> concat(k, ':', v), mapKeys(m), mapValues(m)))) AS paths FROM (SELECT JSONAllPathsWithTypes(__raw_data) AS m FROM team_37.scratch LIMIT 5000) UNION ALL  SELECT 'team_37.submissions' AS t, arraySort(groupUniqArrayArray(arrayMap((k, v) -> concat(k, ':', v), mapKeys(m), mapValues(m)))) AS paths FROM (SELECT JSONAllPathsWithTypes(__raw_data) AS m FROM team_37.submissions LIMIT 5000)
```

**`samples`**: Two raw rows per table. (output: `inv/out/samples.json`, 17 rows)

```sql
SELECT 'shop.catalog' AS t, toJSONString(__raw_data) AS j FROM (SELECT __raw_data FROM shop.catalog LIMIT 2) UNION ALL  SELECT 'shop.catalog_updates' AS t, toJSONString(__raw_data) AS j FROM (SELECT __raw_data FROM shop.catalog_updates LIMIT 2) UNION ALL  SELECT 'shop.events' AS t, toJSONString(__raw_data) AS j FROM (SELECT __raw_data FROM shop.events LIMIT 2) UNION ALL  SELECT 'shop.history_events' AS t, toJSONString(__raw_data) AS j FROM (SELECT __raw_data FROM shop.history_events LIMIT 2) UNION ALL  SELECT 'shop.history_sessions' AS t, toJSONString(__raw_data) AS j FROM (SELECT __raw_data FROM shop.history_sessions LIMIT 2) UNION ALL  SELECT 'shop.requests' AS t, toJSONString(__raw_data) AS j FROM (SELECT __raw_data FROM shop.requests LIMIT 2) UNION ALL  SELECT 'team_37.feedback' AS t, toJSONString(__raw_data) AS j FROM (SELECT __raw_data FROM team_37.feedback LIMIT 2) UNION ALL  SELECT 'team_37.scratch' AS t, toJSONString(__raw_data) AS j FROM (SELECT __raw_data FROM team_37.scratch LIMIT 2) UNION ALL  SELECT 'team_37.submissions' AS t, toJSONString(__raw_data) AS j FROM (SELECT __raw_data FROM team_37.submissions LIMIT 2)
```

**`ranges_live`**: Counts and min/max ts of live tables; submissions distinct requests/versions. (output: `inv/out/ranges_live.json`, 5 rows)

```sql
SELECT 'shop.requests' AS t, count() AS n, toString(min(ts::DateTime64(3))) AS min_ts, toString(max(ts::DateTime64(3))) AS max_ts FROM shop.requests
UNION ALL SELECT 'team_37.feedback', count(), toString(min(ts::DateTime64(3))), toString(max(ts::DateTime64(3))) FROM team_37.feedback WHERE request_id::String != '__init__'
UNION ALL SELECT 'shop.catalog_updates', count(), toString(min(ts::DateTime64(3))), toString(max(ts::DateTime64(3))) FROM shop.catalog_updates
UNION ALL SELECT 'shop.events', count(), toString(min(ts::DateTime64(3))), toString(max(ts::DateTime64(3))) FROM shop.events
UNION ALL SELECT 'team_37.submissions', count(), toString(uniqExact(request_id::String)), toString(uniqExact(model_version::String)) FROM team_37.submissions
SETTINGS max_execution_time = 25
```

### F. Public leaderboard (not DB; already mirrored in `tukey_dashboard/data/raw/api`)

```text
GET https://datathon.rawtree.dev/api/state?by=model                         # last 60 min
GET https://datathon.rawtree.dev/api/state?by=model&from=<unix>&to=<unix>   # step 300 s, 900-10800 s, from >= 1794646800
```

### G. Python access pattern

```python
# run from C:\Users\matia\Documents\DATATHON\rawtree_team37_engine with .venv\Scripts\python.exe
from engine.rt import RawTree          # reads TEAM_ID / RAWTREE_API_KEY from .env (never print them)
rows = RawTree(timeout=30).query(sql, timeout=30, retries=0)   # -> list[dict]
```
