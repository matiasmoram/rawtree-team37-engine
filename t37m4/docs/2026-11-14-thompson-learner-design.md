# Thompson-sampling online learner (t37 "self-improving" model) — design

Date: 2026-11-14, ~18:30 CET. Final round: Sun 2026-11-15 10:00–12:00 CET.
Owner: team_37 (this machine). Code lives in `~/Desktop/4t/datathon/recsys/`.

## 1. Intent and why

Build a recommender that **keeps improving from live feedback with no code changes or restarts**: it
updates its own weights from `team_37.feedback` and explores with Thompson sampling. It runs live tonight on
half the traffic so it accumulates learning and we can fine-tune tomorrow morning before the final.

Why:
- Every hand-tuned arm so far has fixed weights; winners flip between 15-minute windows (drift, traffic mix).
- Jury awards 10/30 points for "learning from the stream"; conversion (50 pts) and cold-start conversion
  (10 pts) reward a model that adapts to new products, trends and price changes.
- The user can run models from this machine from now on; the teammate's engine keeps the other half.

## 2. Goals, non-goals, anti-goals

Goals
- Maximise expected purchases per 100 requests (leaderboard conversion), cold requests included.
- Learn continuously: weight updates every ~2 min from mature feedback, Thompson exploration in all slots.
- Answer 100% of *our* requests validly within 3 s (reliability = 10 pts).
- Log enough to show the jury how weights evolved and to measure our own conversion cleanly.

Non-goals
- Not a replacement for the teammate's engine tonight; no changes to `rawtree-team37-engine`.
- No offline counterfactual "proof" before going live; the live 50/50 comparison is the test.
- No external model calls (helmcode etc.) in the serving path.

Anti-goals (failure even if it "works")
- Answering requests owned by the teammate's shard (two writers on one request).
- Showing a product the shopper already bought (any source).
- Learning from lists we did not send as if we had sent them, or letting exploration rediscover re-buys.
- Late answers because learning or data refresh blocks the serving thread.
- A model name that reveals the method (use opaque `t37-m4`, next `t37-m5`, ...).

## 3. Evidence the design rests on (audit of 51,486 live requests, 514,860 impressions, 549 buys)

Rates are buys per 1,000 impressions. Full output: scratchpad `audit/report.txt`; script
`audit_assumptions.py` (copy into `explore/` when implementing).

| Fact | Numbers | Consequence |
|---|---|---|
| Slot curve | s1 4.5, s2–3 1.4, s4–6 0.7, s7–10 0.3 | slot is a feature; order by score |
| Already bought (exact product) | 1 buy / 24.5k impressions; bought-live 0 / 2.1k | hard ban, never learned. Organisers confirm (17:05 CET) the rule covers organic *and* our-list purchases |
| Same subcategory as a bought item | s1 7.2 vs 3.7 | do **not** suppress siblings; affinity feature instead |
| Viewed items | s1: earlier-viewed 19.4, last-viewed 10.2, other 4.2; no effect below slot 3 | viewed features × top-slot interaction |
| Session × history category | session-cat 4.3–5.3; history share non-monotone | session strong, history a modest feature |
| Popularity | inside last-viewed category steep (s1 0.4 → 13.1); outside flat ~0.9 | popularity only interacted with "in session category" |
| Price | much cheaper than viewed (same subcat) 3.3 vs ~1.2; >€100 converts 1.48 | price-ratio and log-price features; revenue tie-break is cheap |
| New products / cold | new item s1 7.2 vs 4.7; cold requests 1.61 vs 0.78 warm | new-item and cold features |
| Page | home 0.35, product 1.25, category 1.24 | page feature; home candidates from user history |
| Purchase always follows a click on the same item | 549/549 | factor P(buy) = P(click) · P(buy\|click) |
| Conversion per click | ≈0.33, flat slots 1–6 | P(buy\|click) needs few features |
| Feedback latency | feedback lands ≈6 min after the request | learn only from rows ≥6 min old |

## 4. Approaches considered

