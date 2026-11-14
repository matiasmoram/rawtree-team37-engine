# Thompson Online Learner (t37-m4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A live recommender, `t37-m4`, that ranks with Bayesian logistic click/buy models, explores by Thompson sampling, and updates itself every ~2 min from `team_37.feedback`, on request shard 1 of 2.

**Architecture:** New package `recsys/thompson/` with small single-purpose modules: a slim live state (catalogue, stock, bought sets, user/item stats, co-views) refreshed by deltas; a feature builder; a diagonal-Gaussian Bayesian logistic model; a ranker (candidates → bans → greedy slot fill); a learner thread; guards; a serving loop; a KPI report. Serving, stock, learning and pushing run on separate threads.

**Tech Stack:** Python 3 in `~/Desktop/4t/.venv`, numpy, scipy, pandas, requests; tests with stdlib `unittest` (pytest is not installed — do not install it).

**Spec:** `docs/superpowers/specs/2026-11-14-thompson-learner-design.md`

## Global Constraints

- Model version string: `t37-m4` (opaque; never reveal the method in the name).
- Ownership: `int(hashlib.md5(request_id.encode()).hexdigest()[:8], 16) % 2 == 1` (shard 1 of 2, engine-compatible).
- Deadline: drop answers older than `DEADLINE_S = 2.8` s from request ts (server clock).
- Every answer: exactly 10 distinct product_ids, all known and in stock, none bought by the user.
- Learn only from feedback rows with request ts ≤ now − 6 min.
- Objective: greedy per-slot max P(buy); near-tie (within 5%) → higher P(buy)·price^0.1.
- Defaults: σ_u = 0.5, half-life 3 h, redraw 5 s, clip k = 4, update every 120 s, collision stop > 5%.
- Read-only SQL (`recsys.data.sql`); the only writes are inserts into `team_37.submissions`.
- Stop: file `STOP_SUBMIT` in repo root (note: it exists now; serving refuses to start while it exists — the user deletes it).
- No network in unit tests; tests build synthetic `LiveState` objects.

## Review Focus

1. A new product (from `catalog_updates` after startup) appears in a request's recent_views or as a candidate → must be indexed and scored, not crash or be silently dropped (Task 1 test `test_new_product_delta_is_indexed`).
2. A user who bought an item through *our* list a few seconds ago → banned on their next request (Task 1 test `test_live_purchase_bans_item`).
3. Candidate pool smaller than 10 after bans/stock (home page, new user, empty session) → still 10 valid items (Task 4 test `test_fill_when_pool_small`).
4. Feedback batch with an unknown product or empty shown list, or a NaN in an update → posterior unchanged and learner keeps running (Task 3 test `test_update_rejects_nonfinite`, Task 5 test `test_bad_rows_skipped`).
5. Server returns no requests / API errors for minutes → serving loop and learner survive and resume (Task 7 test `test_poll_error_survives`).

---

### Task 1: Live state with deltas

**Files:**
- Create: `recsys/thompson/__init__.py` (empty), `recsys/thompson/state.py`
- Test: `tests/test_thompson_state.py`

**Interfaces:**
- Produces:
  - `class LiveState` with attributes: `pid2i: dict[str,int]`, `items: pd.DataFrame` (cols product_id, category, subcategory, price, cat, sub, new, logp), `oos: set[int]`, `bought: dict[str,set[int]]` (user_id → item idx), `ucat: dict[str, np.ndarray]` (user_id → share per category, sums to 1), `bought_sub: dict[str,set[int]]`, `cov: dict[int, list[int]]` (item → top co-viewed items), `cat_best: dict[int, list[int]]` (category → items by logp desc), `sub_best: dict[int, list[int]]`.
  - `LiveState.from_frames(catalog, updates, purchases, user_cat, item_stats, coview) -> LiveState` (pure, used by tests).
  - `LiveState.load() -> LiveState` (pulls fresh from RawTree: catalogue + all `catalog_updates`; history caches `data/purchases.pkl`, `user_cat.pkl`, `item_stats.pkl`, `coview.pkl`; live purchases from `shop.events` since 2026-11-14).
  - `apply_updates(rows: pd.DataFrame) -> int` (new_product appends an item and indexes it; price_change sets price; out/back_in_stock edits `oos`).
  - `apply_purchases(rows: pd.DataFrame) -> int` (user_id, product_id → `bought`, `bought_sub`).
  - `refresh_loop(stop: threading.Event)` — every 20 s purchases delta, every 60 s updates delta (watermarks on ts); errors logged, never raised.

