# `skibidy-*`: standalone online-learning policy (parallel to `lgbm-recent`)

Independent of the LightGBM models: no model file, no wrapping. The version string (`t37-skibidy-v1`) does not reveal the method.

**Model.** Log-odds click model with a diagonal Laplace posterior, served by Thompson sampling.
`P(click, slot k) = e_k * sigmoid(theta . z)`, `e_k = 0.27 + 0.73/k`; rank by `sigmoid(theta . z) * price_factor`
(`price_factor = clip(price/median, .5, 2.5) ** 0.25`, the revenue tie-break).
`z` = 39 standardised generic features from `engine/features.py` (no `slot`) + `in_cart`, `cart_recency` + intercept.

**Prior.** Informative mean (sd 0.5): last-viewed, co-visitation, organic/carousel quality positive; bought items strongly
negative; carted-not-bought positive (live: ~9x). It is sensible from request 1; data moves it.

**Learning.** Every ~3 s `LiveRunner.learner` passes new `team_NN.feedback` rows to `observe()`. Per shown slot: Bernoulli
likelihood of the click, position handled by `e_k`, purchases weighted x3, diagonal online Newton step, forgetting
`gamma = 0.9998`. Fallback answers are ignored.

**Exploration.** `skibidy-v1`: 30 % of requests (stable hash of `request_id`) draw `theta ~ N(mu, 1/P)`; slots 1-2 always
use the mean. `skibidy-v1g`: no sampling, still learning (final-round candidate).

**Hard rules.** Items the user already bought are never shown; carted items are always candidates.

**Deploy next to lgbm-recent** (arms must sum to 100; keep your current allocation for the rest):
`python scripts/run_live.py --arms <current arms>,skibidy-v1:15,skibidy-v1g:10`
Compare by `model_version` (`t37-skibidy-v1`, `t37-skibidy-v1g`). `policy.weights()` shows what it learned.

**Checked:** `tests/test_skibidy.py` (synthetic world: recovers a hidden signal the prior ignores, weight 1.03 vs true 0.9;
valid lists, bought items excluded, cart item surfaces first on the real feature path). **Not checked:** live data.