1. **Bayesian logistic regression + Thompson sampling (chosen by the user).** Posterior over interpretable
   feature weights plus shrunk per-item offsets; draw weights every few seconds; online updates from
   feedback. Exploration is proportional to uncertainty in every slot and fades/reappears automatically.
2. Fixed small swaps (ε = 10% into slots 2–4, logged propensities). Clean off-policy evaluation, but slower
   learning and a hand-tuned rate. Rejected.
3. Separate `_explore` version on ~15% of traffic. Protects the main score but that share scores poorly
   and still counts for the team. Rejected.
4. (Context) Periodic LightGBM retrain like the engine's `lgbm-recent`: learns, but in batches, with
   popularity features the lab judge showed inflate exposure bias, and no exploration. Not chosen.
5. (Context) Exploration only in slots 9–10: rejected after measuring ~7 buys/hour there.

## 5. Decisions made with the user

- **Learner:** Thompson sampling over Bayesian weights (option A).
- **Objective:** rank by pure P(buy). Price only breaks **near-ties**: among items whose P(buy) is within 5%
  of each other, order by P(buy) · price^0.1 (fixed α = 0.1, not learned). (User chose this over a constant
  price^0.1 multiplier, which would tilt every slot toward expensive items.)
- **Final-round traffic split:** decided by the user tomorrow morning from the model's KPIs (§6.6 must
  deliver them). Not decided now.
- **Unattended running:** not known yet; the automatic guard (§6.7) is built and on by default so it is
  safe either way.
- **Re-buys:** hard ban on the exact product only; siblings stay eligible.
- **Traffic tonight:** 50/50 split by request hash with the teammate's best engine arm (option B).
- **Runs on this machine**, via our own submitter, not inside the teammate's engine.
- **Learns from all team feedback** (every shown list is valid evidence); judges *its own* performance only on
  requests where the shown list equals the list it sent.

## 6. Design

### 6.1 Request ownership (must match the engine's contract)
The engine claims requests with `int(md5(request_id).hexdigest()[:8], 16) % shard_count == shard_index`
(`engine/experiments.py: request_bucket`). Our current `submit.py` uses a *range* on `% 1000 / 1000`,
which would overlap. The new model must use the engine's rule: **we own shard 1 of 2**; the teammate runs
`run_live.py --shard-index 0 --shard-count 2` (coordinate before starting). `t37-m1..m3` stay off.

### 6.2 Model
- P(click at slot s | request, item) = σ(w_c · x + u_i), P(buy | click) = σ(w_b · z).
- x (click features): slot one-hot (10) ; earlier-viewed, last-viewed, each × top-slot (s ≤ 3) ;
  session category share; same last-viewed subcategory; user history category share; bought-same-subcategory;
  log popularity × in-session-category; log price; log(price / last-viewed price) and its square;
  new item; cold request; page one-hot; nviews bucket; bias.
- z (buy-given-click): bias, log price, cold, page, viewed (few features; ~550 buys).
- u_i: per-item click offset, prior N(0, σ_u²), only items with exposures get a posterior entry.
- Posterior: diagonal Gaussian (Laplace / online Bayesian logistic regression, e.g. Chapelle & Li 2011),
  per-weight mean m and precision q.
- Initialisation: fit on all existing live feedback (≈515k impressions) excluding bought items; this is the
  starting posterior and the "frozen start" for safety resets.

### 6.3 Learning loop (background thread, never blocks serving)
- Every ~120 s: query `team_37.feedback` rows with ts in (last_seen, now − 6 min]; rebuild features for each
  shown item **as of request time** (bought set, viewed items, stock); one online-Bayes update per row.
- Forgetting: before each update, scale precisions by a decay giving a half-life of a few hours (builder
  picks ≈3 h, configurable) so the model follows drift.
- Safety: weights clipped to ±k prior std of the starting posterior; non-finite update → keep last good
  posterior; persist posterior to `models/thompson/posterior_<ts>.pkl` every update (restart resumes).

### 6.4 Serving (per request, inside the 3 s budget)
1. Ownership check (6.1); skip if not ours.
2. Candidates (~150–200): viewed items; top items in session subcategories and categories (by in-category
   popularity); co-views of viewed items; new products in session categories; user's top history categories;
   home with no session → best sellers within user history categories, else global in-category best sellers.
