# Cart-first policy (cf-v1)

`cf-v1` uses the strongest new live signal in the team's Notion research: an
unbought product in the user's cart converted at about 6.3 per thousand shown items,
versus about 0.7 per thousand for ordinary items. Previously purchased items are excluded
because observed live conversion was near zero. Carts are kept separate from
`user_view`; the snapshot's existing view table combines views and carts.

The policy considers up to six recent cart items, then recent session views,
content neighbours, subcategory and user-affinity candidates, and trending/global
popular products. New items borrow a bounded quality prior from established
content neighbours; without that signal, the smoothed subcategory prior still
applies. It removes inactive, not-yet-launched and previously purchased products
and validates a unique ten-item slate. The cart table is loaded at startup and
incrementally refreshed from `shop.events` every 1.5 seconds. If loading fails,
the policy still returns a valid slate from its non-cart signals.

The prior live allocation was `lgbm-recent:60,cf-v1:20,cf-rot:20`. The current trial
is `lgbm-recent:45,cf-v1:20,cf-rot:15,skibidy-v1:20`: it keeps most traffic on
the strongest recent arms while giving the newly merged online learner enough traffic
to collect feedback. The newest public
15-minute view showed 1.874 expected purchases per 100 for `lgbm-recent` and
1.416 for `cf-v1`; the windows overlap previous traffic and are not a causal
comparison. `cf-rot` tests the team's observation that an earlier session view in
slot 1 converted more often than the most recent view (2.08% vs 0.66%). This is a
prospective trial, not a claim that any policy already beats the public score.
Team-wide online comparisons still require other emitters to remain stopped and
reliable submission transport. The old `ev-v2-nocovis` arm has been removed from
the policy registry and evaluator defaults; current comparisons focus on recent
LightGBM, cart-first, rotation, revenue-aware, and online-learning policies.

The companion branch also contains a Ridge/LinUCB core. It is not activated:
the code has no mature-feedback updater or validated end-to-end propensity and
reward pipeline. The existing tail-exploration implementation logs conditional
propensities and remains the safer basis for a later randomized experiment.


## Sources

- Team evidence and implementation: [Research recomanador ? team_37 (Jordi)](https://www.notion.so/418c8c86cbf0811dbceef898148d4939) and the teammate branch [feat/cartfirst-lints](https://github.com/matiasmoram/rawtree-team37-engine/tree/feat/cartfirst-lints).
- [Theo Viel's third-place OTTO solution](https://github.com/TheoViel/kaggle_otto_rs) supports candidate retrieval plus session features and a separate LightGBM reranker; its batch Kaggle metric and data differ from our online simulator.
- [Deezer carousel bandits](https://github.com/deezer/carousel_bandits) models multiple carousel plays, cascade effects, contextual users and delayed feedback. Its click/stream reward differs from our purchase reward, so it is a design reference, not a drop-in policy.