- [ ] **Step 1: Write failing tests** in `tests/test_thompson_state.py` using tiny frames (3 categories, ~20 items):
  - `test_new_product_delta_is_indexed`: after `apply_updates` with a `new_product` row, `pid2i` contains it, `items.new` is True, it appears in `cat_best[its cat]`.
  - `test_live_purchase_bans_item`: `apply_purchases` adds idx to `bought[user]` and its subcategory to `bought_sub[user]`.
  - `test_stock_toggle`: out_of_stock then back_in_stock leaves `oos` without it.
  - `test_ucat_shares_sum_to_one`: weight v + 3c + 10p, shares sum to 1 per user.
- [ ] **Step 2: Run** `python -m unittest tests.test_thompson_state -v` → FAIL (module missing).
- [ ] **Step 3: Implement** `recsys/thompson/state.py` per Interfaces. logp = log1p(history purchases); new products get logp = mean logp of their subcategory (cold prior).
- [ ] **Step 4: Run** the tests → PASS.
- [ ] **Step 5: Commit** `feat(thompson): live state with catalogue/purchase deltas`.

### Task 2: Feature builder

**Files:**
- Create: `recsys/thompson/features.py`
- Test: `tests/test_thompson_features.py`

**Interfaces:**
- Consumes: `LiveState` (Task 1).
- Produces:
  - `CLICK_FEATURES: list[str]`, `BUY_FEATURES: list[str]` (names, fixed order; used for logging weight trajectories).
  - `class Req` (dataclass): request_id, ts (pd.Timestamp), user_id, is_new_user, page, views (list[int] oldest→newest, only views with ts < request ts), cold (bool), served_by_fallback (bool, default False). `Req.from_row(row: dict, st: LiveState) -> Req`.
  - `click_matrix(st, req, items: np.ndarray, slots: np.ndarray) -> np.ndarray` shape (len(items), len(CLICK_FEATURES)).
  - `buy_matrix(st, req, items) -> np.ndarray` shape (len(items), len(BUY_FEATURES)).
- CLICK_FEATURES (exact order): `bias, slot_1..slot_10` (one-hot), `earlier_viewed, last_viewed, earlier_viewed_top3, last_viewed_top3, sess_cat_share, same_last_sub, hist_cat_share, bought_same_sub, logp_in_sess_cat, logp_out_sess_cat, log_price, log_price_ratio, log_price_ratio_sq, new_item, cold, page_home, page_category, nviews_0, nviews_1_3, served_by_fallback`. Price ratio = log(price / last-viewed price), 0 if no views.
- BUY_FEATURES: `bias, log_price, cold, page_home, viewed`.

