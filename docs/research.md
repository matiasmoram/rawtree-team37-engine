# Research: techniques for the real-time carousel recommender

Scope: published methods only (papers, Kaggle OTTO write-ups, GitHub repos). No material about this specific challenge was used.

## Recommended plan (ranked by expected impact)

1. **Re-visit backbone (biggest lift).** Put the last-viewed item in slot 1, then the other items viewed in the session by recency, then pre-event purchases. Logged buy rates are 2.35% / 1.78% / 1.66% against 0.058% for never-seen items, which is 30–40x. Drop items that are out of stock or that this user already bought during the event.
2. **Co-visitation candidates for the free slots.** Use view→buy, buy→buy and view→view matrices built from the 60 days of data, with time decay and extra weight on recent days. Do not limit candidates to the same category.
3. **Smoothed purchase prior for every item.** Compute it per item with empirical Bayes, shrinking towards the subcategory and brand rate. Include a price effect and a live trend lift (short window against long window). Use it for the 20% of requests from the home page with no views, for new users, and as a ranker feature.
4. **GBDT reranker** (LightGBM, lambdarank or binary objective) over about 100 candidates. Use relative or ratio features and no IDs. Train with position as a feature and set it to slot 1 at inference. Validate on a time split.
5. **Live in-memory state.** Track stock, price, per-user purchases and trend counters from the stream and catalog updates. Keep a precomputed fallback list so every answer is valid and fast, which also covers the reliability score.
6. **New products.** Embed each description and find its nearest existing products. Borrow their co-visitation neighbours and their conversion priors.
7. **Online learning.** Keep a per-item Beta posterior on purchases per *examined* impression, with examination weights taken from the slot curve. Update in batches every 30–60 s. Use Thompson sampling only in the bottom 2 slots, mainly for new products.
8. **Offline evaluation in two views.** Use IPS on the logged impressions (item-position or PI estimator) for orderings within the old category support. Use replay of organic sessions (next-purchase hit rate) for cross-category moves.
9. **A/B test before the final.** Split users into buckets by hashing user_id. Use click rate and model-expected purchases as surrogate metrics, because a test on purchases alone needs tens of thousands of requests per arm.
10. **Revenue tie-break.** When purchase probabilities are nearly equal, rank the higher-priced item first.

---

## 1. Session candidate generation and reranking (OTTO recipes)

