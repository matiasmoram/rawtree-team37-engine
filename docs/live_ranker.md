# Live-feedback LightGBM ranker

Goal: learn the ranking score directly from our own live feedback (`team_37.feedback`), not from the old
logged carousel data. The old data misled us on repurchases.

Code: `engine/learn/` (dataset, training, scoring, live check), `engine/policies/lgbm.py` (serving policy),
`scripts/train_live_ranker.py` (CLI). Every model is a LightGBM text file plus a JSON sidecar with the same stem.

## 1. Training data

One row per item the shopper actually saw (`feedback.shown`, 10 per request), labelled `click` and `purchase`
(`purchased` is always the clicked id when set). Sources:

- `team_37.feedback`, excluding `__init__`. Both `served_by='team'` and `served_by='fallback'` rows are used.
  The label is defined on `shown`, so a fallback row is a valid labelled exposure of the fallback list.
- `shop.requests`, to rebuild the `Request` (user, context, `recent_views`).
- `team_37.submissions`, for `any(model_version)` per request.

Features are exactly the serving features: `engine.features.featurize(ctx, snap, shown, slots=[0..9])`.
`slot` is a feature, so position bias is absorbed during training. Serving scores every candidate at `slot=0`.

### No leakage

Every feature uses only data strictly before the request ts:

- **One snapshot at T0 = `--since`.** It holds user histories, co-visitation, item counters and carousel stats.
  Every training request is at or after T0.
- **Point-in-time catalogue.** Catalogue updates with ts in [T0, request ts) are replayed in order on a private
  copy of the products: prices, stock and new products. The live `stock` thread does the same.
- **Point-in-time recent purchases** (`bought_in_event`). These are purchases in [ts - 6 h, ts) from
  `shop.events`, plus our own feedback purchases with feedback ts < request ts. This uses the same sources and
  lookback as the live `RECENT_BUYS_SQL`.

**Staleness trade-off.** One snapshot at T0 guarantees no future data. The cost is that snapshot features get
older along the range. At the end of a 2 h window they are 2 h old, while live refreshes item counters every
minute and rebuilds user tables every hour. Fast-moving features are therefore older in training than in
serving: `log_view_3h`, `log_trend`, `log_buy_1d`, and the histories of users active during the window. Keep the
window short (at most 3-6 h) and roll T0 forward (see §6). A purchase made after T0 is missing from
`user_bought_n`, but `bought_in_event` covers it as long as the window is at most 6 h.

Cache: `cache/live_ds_v1_<since>_<until>.pkl`. A build takes about 15 s once the snapshot exists. Building a
new snapshot takes 4-7 min.

## 2. Models

| model | target | rows |
|---|---|---|
| click | P(click \| x, slot) | every shown item |
| purchase | P(purchase \| x, slot) | every shown item |
| factored | P(click \| x, slot) * P(purchase \| click, x) | click model + second stage fitted on clicked items only |

- **Second stage P(purchase | click).** The candidates are a smoothed constant rate and logistic regressions
  with strong L2 (C = 0.01 or 0.1) on z-scored features clipped to ±5. The winner is the one with the lowest
  validation log loss on clicked rows.
- **Split.** Requests are ordered by ts. The earliest 75 % train and the last 25 % validate. The split is
  time-strict (train ts < cutoff <= validation ts) and never random.
- **Search.** A grid of 12 conservative configurations: `num_leaves` in {7, 15, 31}, `min_data_in_leaf` in
  {200, 800}, `lambda_l2` in {1, 20}. Fixed settings: `learning_rate` 0.03, `feature_fraction` 0.8,
  `bagging_fraction` 0.8, early stopping (100 rounds) on the validation slice. The grid is searched separately
  for the click model and the purchase model, and the winner is chosen by validation log loss.
- **Position.** `slot` has a monotone non-increasing constraint. Examination can only fall with position. The
  constraint stops the trees from learning slot-specific bumps, for example a fixed fallback list that always
  shows the same item in slot 9.
- **Serving choice.** The rule is fixed in advance: serve the factored model unless the purchase model's
  validation purchase AUC is higher by more than 0.01. The factored model learns from about 3x more positives.
- **Final refit.** The served models are refitted on all rows with the chosen parameters and
  `best_iter * n_all / n_train` rounds.

## 3. Validation (run of 14:25 UTC)

**Data.** Requests from 12:10:00 to 14:25:14: 24 342 requests, 243 420 rows, 636 clicks, 198 purchases. Of the
rows, 183 100 come from team lists and 60 320 from fallback lists. No shown item was missing from the catalogue.

**Split.** Cutoff 13:51:25.
- Train: 18 256 requests, 483 clicks, 154 purchases.
- Validation: 6 086 requests, 153 clicks, 44 purchases.

**Metric definitions.**
- AUC and log loss are pooled over validation rows, scored at their logged slot.
- Ranking metrics re-rank each validation request's shown items by the score at slot 0. Ties break by logged
  slot.