- [ ] **Step 1: Write failing tests**: `test_shapes_and_names`; `test_last_viewed_flags` (item = last view → last_viewed=1, earlier_viewed=0, top3 flag only when slot ≤ 3); `test_future_views_dropped` (view ts ≥ request ts ignored); `test_no_views_price_ratio_zero`; `test_unknown_view_ignored`.
- [ ] **Step 2: Run** `python -m unittest tests.test_thompson_features -v` → FAIL.
- [ ] **Step 3: Implement**, vectorised over items with numpy.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(thompson): click/buy feature builder`.

### Task 3: Bayesian logistic model with Thompson draws

**Files:**
- Create: `recsys/thompson/model.py`
- Test: `tests/test_thompson_model.py`

**Interfaces:**
- Produces:
  - `class BayesLogit(dim, prior_var=1.0)`: `m: np.ndarray`, `q: np.ndarray` (precisions); `fit(X, y, iters=20)` (batch MAP by Newton/IRLS on diagonal precision, then q = q0 + Σ p(1−p)x²); `update(X, y) -> bool` (Chapelle & Li 2011 Algorithm 3: per batch, minimise ½Σq(w−m)² + log-loss, new q += Σ p(1−p)x²; returns False and leaves state untouched if any result is non-finite); `decay(factor)` (q ← q·factor, floored at prior precision); `sample(rng) -> np.ndarray`; `clip_to(anchor: "BayesLogit", k=4)` (m within anchor.m ± k/√anchor.q).
  - `class ItemOffsets(sigma=0.5)`: per-item mean/precision dict; `update(items, X_resid_logit, y)` with the same Chapelle–Li rule (1-dim); `sample(items, rng)`, `mean(items)`; unknown items → 0.
  - `class Posterior`: holds `click: BayesLogit`, `buy: BayesLogit`, `items: ItemOffsets`, `anchor` (frozen copy of the starting click/buy), `version: int`; `save(path)`, `Posterior.load(path)`; `draw(rng) -> Draw` where `Draw` has `wc, wb, item_offset(items)->np.ndarray`, `id: int`; `mean_draw() -> Draw`.
  - `p_buy(draw, Xc, Xb, items) -> np.ndarray` = σ(Xc·wc + offset) · σ(Xb·wb).

- [ ] **Step 1: Write failing tests**: `test_fit_recovers_weights` (synthetic 20k rows, 3 features, true w=[−3,1.5,−1] → |m−w| < 0.15); `test_update_moves_toward_truth` (fit on 2k, update on 20k in 10 batches → error shrinks); `test_update_rejects_nonfinite` (X with NaN → returns False, m and q unchanged); `test_decay_floor`; `test_sample_spread_shrinks_with_data`; `test_clip_to_anchor`; `test_save_load_roundtrip`.
- [ ] **Step 2: Run** `python -m unittest tests.test_thompson_model -v` → FAIL.
- [ ] **Step 3: Implement.** Batch update: a few Newton steps on the diagonal objective (it is separable after linearisation); keep it numpy-only.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(thompson): bayesian logistic posterior with thompson draws`.

### Task 4: Candidates and ranker

**Files:**
- Create: `recsys/thompson/ranker.py`
- Test: `tests/test_thompson_ranker.py`

**Interfaces:**
- Consumes: `LiveState`, `Req`, `click_matrix`, `buy_matrix`, `Draw`, `p_buy`.
- Produces:
  - `candidates(st, req, cap=200) -> np.ndarray` (order: viewed; `sub_best` of session subcategories (40 each); co-views of viewed (30 each); `cat_best` of session categories (40 each, new items first among ties); top-3 history categories from `ucat` (30 each); if still < 60: global `cat_best` round-robin). Deduplicated, capped.
  - `banned(st, req) -> set[int]` = bought[user] ∪ oos.
  - `rank(st, req, draw, rng=None) -> list[int]` (10 item idx): remove banned; compute P(buy) per candidate per slot 1..10 (`click_matrix` with that slot); greedy slot fill; near-tie rule: if second-best P(buy) ≥ 0.95 × best, pick larger P(buy)·price^0.1; if fewer than 10, fill from `cat_best` across categories skipping banned/used.
- [ ] **Step 1: Write failing tests**: `test_never_bought_or_oos`; `test_ten_distinct`; `test_fill_when_pool_small` (new user, home page, no views, 15 of 20 items banned → still 10 valid... use a 30-item catalogue with 18 banned); `test_viewed_item_goes_top_when_weight_high` (draw with big `earlier_viewed_top3` → earlier-viewed item in slot 1–2); `test_near_tie_prefers_pricier`; `test_new_product_candidate` (new product in session category can appear).
- [ ] **Step 2: Run** `python -m unittest tests.test_thompson_ranker -v` → FAIL.
- [ ] **Step 3: Implement.** Score all slots in one matrix call (stack candidates × 10 slots) to stay < 50 ms for 200 candidates.
- [ ] **Step 4: Run** → PASS; also assert in a test that `rank` on 200 candidates takes < 50 ms (`test_rank_fast`).
- [ ] **Step 5: Commit** `feat(thompson): candidates and greedy slot ranker`.