3. Remove: bought by this user (history + live organic + purchases from our/any shown list), out-of-stock
   (stock thread), duplicates.
4. Score with the current **Thompson draw** of weights (redrawn every few seconds, not per request, to keep
   cost low); P(buy) = P(click | slot) · P(buy | click). Because viewed × top-slot terms make scores
   slot-dependent, fill **greedily slot by slot**: slot 1 gets the candidate with the highest P(buy at slot 1),
   remove it, slot 2 the highest P(buy at slot 2), and so on. Near-tie rule (builder's call on mechanics):
   when the top two remaining candidates for a slot are within 5% in P(buy), take the higher P(buy)·price^0.1.
5. Fill to 10 distinct in-stock items from in-category best sellers if short.
6. On any exception: rank the same candidates with the **posterior mean**; if that fails, starting-posterior
   ranking; never send nothing.
7. Drop answers already past 2.8 s (existing submitter rule).

### 6.5 Fresh state (the old lab Store froze at 13:09 — must not happen again)
- New products and price changes from `shop.catalog_updates` (delta every ≤60 s).
- Live purchases from `shop.events` (delta every ≤20 s) feeding the bought set.
- Popularity and co-views may stay at startup values tonight; refresh at restart before the final.

### 6.6 Logging and measurement
- Per request: request_id, sent list, draw id, latency, candidate count, fallback level.
- Per update: posterior snapshot (means and stds of named weights), rows used, timestamp.
- Own-performance: join feedback on (request_id, exact shown list == sent list) → realised clicks/buys per
  100 on our shown requests; compare against leaderboard `/api/state?by=model` for `t37-m4` vs the engine arm in
  common 15-min windows.
- A small script prints weight trajectories (for the jury "learning from the stream" slide).
- **Morning KPI report** (`python -m recsys.thompson.report`), for the user's final-split decision: per
  15-min window since launch, `t37-m4` vs the engine arm on leaderboard conversion, cold conversion, on-time
  %, revenue/request (from `/api/state?by=model&from&to`), plus our realised buys/clicks per 100 on
  own-shown requests, collision rate, fallback-level counts, and the weight trajectories.

### 6.7 Guards (on by default; Claude's calls)
- **Double-writer guard:** at startup and every 5 min, check `team_37.submissions` for our shard's requests
  answered by any other model_version in the last 5 min. If > 5% collide, stop submitting and log why
  (the teammate may not have restarted on shard 0 yet).
- **Performance guard (for unattended nights):** if our leaderboard conversion is below the engine arm's
  in two consecutive 30-min windows (each ≥ 300 of our requests), reset the posterior to the frozen start
  and log it; if the frozen start then also loses two consecutive windows, stop submitting (requests fall
  to the fallback) and write `STOP_SUBMIT`. Flag `--no-guard` disables it when someone is watching.
- **Fallback rows:** feedback rows served by the organisers' fallback are used for learning, with a
  `served_by_fallback` feature so their different list distribution does not distort the other weights.
- **Carry-over to the final (Claude's call):** keep the persisted posterior (forgetting already discounts
  old evidence); at 09:30 CET restart with fresh catalogue, purchases, popularity and co-views.

## 7. Constraints
- 3 s deadline from request ts; RawTree API is the bottleneck (queries 0.2–5 s). Serving and learning on
  separate threads; heavy queries never on the serving thread.
- One writer per request (6.1). Opaque model name. Stop via `STOP_SUBMIT` file.
- Python env `~/Desktop/4t/.venv`; credentials in `datathon/.env` (never committed).

## 8. Left to the builder
- Exact prior variances, decay half-life, redraw interval, clip k (start: σ_u = 0.5, half-life 3 h,
  redraw 5 s, k = 4) — mark as tunable constants.
- Whether to reuse `recsys/features.py` Store or a slimmer live feature builder, as long as 6.5 holds.
- Candidate pool sizes per source.
- Test layout (unit tests for ownership hash parity, bought ban, valid 10 lists, update math on synthetic
  data, fallback path).