**Key ideas**
- The winning OTTO pattern has two stages: (a) generate candidates from the session history plus co-visitation neighbours, then (b) rerank them with a GBDT. The 3rd-place team generated about 80 candidates per session and computed 744 features from item–item scores. Each feature was weighted by the item's position in the session, its timestamp and its event type, then aggregated. They used one XGBoost classifier per target ([Theo Viel repo](https://github.com/TheoViel/kaggle_otto_rs), [Schifferer repo](https://github.com/bschifferer/Kaggle-Otto-Comp)).
- Simple neighbourhood methods are hard to beat in session recommendation. Session-kNN often matches or beats GRU4Rec ([Ludewig & Jannach](https://arxiv.org/abs/1803.09587)).
- Rules carry most of the value. One top-3% solo solution reports that the GBDT reranker added only about 1–2 points over rule-based candidates ([Fedorov](https://github.com/Fedorov-Artem/kaggle_OTTO/blob/main/README.md)).

**Concrete co-visitation recipes**

| Matrix | Pair rule | Weight | Source |
|---|---|---|---|
| view→view | both events within 5 min (Fedorov) or within a day (Deotte) | later or more recent events weigh more | [Fedorov](https://github.com/Fedorov-Artem/kaggle_OTTO/blob/main/README.md), [KaggleX notes on Deotte](https://nupur2308.github.io/2023/03/15/kagglex.html) |
| any→buy ("carts-orders") | target event weighted by type `{click:1, cart:6, order:3}` | type weight | [Deotte notebook](https://www.kaggle.com/code/cdeotte/candidate-rerank-model-lb-0-575) (code mirrored [here](https://blog.csdn.net/CSDNXXCQ/article/details/128219856)) |
| click→buy | later event is a cart or order, gap < 10 h (a "short" variant uses < 2 h) | smaller gap weighs more | [Fedorov](https://github.com/Fedorov-Artem/kaggle_OTTO/blob/main/README.md) |
| buy→buy | both events are cart or order, gap < 5 days | uniform; Deotte keeps the top 15 | [Fedorov](https://github.com/Fedorov-Artem/kaggle_OTTO/blob/main/README.md), [Deotte mirror](https://blog.csdn.net/CSDNXXCQ/article/details/128219856) |
| click→click, click→cart/buy, cart→cart, cart→buy, buy→buy | 12–24 h windows, top 20 per item | counts, plus relative-count and rank features | [nicolaivicol](https://github.com/nicolaivicol/otto-recommender) |

- **Candidates.** Concatenate the session tail (last 20 events) with the top co-visitation neighbours of those items ([KaggleX](https://nupur2308.github.io/2023/03/15/kagglex.html)). Raising candidates from 20 to 75 lifted order recall from 64.8% to 69.0% ([Fedorov](https://github.com/Fedorov-Artem/kaggle_OTTO/blob/main/README.md)). Another solution used about 170 candidates per session, adding word2vec neighbours and popularity within session clusters ([nicolaivicol](https://github.com/nicolaivicol/otto-recommender)).
- **Reranker settings that worked without tuning.** LightGBM lambdarank with 150 trees, lr 0.25, depth 4, 15 leaves, colsample 0.25 and subsample 0.5. Keep only sessions that have at least one positive. Sample negatives at about 1:40, capped at 100 per session ([nicolaivicol](https://github.com/nicolaivicol/otto-recommender)). `rank_xendcg` is faster than lambdarank with similar quality ([LightGBM docs](https://lightgbm.readthedocs.io/en/stable/Parameters.html)).
- **Features that mattered.** Item-in-session counts by event type, recency rank, time since the last interaction, co-visitation scores aggregated over the session items (sum, max, weighted by recency), word2vec similarity, and conversion ratios ([nicolaivicol](https://github.com/nicolaivicol/otto-recommender), [Fedorov](https://github.com/Fedorov-Artem/kaggle_OTTO/blob/main/README.md)).

**Pitfalls.** Co-visitation built over the whole period leaks the future into validation. "Daily top items" leaked future information in OTTO ([Fedorov](https://github.com/Fedorov-Artem/kaggle_OTTO/blob/main/README.md)).

**How it applies here.** The catalogue has only 5,000 items, so full matrices fit in memory: 5k × top-50 per matrix. Rebuild them with extra weight on the last 7–14 days. Score candidates by expected *purchase*, not view, because that is the metric. Do not inherit the old policy's same-category restriction. The 0.20% buy rate for same-subcategory items shows that the category filter is weak, and co-visitation can surface complements across categories.

## 2. Learning a ranker from logged bandit feedback with position bias

**Click models**
- **PBM.** P(click) = examine(slot) × attract(item, context). In this model, sorting by attractiveness is optimal ([Joachims et al.](https://arxiv.org/abs/1608.04468), [Lagrée et al.](https://arxiv.org/abs/1606.02448)).
- **Cascade.** The user scans from the top and stops at the first attractive item ([Kveton et al.](https://arxiv.org/abs/1502.02763)).
- Purchase happens only on the clicked item, so P(buy | shown at slot k) = examine(k) · P(click | examined) · P(buy | click).

**Position as a feature / PAL**
- **PAL** factorises the click probability as σ(f(user, item)) · σ(h(position)). The model trains with the position term and serves f alone ([PAL, RecSys'19](https://dl.acm.org/doi/10.1145/3298689.3347033), as described in [Yuan et al.](https://www.csie.ntu.edu.tw/~cjlin/papers/debiases/debiases.pdf)).
- **YouTube** adds a shallow tower on position and device and sums its output into the logit ([Zhao et al.](https://research.google/pubs/pub49380/), [notes](https://charleslow.github.io/notebook/book/papers/zhao_2019.html)). In this project's GBDT, the equivalent is to include `slot` as a feature and predict with `slot=1` for every candidate.
- **Caveat.** Logged training data has a second selection bias, because only displayed items are labelled ([Yuan et al.](https://www.csie.ntu.edu.tw/~cjlin/papers/debiases/debiases.pdf)).

**Estimating the slot curve without confounding**
- The old policy is stochastic and logs its propensities, so the same item appears at different slots. "Intervention harvesting" (AllPairs) reuses such variation to estimate PBM propensities consistently, without new randomisation ([Agarwal et al.](https://arxiv.org/abs/1812.05161)).
- Regression-EM is a simpler alternative, but it can be biased if the relevance model is wrong ([Wang et al.](https://research.google/pubs/pub46485/), [Agarwal et al.](https://arxiv.org/abs/1812.05161)).
- The raw 21.5k→3.3k click curve overstates the decay, because the old policy put its best items on top.

**Off-policy estimators**
- **IPS / SNIPS.** Self-normalising (dividing by the sum of weights) is biased but consistent and has lower variance. It also prevents "propensity overfitting" when learning ([Swaminathan & Joachims](https://papers.nips.cc/paper/2015/hash/39027dfad5138c9ca0c474d71db915c3-Abstract.html)).
- **Doubly robust (DR).** A reward model plus an importance-weighted correction. It stays accurate if either the reward model or the propensity model is good ([Dudík et al.](https://arxiv.org/abs/1103.4601)).
- **Pseudo-inverse (PI).** Uses slot-level weights and is unbiased when the slate reward is additive across slots. This gives exponential data savings over whole-slate IPS ([Swaminathan et al.](https://arxiv.org/abs/1605.04812)). The self-normalised wPI performed better than PI ([Vlassis et al.](https://arxiv.org/abs/2106.07914)).
- **Item-position (IP) estimator.** Assumes the click depends only on the item and its position, and weights each (item, slot) pair separately. Its error was 13–18% lower than the list-level estimators ([Li et al.](https://arxiv.org/abs/1804.10488)).
- **Cascade-DR.** Uses the product of propensities down to slot k with a control variate. It fits the logged "propensity conditional on the items above" directly ([Kiyohara et al.](https://arxiv.org/abs/2202.01562)).
- [Open Bandit Pipeline](https://github.com/st-tech/zr-obp) implements IPW, SNIPW, DR, Independent IPS, Reward-Interaction IPS and Cascade-DR.

**Narrow logging policy (support deficiency).** IPS needs full support. With deficient support there are three options: restrict the actions to the logged support, extrapolate rewards with a model, or restrict the policy class ([Sachdeva et al.](https://arxiv.org/abs/2006.09438)). Here:
- **Inside the support** (re-ordering same-category items): use IP, PI or SNIPS on the impressions.
- **Outside the support** (cross-category, history items): impressions cannot tell you anything. Use a DM or DR reward model trained on organic data, plus organic replay: "did the next purchase in the session land in our top 10?". Treat these numbers as directional only.
- **Variance.** A deterministic new policy rarely matches a logged top-k prefix across 5,000 items. Evaluate a softened version (sampling with a temperature) or score the top 1–3 slots only.

**How it applies here.** The impressions give about 2M rows but very few purchases. Factor the model: P(click | examined) learned from clicks (dense) × P(buy | click) learned from purchases over clicks and organic cart→purchase rates.

## 3. Online learning in a carousel with delayed batch feedback

**Deezer carousel bandits** ([paper](https://arxiv.org/abs/2009.06546), [repo](https://github.com/deezer/carousel_bandits)):
- **Setup:** 12 slots, 3 visible at first, 20k users per round, rewards processed once per round.
- **Cascade update:** if the user clicks slot i, slots 1..max(L_init, i) count as seen. Unclicked seen slots count as failures, and slots below are not updated ([policies.py](https://github.com/deezer/carousel_bandits/blob/master/policies.py)).
- **Results:** No-cascade variants lost (p<0.01). The best policy was **segment-level Thompson sampling with a pessimistic Beta(1,99) prior**, which beat the naive Beta(1,1). Deterministic KL-UCB explored poorly under batch feedback. Stochastic policies vary the items shown within a batch ([paper](https://ar5iv.labs.arxiv.org/html/2009.06546)).
- **Thompson sampling degrades gracefully as feedback delay grows** ([Chapelle & Li](https://papers.nips.cc/paper/2011/hash/e53a0a2978c28872a4505bdb51db06dc-Abstract.html), as reproduced in [Neural TS](https://arxiv.org/abs/2010.00827)). The Beta–Bernoulli sampling rule is in the [Russo et al. tutorial](https://arxiv.org/abs/1707.02038).
- **Multiple-play under PBM:** update each item with *examination-weighted* impressions. This is the idea behind PBM-UCB/PIE/TS ([Lagrée et al.](https://arxiv.org/abs/1606.02448)).

**Concrete choices for this problem**
- **Posterior per item (or item × device):** Beta(α0 + purchases, β0 + Σ examine(slot)). Use clicks too, with a separate Beta per item for P(click | examined).
- **Prior:** set α0/(α0+β0) from the item's smoothed prior (§4). Give it an effective sample size of about 100–300, so a few lucky purchases do not dominate.
- **Updates:** batch every 30–60 s. Feedback arrives late anyway, and frequent sampling inside a batch provides the needed variation.
- **Exploration cost:** the final round is 2 h × about 3 req/s ≈ 21.6k requests. Slots 9–10 receive roughly 15% of the slot-1 clicks (confounded), so confining TS to those slots caps the regret. Elsewhere, rank by the posterior mean. Exploring is worthwhile only where uncertainty is real, mainly new products and trending items.

**A/B tests with hashed traffic**
- Assign variants by `hash(salt + user_id) mod 100`. This keeps assignment sticky per user. Use separate salts per layer so experiments stay orthogonal ([Tang et al.](https://research.google/pubs/pub36500/)).
- **Sample size:** n per arm ≈ 16σ²/δ² at α=0.05 and 80% power ([Zhou et al.](https://arxiv.org/abs/2305.16459)). With a per-request purchase probability of 2% and a 20% relative lift, that is about 20k per arm, or about 3.6 h at 3 req/s with a 50/50 split. So:
  - Run purchase A/B tests before the final.
  - Use click rate and the model's expected purchase as surrogate metrics.
  - Test only large changes.
- CUPED needs pre-experiment covariates ([Deng et al.](https://exp-platform.com/cuped/)), which new users do not have, so it helps little here.

## 4. Cold start, trends, price and repeat purchase

**New products (description only)**
- Embed each description with a sentence encoder and take the k=10 nearest existing products. Then borrow from those neighbours:
  - (a) Their co-visitation neighbours, as candidates for sessions that viewed the new item.
  - (b) Their purchase prior, mixed with the subcategory and brand prior.
  - (c) Their price-relative features.
- Learning a text→collaborative-embedding mapping (CB2CF) works for items that have no usage at all ([Barkan et al.](https://arxiv.org/abs/1611.00384)).
- Train the ranker with history features randomly masked (DropoutNet-style input dropout). This keeps warm accuracy and improves cold-start accuracy ([Volkovs et al.](https://proceedings.neurips.cc/paper/2017/file/dbd22ba3bd0df8f385bdac3e9f8be207-Paper.pdf)). In practice, set the history features to "missing" for about 10–20% of training rows.
- A new item that the user just viewed still gets the "last viewed" boost. That is the single biggest cold-start lever, and it needs no history.

**New users.** Use only in-session features (re-visit plus co-visitation from the session views). With no views, use a segment prior: the trending best sellers for that device × region × page. Never fall back to the all-time best sellers, because that is the baseline.

**Smoothing sparse rates**
- **Beta shrinkage:** posterior = (purchases + m·p_parent) / (impressions + m), with the parent chain item → subcategory → category ([hierarchical empirical Bayes for sparse CTR](https://arxiv.org/abs/1809.02213)).
- **Time-varying rates** can be tracked with a dynamic Gamma–Poisson model ([Agarwal et al., Yahoo front page](https://ir.webis.de/anthology/2009.wwwconf_conference-2009.3)).

**Trend detection.** Practitioners compare short-window and long-window averages, for example a 7d/30d ratio above 1.2 counts as "rising" ([Datma](https://help.datma.io/en/articles/13115951-product-trend-based-insights)). Amazon's TrendSpotter reports revenue lifts from trend-aware ranking ([Amazon Science](https://cdn.amazon.science/1d/79/e59dbb0a4f27b035eea560fb6353/trendspotter-forecasting-e-commerce-product-trends.pdf)). Proposed setup:
- Use ~65 events/s ≈ 234k events/h, which is about 47 events per product per hour on average.
- Keep exponentially decayed counters per item and per subcategory, with half-lives of 10 min and 6 h.
- Compare them with the 60-day daily rate. Compute lift = (c_short + m·r_long·T) / ((1+m)·r_long·T), with m ≈ 5 pseudo-windows so that thin items stay near 1.
- Use log(lift) as a feature and as a multiplier on the prior. Weight purchase and cart events above views.

**Price changes and stock-outs**
- Recompute price features at request time: price relative to the subcategory median, and the change against the 60-day price.
- Cheap items convert 4x better here (0.24% vs 0.06%). Keep price as a feature rather than a rule, and use the revenue tie-break.
- Remove an item the moment an `out_of_stock` event arrives. Re-add it on `back_in_stock`.

**Repeat purchase**
- In grocery, repeat items are about 1% of the catalogue but more than 54% of next-basket recall ([ReCANet](https://staff.fnwi.uva.nl/m.derijke/wp-content/papercite-data/pdf/ariannezhad-2022-recanet.pdf)). That matches the 1.66% logged buy rate for previously bought items.
- The rules state that a purchase made *during* the event lowers later appeal. So keep pre-event purchases as candidates with a recency feature. Hard-exclude, or heavily down-weight, items bought during the event, using both the private feedback and the stream's purchase events for that user_id.

## 5. Generalising under distribution shift

- **Time-based validation only.** Splits that ignore the global timeline leak future items into training ([Ji et al.](https://arxiv.org/abs/2010.11060)), and the split strategy alone can reorder model rankings ([Meng et al.](https://arxiv.org/abs/2007.13237)). Build co-visitation and priors on days 1–45 and train the ranker on days 46–53. Validate on days 54–60, and keep the latest impressions as the final check.
- **Slice the metrics** the way the evaluation does: new users, sessions touching products first seen in the last 7 days, the home page with no views, and pre-event buyers. Choose the model on the worst slice, not the average.
- **Relative features, no IDs.** Do not use product_id, user_id or brand_id as raw categoricals. Prefer:
  - Ranks within the request (recency rank, co-visitation rank).
  - Ratios (co-visitation score / max score, price / subcategory median, short/long trend).
  - Smoothed rates.
  These transfer to new products and trends; ID memorisation does not.
- **Small, regularised GBDT.** Depth 4–6, 100–300 trees, `min_child_samples` ≥ 100 and feature subsampling, as in the untuned OTTO settings that worked ([nicolaivicol](https://github.com/nicolaivicol/otto-recommender)). Self-normalised objectives avoid propensity overfitting ([Swaminathan & Joachims](https://papers.nips.cc/paper/2015/hash/39027dfad5138c9ca0c474d71db915c3-Abstract.html)). Tuning per fold was called "not a good practice" by a 3rd-place author ([Theo Viel](https://github.com/TheoViel/kaggle_otto_rs)).
- **Simulate the final round in validation:** mask the history of 20% of products (cold), drop all user history for 30% of sessions, and apply random price shocks. Then check that the ranking degrades gracefully toward the content and prior signals.
- **Keep a rule-based fallback** (plan items 1–3) as a live control arm. If the learned ranker underperforms it on any slice in the pre-final feedback, ship the rules.