### Task 5: Initial fit and learner

**Files:**
- Create: `recsys/thompson/learner.py`
- Test: `tests/test_thompson_learner.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `rows_to_training(st, rows: pd.DataFrame) -> tuple[Xc, yc, items, Xb_clicked, yb]` — rows have request_id, ts, user_id, is_new_user, context, recent_views, shown, clicked, purchased, served_by. One row per shown item with its slot; drops items bought by the user (ban rule), unknown products, rows with empty/invalid shown. Buy model rows = clicked items only (y = purchased == clicked).
  - `initial_fit(st, rows) -> Posterior` (fit click, buy, item offsets; anchor = copy).
  - `FEEDBACK_SQL` joining `team_37.feedback` with `shop.requests` on request_id, for `ts` in (watermark, now64 − 6 min].
  - `class Learner(st, post, path, half_life_h=3.0, every_s=120)`: `step(rows) -> dict` (decay by 0.5^(Δt/half_life), update click/buy/items, clip_to anchor, bump version, save; returns stats incl. n rows, ok flag); `loop(stop)` (query → step; exceptions logged, never raised); thread-safe `current() -> Posterior` (swap reference under a lock).
  - CLI: `python -m recsys.thompson.learner --init` pulls all feedback so far, runs `initial_fit`, saves `models/thompson/posterior_init.pkl` and `posterior_latest.pkl`, prints named weights.
- [ ] **Step 1: Write failing tests** with synthetic rows: `test_rows_to_training_slots_and_ban`; `test_bad_rows_skipped` (unknown pid, empty shown, NaN price → skipped, no exception); `test_step_saves_and_bumps_version`; `test_step_nonfinite_keeps_last_good`.
- [ ] **Step 2: Run** `python -m unittest tests.test_thompson_learner -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Run the real initial fit:** `python -m recsys.thompson.learner --init`. Expected: prints ≥ 400k click rows, weights with `last_viewed_top3` and `earlier_viewed_top3` > 0, `slot_10` < `slot_1`; files exist in `models/thompson/`.
- [ ] **Step 6: Commit** `feat(thompson): initial fit and online learner` (do not commit `models/thompson/*.pkl` if `.gitignore` excludes models; check).

### Task 6: Guards

**Files:**
- Create: `recsys/thompson/guards.py`
- Test: `tests/test_thompson_guards.py`

**Interfaces:**
- Produces:
  - `owns(request_id: str, shard: int = 1, count: int = 2) -> bool` (engine contract).
  - `collision_rate(sub_rows: pd.DataFrame, version: str) -> float` — sub_rows: request_id, mv; among request_ids we own that `version` answered, share also answered by another mv.
  - `COLLISION_SQL` (last 5 min of `team_37.submissions` joined to `shop.requests` ts).
  - `class PerfGuard`: `observe(window_ours: float, window_ctrl: float, n_ours: int) -> str` returning `"ok" | "reset" | "stop"`; two consecutive losing 30-min windows with n_ours ≥ 300 → "reset" (first time), again → "stop"; a winning window resets the losing streak.
  - `leaderboard_windows(version, ctrl_version_prefix="t37-") -> tuple[float,float,int] | None` using `GET {API}/api/state?by=model&from=&to=` (30-min window ending now); control = best other `t37-` version with ≥ 300 requests; None on error.