- `top3` is the share of requests whose clicked or purchased item lands in the model's top 3 of the shown 10.
  NDCG@10 has one relevant item per request.

| model | clk AUC | clk LL | buy AUC | buy LL | clk NDCG | clk top3 | buy NDCG | buy top3 |
|---|---|---|---|---|---|---|---|---|
| logged order | | | | | 0.614 | 0.575 | 0.692 | 0.750 |
| slot-only (train rates) | 0.674 | 0.01698 | 0.760 | 0.00565 | 0.614 | 0.575 | 0.687 | 0.750 |
| relation rates (train) | 0.700 | 0.01716 | 0.747 | 0.00621 | 0.590 | 0.562 | 0.651 | 0.705 |
| click lgbm | 0.828 | 0.01528 | 0.916 | | 0.621 | 0.647 | 0.668 | 0.659 |
| purchase lgbm | 0.815 | | 0.912 | 0.00475 | 0.621 | 0.569 | 0.684 | 0.659 |
| **factored (served)** | 0.828 | 0.01528 | 0.917 | 0.00469 | 0.621 | 0.667 | 0.686 | 0.705 |

Random order gives top3 = 0.30 and NDCG of about 0.39. The slot-only ranking is the logged order wherever the
per-slot rates are monotone, which is why the two rows almost coincide.

Paired bootstrap (2 000 resamples of requests), factored minus logged order:

| metric | difference | 95 % CI |
|---|---|---|
| click NDCG | +0.007 | [-0.044, +0.056] |
| click top3 | +0.092 | [-0.007, +0.190] |
| purchase NDCG | -0.006 | [-0.100, +0.085] |
| purchase top3 | -0.045 | [-0.205, +0.114] |

**Reading.**
- The learned model clearly beats position-only and relation-only baselines on pooled AUC and log loss.
  Click AUC is 0.83 against 0.67-0.70.
- Inside the shown 10, it is better than the logged order at putting the clicked item in the top 3. The CI only
  just touches 0.
- On purchases it is not distinguishable from the logged order, with only 44 purchases.
- An earlier run gave factored minus logged purchase NDCG of +0.10, CI [-0.01, +0.21]. That run used cutoff
  13:44, 22 731 requests and no monotone constraint. Single-run purchase comparisons are noise at this sample
  size.
- Pooled purchase AUC (about 0.92) is inflated by easy negatives. About 18 % of validation rows are items the
  user already bought, which almost never convert. Judge the model by the within-request metrics.

Selected hyperparameters:
- Click model: `num_leaves=7, min_data_in_leaf=200, lambda_l2=20`, 370 rounds on validation, 493 after refit.
- Purchase model: `num_leaves=15, min_data_in_leaf=200, lambda_l2=1`, 158 rounds on validation, 211 after refit.
- P(purchase | click): logistic regression with C=0.01. Validation log loss 0.545 against 0.602 for the
  constant rate.

## 4. What the model learns

Gain importance, final click model: `user_cat_share` 17.8 %, `slot` 13.3 %, `user_bought_n` 8.8 %,
`log_price_vs_user` 5.7 %, `q_organic` 5.3 %, `covis_vb_rank` 4.7 %, `log_price_vs_sub` 4.7 %, `covis_vb` 4.4 %,
`user_sub_share` 4.1 %, `is_new_user` 3.4 %, `q_carousel` 3.4 %, `sess_cat_share` 3.1 %, `user_viewed_n` 2.7 %,
`log_buy_1d` 2.1 %, `log_buy_7d` 1.9 %.

The model is driven by:
1. Category affinity from the user's history.
2. Position.
3. "Already bought", which is strongly negative.
4. Price relative to the user's usual price.
5. Item quality.
6. Co-visitation with the session.

Sanity checks on the served models measure the mean SHAP log-odds on rows with the property minus rows without,
at slot 0:

| property | click | purchase | expected |
|---|---|---|---|
| user bought the item before | -1.67 | -1.24 | negative: OK |
| last viewed item | +0.59 | +0.42 | positive: OK |
| viewed earlier in the session | +0.54 | +0.53 | positive: OK |
| user viewed it before (history) | +0.40 | +0.51 | positive: OK |
| same subcategory as last view | +0.04 | +0.01 | positive (weak): OK |
| bought during the event (`bought_in_event`) | unused | unused | the trees never split on it |

- `bought_in_event` covers 1 746 rows with 7 clicks and 1 purchase, and most of these rows are also
  `user_bought_n > 0`. The policy therefore applies its own bought penalty to both signals (§5).
- Position curve: the same rows are scored at every slot. POSITION_CURVE

Score at slot 0 by relation, final served model, all rows. `slot1` is the share of that relation's exposures
that were in slot 1.

