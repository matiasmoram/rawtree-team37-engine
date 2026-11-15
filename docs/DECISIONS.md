# Decision log · team_37

Every decision that led to the final system, with the evidence it rests on and the document that records it.
"Conversion" is the leaderboard's expected purchases per 100 requests, computed by the organisers' simulator per
`model_version`. Baseline 0.48, organisers' reference 1.88.

The final system is [`fz_adaptive/`](../fz_adaptive/README.md), `model_version = fz-v10-nocorr`.

## A. How we measure (Saturday 14 Nov)

| # | Decision | Evidence | Source |
|---|---|---|---|
| A1 | The judge is the leaderboard's conversion per `model_version`. Offline AUC and NDCG on logged lists are diagnostics only. | A ranker with better AUC did not order purchases better (see B4). | [review_2026-11-14](review_2026-11-14.md), [recent_evaluation](recent_evaluation.md) |
| A2 | Compare variants only on disjoint traffic: one writer, or arms split by a hash of the request id, in the same time window. | With several team writers answering the same requests, per-arm numbers were not interpretable; on-time fell to 80.9% and the team was 10th of 42 (17:46 CET). | [review_20261114](review_20261114.md), [strategy_review](strategy_review_2026-11-14.md) |
| A3 | No automatic promotion. A variant is promoted by a person after a closed window. | Overlapping windows and repeated peeking make automatic gates unreliable. | [model_architecture_decision](model_architecture_decision.md), [experiments](experiments.md) |

## B. Earlier systems (Saturday 14 Nov; code in the archive tag)

| # | Decision | Evidence | Source |
|---|---|---|---|
| B1 | Never recommend a product the shopper already bought. | 1 purchase in 24.5k impressions of already-bought products. | [t37m4_thompson](t37m4_thompson.md) |
| B2 | Drop co-visitation as a ranking signal. | Paired ΔNDCG −0.038, 95% CI [−0.074, −0.010] against the champion. | [cycle_log](cycle_log.md), cycle 1 |
| B3 | Stop adding rule-based "evidence policy" variants. | Four cycles; no challenger confirmed (pooled gains +0.01 to +0.02, intervals include zero). | [cycle_log](cycle_log.md), cycle 4 |
| B4 | Replace the collection of policies with one purchase ranker over retrieved candidates; do not promote `lgbm-cart-v2` on AUC alone. | `lgbm-cart-v2`: purchase AUC 0.904 but NDCG 0.0445 below the logged order, CI [−0.107, +0.015]. | [model_architecture_decision](model_architecture_decision.md), [lgbm_cart_v2](lgbm_cart_v2_2026-11-14.md) |
| B5 | Cart and recent session views go to the top; cart state becomes a model feature. | Buys per 1,000 shown in slot 1: viewed earlier 19.4, last viewed 10.2, other 4.2. | [cartfirst](cartfirst.md), [t37m4_thompson](t37m4_thompson.md), [live_ranker](live_ranker.md) |
| B6 | Build a self-learning Thompson-sampling model (`t37-m4`) as a challenger. | Dry run: 0 late, p50 350 ms. It was a comparison arm on Saturday evening and was not the version run in the final. | [t37m4_thompson](t37m4_thompson.md), [design](t37m4_thompson_design.md) |

## C. The final system, `fz_adaptive` (Saturday afternoon to Sunday morning)

Built from zero, independently of the systems in B. Each variant ran live under its own `model_version`; arms listed
together ran at the same time on a hash split.

| # | Decision | Evidence (conversion %) |
|---|---|---|
| C1 | Score **every** active product with a model instead of hand rules: `P(click) × P(buy | click)`, two LightGBM models trained on 30 days of `shop.history_sessions`. | Heuristic 1.02 → model on the browsed category 1.28 → model on the whole catalogue 2.02. |
| C2 | Rank the whole catalogue, not only the browsed category. | Same category only 1.38 vs. all 2.09. |
| C3 | No penalty and no boost for other categories. | Penalty ×0.5: 1.84 vs. 2.09. Boost ×2.5: 1.86 vs. 2.49. |
| C4 | No diversity cap. | Max 2 per subcategory 1.42 vs. 1.85. |
| C5 | Add cart state and shopper profiles that update with every live event. | 2.02 → about 2.2. |
| C6 | Keep all feature groups. | Offline ablation: removing any group lowers the benchmark; shopper-brand affinity is roughly neutral. |
| C7 | Train on the history only, not on our live feedback. | With ~16k logged lists, adding live rows lowered click AUC on the newest unseen live impressions (0.83 vs. 0.86). |
| C8 | Switch the online correction off for the final. | Overnight A/B, 06:40–09:39 Sunday: off 2.23 (cold 2.74, 10,789 requests) vs. on 2.15 (cold 2.59, 21,551 requests). |
| C9 | Already-bought products: score ×0.05 (history, live store events, our own answers). | B1, and the organisers' note that buyers are much less likely to rebuy. The value 0.05 is a guess, not measured. |
| C10 | Reliability before model changes: one server process, a watchdog, hedged re-sends after 0.7 s. | Late answers came in bursts of slow API round trips while ranking stayed at ~45 ms. After hedging: zero late answers 03:00–09:00 Sunday, on-time 99.5–99.8%. |
| C11 | Freeze at 09:40 Sunday: all traffic on `fz-v10-nocorr`, no changes during the final. | On the 3 h window before the final the team was 3rd of 42 (2.17; leader 2.22). A 2 h split could only detect differences of about 0.19 (see the dashboard, power view). |

### Incident

Saturday 23:01–23:08 CET: a watchdog bug started duplicate servers, the laptop ran out of memory and rebooted, and
the saved state file was corrupted. Fixes: the watchdog matches the exact process, state is written with fsync to a
temporary file and renamed, and a corrupt state file is ignored on start.

## D. Known limits and what we would test next

1. **Retrain on our own feedback.** C7 was decided with ~16k logged lists; overnight we collected about 100k. The
   organisers advise trusting the feedback loop over the history, so this is the first thing to re-test.
2. **Measure the repeat-purchase penalty** (C9) from our feedback instead of guessing 0.05.
3. **Cart signal is probably overweighted**: in the history, carted products overlap with purchases and repeat
   purchases are allowed, unlike in the live simulator.
4. Purchases made through the earlier team systems (B) are not in our bought-memory (only history, `shop.events` and our own answers are).