- [ ] **Step 1: Write failing tests**: `test_owns_matches_engine` (compare with `int(md5[:8],16) % 2` on 1,000 ids; both shards partition the set); `test_collision_rate`; `test_perfguard_sequence` (lose, lose → reset; lose, lose → stop; lose, win, lose → ok).
- [ ] **Step 2: Run** `python -m unittest tests.test_thompson_guards -v` → FAIL.
- [ ] **Step 3: Implement.** Check the real `/api/state` JSON shape once by hand (`curl` with the API key header) before writing the parser; document the fields used in a comment.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(thompson): ownership, collision and performance guards`.

### Task 7: Serving loop

**Files:**
- Create: `recsys/thompson/serve.py`
- Test: `tests/test_thompson_serve.py`

**Interfaces:**
- Consumes: everything above; reuse `NEW_REQUESTS`, `OUT_OF_STOCK`, `DEADLINE_S`, `session()` from `recsys/submit.py` (import, do not copy).
- Produces: `class Server(version="t37-m4", shard=1, count=2, guard=True, dry_run=False)`; `answer(df: pd.DataFrame) -> list[dict]` (pure given state/posterior: ownership filter → `rank` with current draw → fallback chain posterior-mean → anchor → `cat_best` fill; never raises); `run(minutes)`; CLI `python -m recsys.thompson.serve [--minutes 900] [--no-guard] [--dry-run]`.
- Threads: poll (main, 0.25 s), stock (3 s, updates `st.oos`), state refresh (`st.refresh_loop`), learner (`Learner.loop`), draw refresher (every 5 s `post.draw(rng)`), 4 push workers (same merge/deadline-drop logic as `submit.py`), guard thread (every 5 min collision check; every 30 min `PerfGuard`; "reset" → learner resets posterior to anchor; "stop" → write `STOP_SUBMIT`).
- Refuses to start if `STOP_SUBMIT` exists or startup collision rate > 5%.
- Logs: `data/thompson_serve.pkl` (request_id, ts, items, draw id, posterior version, fallback level, latency, status) every minute; console line per minute like `submit.py.report`, plus posterior version and learner rows.
- [ ] **Step 1: Write failing tests** (no network; inject a fake state/posterior): `test_answer_only_owned_requests`; `test_answer_valid_lists`; `test_answer_fallback_on_exception` (rank raises → still 10 valid items, fallback level 1); `test_poll_error_survives` (fake http raising for 3 polls then returning rows → answers produced).
- [ ] **Step 2: Run** `python -m unittest tests.test_thompson_serve -v` → FAIL.
- [ ] **Step 3: Implement** with `http`/`now` injectable for tests.
- [ ] **Step 4: Run** → PASS, then full suite `python -m unittest discover -s tests -p "test_thompson_*.py" -v` → all PASS.
- [ ] **Step 5: Dry run live** (no inserts): `python -m recsys.thompson.serve --dry-run --minutes 2`. Expected: ~50% of polled requests answered, 0 invalid lists, local p95 < 200 ms, learner logs at least one step.
- [ ] **Step 6: Commit** `feat(thompson): serving loop with learner, guards and logging`.

### Task 8: KPI report and go-live

**Files:**
- Create: `recsys/thompson/report.py`
- Modify: spec §6.6 command → `python -m recsys.thompson.report`

**Interfaces:**
- Consumes: `leaderboard_windows`-style API calls (Task 6), `data/thompson_serve.pkl`, posterior snapshots in `models/thompson/`.
- Produces: CLI printing, per 15-min window since launch: `t37-m4` vs best other `t37-` version: conversion, cold conversion, on-time %, revenue/request; own-shown realised buys and clicks per 100 (feedback joined on request_id + exact list); collision rate; fallback-level counts; and a table of named weight means over posterior versions (first, every hour, latest). Writes `data/thompson_report.csv`.
- [ ] **Step 1:** Implement; run `python -m recsys.thompson.report` after dry run → prints weight table (leaderboard rows may be empty before go-live).
- [ ] **Step 2:** Copy the audit script (`$SCRATCHPAD/audit_assumptions.py`) to `explore/audit_assumptions.py`.
- [ ] **Step 3: Commit** `feat(thompson): KPI and weight-trajectory report`.
- [ ] **Morning (09:30 CET) restart for the final:** stop, restart `serve` — `LiveState.load()` re-pulls catalogue, purchases and stats; `Posterior.load(posterior_latest.pkl)` keeps tonight's learning.
- [ ] **Step 3: Go-live checklist (user actions):** teammate restarted with `--shard-index 0 --shard-count 2`; user deletes `STOP_SUBMIT`; start `python -m recsys.thompson.serve --minutes 900` in its own terminal; after 10 min, run the report and check collisions < 5%, on-time ≥ 95%, posterior version increasing.