| relation | rows | slot1 | buys | observed buy % | score@slot0 % |
|---|---|---|---|---|---|
| viewed_last | 2 598 | 0.20 | 6 | 0.23 | 0.24 |
| viewed_earlier | 2 701 | 0.09 | 9 | 0.33 | 0.36 |
| user_viewed (history) | 13 291 | 0.13 | 38 | 0.29 | 0.47 |
| same_cat | 17 354 | 0.04 | 33 | 0.19 | 0.48 |
| same_sub | 68 391 | 0.15 | 63 | 0.09 | 0.19 |
| other | 76 719 | 0.05 | 36 | 0.05 | 0.13 |
| other_home | 40 613 | 0.09 | 12 | 0.03 | 0.08 |
| user_bought | 21 753 | 0.14 | 1 | 0.005 | 0.04 |

The order is sensible: bought items are last, and history views and session views are on top. Two
qualifications apply:

- **Session views rest on very little data.** Before the 13:44-13:51 switch to the ev policies, the old policies
  almost never showed them: 163 exposures of `viewed_*` items in the first 75 % of the data. All of what the
  model knows about them comes from about 5 000 exposures and 15 purchases.
- **`same_cat` at slot 0 is an extrapolation.** Only 4 % of `same_cat` exposures were in slot 1, so its slot-0
  score depends on the position model.

## 5. Serving policy

`LgbmPolicy(name, model_path, bought_penalty=3.0)`:

1. Run `prepare_snapshot`, `build_context` and `generate_candidates`.
2. Featurize at slot 0 and score all candidates in one vectorised `predict`.
3. Apply the bought penalty and take the top 10 through `fill`.

The model is loaded once, and `predict` sits behind a lock, so pollers can share it across threads.

**Bought items.** These are items in the user's history (`user_bought_n > 0`) or bought during the event
(`bought_in_event`). Their score is divided by `bought_penalty`. A bought item therefore enters the list only
when the model scores it at least 3x the non-bought item it would displace. Use `bought_penalty=float("inf")`
for a hard exclusion.

`prepare_snapshot` adds `sub_price`, which the live runner does not attach on its own. Without it,
`log_price_vs_sub` would be 0 at serving and differ from training.

Live check: LIVE_CHECK

## 6. Retraining every hour

```powershell
.venv/Scripts/python.exe scripts/train_live_ranker.py --since "<T0>" --out cache/lgbm_live_<stamp>.txt
```

- **Choosing T0.** Use the T of a cached snapshot (`cache/snapshot_<T0>.pkl`), so the 4-7 min build is skipped.
  Keep `until - T0` at or under about 6 h, for staleness and so that recent buys cover every purchase after T0.
  Every 3 h, build a new snapshot in the background (`python scripts/build_snapshot.py 2026-11-14T15:10:00`),
  then move `--since` to it.
- **Default `--until`.** It is now minus 2 min, because feedback lands about 4 s after each request. The run
  takes about 7 min, mostly the 24 LightGBM fits.

**Promotion gate.** Check these against the JSON sidecar before a new model goes live:
1. The sanity checks are OK: bought negative, session views and history views positive, position curve
   non-increasing.
2. The factored purchase NDCG is not below the logged order by more than its CI.
3. The live check composition looks sane (`python -m engine.learn.live_check --model ...`).

**Deploy.** The policy loads its model when it is constructed. Point the registry entry at the new file and
restart `scripts/run_live.py`; the takeover handoff avoids a gap. Alternatively, keep a fixed path, for example
`cache/lgbm_live_latest.txt` plus `.json`, and copy the promoted pair over it before the restart.

## 7. Risks

- **Exposure bias and feedback loop.** We only learn about items our policies, or the fallback, chose to show,
  in the slots they chose.
  - The first 75 % of the data comes from `content-session-popularity-v1` and the near-constant fallback list.
    Session views were almost never shown, so the model's view of them is thin.
  - Slot-0 scores for groups rarely shown in slot 1 are extrapolations by the position model, for example
    `same_cat` (4 %).
  - Training on our own exposures reinforces what we already show. Keep traffic split across several arms, the
    learned ranker included, so the next retrain sees varied lists.
- **Small purchase counts.** There are 198 purchases in total and 44 in validation. Purchase metrics have CIs of
  about ±0.1 NDCG, and the two runs above disagree in sign. The factored model leans on clicks (636) for exactly
  this reason. Do not tune on purchase metrics alone.
- **Non-stationarity.** The policy mix changed at about 13:50: training data came mostly from the old policy,
  validation data from the ev policies. Validation is therefore partly an off-policy test. The simulator,
  catalogue (about 1 500 updates in 2 h) and traffic mix can drift too. An hourly retrain on a rolling window is
  the mitigation.
- **Train/serve skew.** See the staleness trade-off in §1. The live runner and the training snapshot differ in
  freshness. Features with the same name can have slightly different age distributions.
- **Optimistic validation.** Early stopping and the 12-config search share the validation slice with the report.
- **Position model.** We assume the position effect is mostly separable (monotone `slot` plus tree interactions).
  If the simulator's examination depends strongly on item type, slot-0 scores of rarely-top items are biased.
