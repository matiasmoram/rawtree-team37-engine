# fz_adaptive · team_37 real-time recommender (final version)

Final-round version: `model_version = fz-v10-nocorr`. Everything needed to run it is in this folder; it shares no
code with the rest of the repo.

For every shopper request we rank the whole active catalogue (~5,000 products) and answer with the 10 products
most likely to be **bought**, in about one second.

## Run

Python 3.12. The trained model, its config and the shopper/product aggregates are committed in `data/`, so the
server starts straight from a clone:

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in TEAM_ID and RAWTREE_API_KEY
screen -dmS reco ./run.sh       # live loop under a watchdog (or: .venv/bin/python serve.py)
tail -f serve.log               # one status line every 30 s
```

Run only one instance per team: two servers answer the same requests twice.

`run.sh` uses `caffeinate` and `stat -f`, so it is macOS-only; on Linux run `serve.py` directly.

### Rebuild the model from scratch (optional)

```bash
.venv/bin/python download.py se 30     # 30 days of shop.history_sessions -> data/se_*.parquet
.venv/bin/python download.py agg       # aggregates computed in RawTree SQL -> data/*.parquet
.venv/bin/python train.py build        # training matrix -> data/train_X.npy, train_M.parquet
.venv/bin/python learn.py once         # trains and writes data/model.pkl (needs ~1.5 GB RAM)
.venv/bin/python setcfg.py fz-v10-nocorr same_cat_only=false xcat_factor=1.0 a_item=0.0 a_sub=0.0 'variants=null'
```

`setcfg.py` writes the config into `data/cfg.json` and `data/model.pkl`; a running server picks it up without a
restart.

## How it works

1. **What does this shopper like?** A taste profile per shopper (favourite subcategories, brands, product
   attributes such as "organic ingredients", price level) built from 60 days of store activity and updated **with
   every live event**, so a brand-new shopper gets a profile seconds after their first view.
2. **What did they almost buy?** Products a shopper put in the cart are a strong signal. Products they already
   bought (history, live store events, or through our own answers) have their score multiplied by 0.05.
3. **What are they doing right now?** The products viewed in this session: same product, subcategory, brand,
   attributes, price range.
4. **What is the market doing?** Long-run popularity, plus live trends (product / subcategory views in the last
   30 min vs. normal), live conversion, price changes, new products and stock-outs.
5. Two LightGBM models turn those 45 features into `P(click) × P(buy | click)` for every active product; the top 10
   are sent.

Adapting to the market:

| Speed | What | Where |
|---|---|---|
| seconds | stock-outs, price changes, new products (`shop.catalog_updates`); shopper profiles, carts, purchases (`shop.events`) | `serve.py` refreshers → `features.Store` |
| ~1 minute | trends: product and subcategory view share vs. long-run share, live conversion | `Store.build_pop` |
| on demand | retraining on history + our live feedback; live rows go in only if they improve AUC on the newest unseen live impressions | `learn.py` |

Exploration: on ~30% of requests the last slot shows a product from ranks 11–40, so the logs keep covering the rest
of the catalogue.

Cold start: the model was trained with shopper profiles hidden on 30% of impressions; new products inherit their
subcategory's popularity and are described by brand, price and the attributes parsed from their description.

`ranker.py` also contains an online correction (expected vs. observed clicks and purchases on our own impressions,
90-minute half-life). It is **switched off** in the final version (`a_item = a_sub = 0`) because it lost the
overnight A/B test below.

Reliability: 4 polling and 6 pushing threads; an insert in flight for more than 0.7 s is sent again on another
connection. Ranking takes ~45 ms; the rest of the ~1 s is API round trips.

## Files

| File | Role |
|---|---|
| `serve.py` | poll → rank → push loop, state refreshers, logging |
| `ranker.py` | model scoring, bought-product penalty, exploration → 10 products |
| `features.py` | the single feature function used both offline and online (no train/serve skew) |
| `run.sh` | watchdog: keeps exactly one `serve.py` alive and the machine awake |
| `setcfg.py` | sets the config / model version, hot-reloaded by the server |
| `q.py` | RawTree SQL client used by `download.py` |
| `download.py` | pulls the history; aggregates are computed in RawTree SQL |
| `train.py` | builds the training set from `shop.history_sessions` |
| `learn.py` | trains the model and writes `data/model.pkl` |
| `data/model.pkl`, `data/cfg.json` | the final model and its config |
| `data/*.parquet` | catalogue, product popularity, device × region lift, shopper profiles, carts, purchases |

Not committed: the API key, the raw history, the training matrix, the saved live state and the live
request/feedback logs. The server creates the last two in `data/` as it runs.

## Results that shaped the final version

Each variant ran live under its own `model_version`; arms listed together ran at the same time on a hash split of
requests. Numbers are conversion % (expected purchases per 100 requests) from the leaderboard.

| Test | Result |
|---|---|
| Candidates: same category only vs. all categories | 1.38 vs. 2.09 → rank the whole catalogue |
| Penalty ×0.5 on other categories vs. none | 1.84 vs. 2.09 → no penalty |
| Boost ×2.5 on other categories vs. none | 1.86 vs. 2.49 → no boost |
| Diversity cap (max 2 per subcategory) vs. none | 1.42 vs. 1.85 → no cap |
| Online correction on vs. off (3 h overnight, 21.6k vs. 10.8k requests) | 2.15 vs. 2.23, cold 2.59 vs. 2.74 → off |
| Live rows in retraining vs. history only (offline, newest live impressions) | click AUC 0.83 vs. 0.86 → history only |

Final configuration: 2.23% conversion and 2.74% cold-start conversion over 10,789 requests in the last three
practice hours (baseline 0.48%, organisers' reference 1.88%); the team was 3rd of 42 on that window.
