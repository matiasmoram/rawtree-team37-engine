# Backlog: what to do next

Prioritized from a parallel research review of the whole codebase, docs, logs and external solutions (14 November 2026, evening). Every item states the evidence and the gate that must pass first. The iteration procedure is `docs/iteration.md`.

## P0 — measurement validity (do before trusting ANY comparison)

1. **Conclude the pending merge commit.** `git status` shows `origin/main` (money/skibidy/linucb arms) merged with all conflicts resolved and staged, but the merge commit is not made. Nothing else should assume the tree.
2. **Single writer.** The 15:50-16:05 audit found 895/897 requests submitted by two distinct versions (`t37-m1`/`t37-m2`), and leaderboard CSVs at 16:14-16:25 still show `t37-lgbm-recent`, `t37-cf-v1`, `t37-cf-rot` submitting concurrently with the ev arms. Attribution noise swamps every other experiment. Coordinate one writer or mutually exclusive `--shard-index/--shard-count` ownership before the next live trial; verify with `scripts/check_emitters.py`.
3. **Resolve the allocation contradiction.** `scripts/run_live.py` defaults to `lgbm-recent:60,cf-v1:20,cf-rot:20` while `docs/review_2026-11-14.md` records a 16:09 switch to `ev-v2-nocovis:60,ev-v3:40`, and the merge resolution just removed `ev-v2-nocovis` from the registry entirely. One of these documents a retired state; write down the actually-deployed allocation in one place and make the runner default match it.
4. **Commit the working tree.** `tests/` (10 files, 125 tests, all passing), `docs/` (8 files) and the whole signal layer (calibration, cartstate, content, contextual, experiments, replay) are untracked. A lost checkout loses the safety rails.
5. **Decide `models/` policy**: currently untracked and not ignored — a `git add .` would commit regenerated binaries. Either ignore it or commit the pinned `lgbm_recent_20261114T1523.txt` that `lgbm-recent` loads (missing file = hard crash at instantiation).

## P1 — ranked experiments (highest expected value first)

| # | Experiment | Evidence | Effort | Gate |
|---|---|---|---|---|
| 1 | **Cart candidates + features into the LGBM ranker** | Carted-not-bought converts ~8x base (`cartfirst.md`), yet `engine/features.py` has zero cart inputs and never emits cart candidates; `snap.user_cart` is refreshed live every 1.5 s and now attachable offline (`iterate.py` does it) | M | `evaluate_recent.py` `online_trial_eligible` + cold segment |
| 2 | **`ev-v2-cat` as second arm** | Best ev-arm conversion in its monitor window (1.72); first offline number now exists: paired NDCG vs ev-v3 `+0.0256 [-0.016,+0.065]`, n=36 (`logs/iteration_20261114T1523.json`) — promising, insufficient | S | repeat `iterate.py` on a later untouched window; then 10-20% arm |
| 3 | **`ev-v2-tier` dedicated cold-traffic shard** | Cold conversion 1.9016 over 374 cold requests vs nocovis 1.6979 (review 15:50-16:05) | S | common-window `analyze_windows.py` comparison |
| 4 | **Register `ContextualPolicy` + add its refresh hook to `live.py`** | Built, tested (13 tests), documented — but absent from `FACTORIES` and `refresh_policy_signals`; `contextual.json` goes stale unrefreshed | S | `iterate.py` (it has rerank hooks), then home/new-user arm |
| 5 | **`ev-recent-covis` with a matrix rebuilt as-of the window** | First replay showed the current `recent_covis.json` is future-built (15:58) relative to the window → arm degenerated to base, Δ=0 exactly | S | rebuild matrix as-of before `--since` (`refresh_signals.py`), rerun `iterate.py` |
| 6 | **Bounded tail exploration (`ev-content-tail`) for real propensities** | Only source of unbiased slot-9/10 reward estimates; wrapper + metadata logging already exist | S | `promotion_gate` review; propensities enable DR/IP estimators later |
| 7 | **Hourly LGBM retrain loop with the predeclared gate** | Pipeline exists, nothing schedules it; non-stationarity documented (`live_ranker.md`) | M | sidecar sanity table + `live_check` composition before swap |
| 8 | **money-v1 / skibidy-v1 (new merged arms)** | First offline numbers: overlap with control 0.20-0.27 (very different slates), latency p95 4-16 ms, no rerank hooks → DIAGNOSTIC ONLY | S | add rerank hooks or gate via `evaluate_recent.py` before any live exposure |

## P2 — data and features (feed experiments 1 and 7)

- **Unused today, computed already**: item-level `cart_all`, `view_1d`, `view_1h`, `buy_3h` counters; carousel **clicks** (discarded in `features.py:197` and `evidence.py:58` — click-to-buy ratio is free signal); `price_changed_ts` (dead field — "hours since price change" + discount-depth flag).
- **In the training table but dropped**: `region` (feature + region×page interaction), time-of-day/daypart from `ts`, `served_by` as a weighting to down-weight fallback exposures.
- **Under-used**: full embeddings (max/mean cosine to last 1-3 views for every candidate; loader already enforces `known_at`), per-brand quality prior (mirror of `attach_sub_quality`), logged propensities for de-biased click targets.
- **Known perf debt**: `new_by_sub` cache slot in `features.py` is never populated → O(N) full-catalog scan per request, duplicated in `evidence.py:119-121`; populate in `_rank_lists` and reuse (mind the `CatalogReplay` shallow-copy path in the dataset builder).
- **OTTO top-3 transferable features** (CPU-feasible, ~25 additions): `covis_last_*` (score between last viewed item and candidate — their single best feature), `covis_buy2buy_sum` (cart→order transitions, the most conversion-aligned signal), embedding sims vs last item, `fusion_score` from candidate generation, `in_session_count`, popularity hour/day/week + ratios, source-rank binaries. Weighted-affinity schemes to add alongside the existing one: positional logspace, recency `1/log(2+Δt_min)`, type multipliers {click 1, cart 6, order 3} (and {0.5/9/0.5} for similarity features).

## P3 — code health (cheap, do between experiments)

- `id()`-keyed caches (`prepare.py`, `policies/content.py`, `policies/contextual.py`) can silently skip recompute after dict-id reuse; key on a monotonic generation counter instead.
- Catalogue-update logic triplicated (`snapshot.load_products`, `live.apply_updates`, `dataset.CatalogReplay.advance`) with visible drift (`base_price` set in one, not the others).
- `arm_bucket` in `live.py` duplicates `request_bucket` in `experiments.py`; `FACTORIES.update(VARIANTS)` ran twice in the registry (merge artifact — recheck after the pending merge).
- README is stale (no tests/learn/policies, "work in progress"); `registry.py` and `run_live.py` disagree about the deployed allocation (see P0-3).
- Engine docs to refresh: `cartfirst.md`/`review_2026-11-14.md` allocations contradict each other; `recent_evaluation.md` says "not deployed" while leaderboard CSVs show `t37-lgbm-recent` serving.

## Parking lot (documented, deliberately not built)

Thompson/Beta posterior exploration and cascade feedback (need the propensity stream from P1-6 first), Ridge/LinUCB cartfirst core (teammate branch, no mature feedback pipeline here), CB2CF text→collaborative mapping (dominated by P2 embedding features for the remaining event time).
