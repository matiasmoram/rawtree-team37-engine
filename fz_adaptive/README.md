# fz_adaptive · team_37 real-time recommender (self-contained)

Serves as `model_version = fz-v9a-xcat1.0`. Everything it needs is in this folder; it shares no code with the rest of the repo.

For every shopper request we rank the whole active catalogue (~5,000 products) and answer with the 10 products
most likely to be **bought**, in about one second.

## How it works (the product-manager version)

1. **What does this shopper like?** We keep a taste profile per shopper (favourite subcategories, brands, product
   attributes such as "organic ingredients", price level) built from 60 days of store activity and updated **with every
   live event** — so a brand-new shopper gets a profile seconds after their first view.
2. **What did they almost buy?** Products a shopper put in the cart but has not bought are by far the best
   recommendation (≈18× the purchase rate in the historical log). Products already bought are pushed to the bottom.
3. **What are they doing right now?** The products viewed in this session: same product, subcategory, brand,
   attributes, price range.
4. **What is the market doing?** Long-run popularity, plus live trends (product / subcategory views in the last
   30 min vs. normal), live conversion, price changes, new products and stock-outs.
5. A model turns all of that into `P(click) × P(buy | click)` for each product; an online layer then corrects the model
   with what actually happened to our own recommendations in the last ~90 minutes.

## Adapting to a changing market — three speeds

| Speed | What | Where |
|---|---|---|
| seconds | stock-outs, price changes, new products (`shop.catalog_updates`); shopper profiles, carts, purchases (`shop.events`) | `serve.py` refreshers → `features.Store` |
| ~1 minute | trends: product & subcategory view share vs. long-run share, live conversion (SQL over `shop.events`) | `Store.build_pop` |
| minutes | **online correction**: per product and per subcategory, expected vs. observed clicks/purchases on our own impressions, exponentially forgotten (half-life 90 min) | `Ranker.correction` |
| on demand | **retraining** on history + our live feedback; live rows are used only if they improve AUC on the newest unseen live impressions; hot-swapped without restart | `learn.py` |

Exploration: on ~30% of requests the last slot shows a product the model would not have shown (sampled from ranks
11–40, or the best product outside the browsed category), so the system keeps learning about the rest of the catalogue.

Cold start: new shoppers have no profile → the model was trained with profiles hidden on 30% of impressions; new
products have no history → they inherit their subcategory's popularity and are described by brand, price and the
attributes parsed from their description.

## Files

| File | Role |
|---|---|
| `download.py` | pulls the history; user/product aggregates are computed **in RawTree SQL** (joins, attribute matching on descriptions) |
| `features.py` | the single feature function used both offline and online (no train/serve skew) |
| `train.py` | builds the training set from `shop.history_sessions`, time-split validation (last ~4 days) |
| `learn.py` | retraining on history + live feedback, gated by a newest-20% check (needs ~1.5 GB RAM, so it is run by hand, not kept running) |
| `bench.py` | internal offline benchmark: scores a candidate model on our most recent live impressions |
| `abcheck.py` / `ablate.py` | realised outcomes per live variant / feature-group ablation on the benchmark |
| `run.sh` | watchdog: keeps exactly one `serve.py` alive and the machine awake |
| `ranker.py` | model + online correction + exploration → 10 products |
| `serve.py` | concurrent poll → rank → push loop, state refreshers, logging |
| `setcfg.py` | change a parameter / model version live (hot reload) |
| `leaderboard.py` | reads the public leaderboard API (noise-free per-model score) for A/B decisions |

## Run

```bash
pip install -r requirements.txt && cp .env.example .env   # fill in TEAM_ID and RAWTREE_API_KEY
python download.py se 30 && python download.py agg        # once: history + SQL aggregates into data/
python train.py build && python learn.py once             # once: training set and data/model.pkl
screen -dmS reco ./run.sh                                 # live loop under a watchdog
python setcfg.py <version> key=value ...                  # change config / start an A/B split, hot-reloaded
```

## What we learned live (Saturday practice round)

Each variant ran under its own `model_version`; the leaderboard's expected-purchase score is the judge.
Arms listed together ran at the same time on a hash split of requests.

| Test | Result (conversion %) |
|---|---|
| Candidates: same category only vs. all categories | 1.38 vs. 2.09 → rank the whole catalogue |
| Penalty x0.5 on other categories vs. none | 1.84 vs. 2.09 → no penalty |
| Boost x2.5 on other categories vs. none | 1.86 vs. 2.49 → no boost |
| Diversity cap (max 2 per subcategory) vs. none | 1.42 vs. 1.85 → no cap |
| Live rows up-weighted x4 in retraining vs. history only (offline benchmark) | click AUC 0.83 vs. 0.86 → history only for now |

Final configuration (`fz-v9a-xcat1.0`): 2.25% conversion, 2.88% cold, over 2,657 requests (baseline 0.59%,
organisers' reference 1.94%).

Reliability: answers are sent with hedged re-sends (an insert in flight for more than 0.7 s is sent again on another
connection). Late answers came in bursts in which every round trip to the API slowed at once while ranking stayed at
~45 ms; `serve.py` logs a per-30 s breakdown and a probe to tell network from API slowness.

## Validation

* Offline: time-based split of the logged impressions, purchase AUC ≈ 0.958.
* Internal benchmark (`bench.py`): candidate models are scored on the newest live impressions they were not trained on.
* Online: concurrent A/B arms by request hash, judged on the leaderboard per `model_version`.
