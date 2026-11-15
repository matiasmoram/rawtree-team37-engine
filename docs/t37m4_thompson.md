# t37-m4 · self-learning Thompson-sampling model

Code: `t37m4/`, kept in the git tag `archive-all-experiments-2026-11-15` (not on `main`, see [README](README.md)).
Full design: [`t37m4_thompson_design.md`](t37m4_thompson_design.md).

## What it does
- Predicts P(click at slot) × P(buy | click) with two Bayesian logistic models (Gaussian posterior) plus
  per-product corrections.
- **Learns by itself from the stream:** every ~2 min it reads mature rows of `team_37.feedback` (≥ 9 min old,
  every shown list of the team, fallback rows flagged) and updates the posterior. Old evidence fades
  (half-life 3 h). Weights are saved after every update, so a restart resumes where it left off.
- **Explores with Thompson sampling:** every 5 s it draws one plausible set of weights and ranks with it;
  uncertain weights vary, confident ones barely move.
- Ranks greedily slot by slot on P(buy); price only breaks near-ties (within 5 %: P(buy)·price^0.1).
- Hard rules: never a product the shopper already bought (history, live organic, or through any shown
  list; purchases polled every 3 s), never out of stock, always 10 distinct products.

## Evidence it rests on (all live feedback to 17:55 CET: 51,486 requests, 549 purchases)
| Fact | Buys per 1,000 shown |
|---|---|
| Already bought | 1 buy in 24.5k impressions → hard ban |
| Same subcategory as a past purchase | 7.2 vs 3.7 in slot 1 → *not* suppressed |
| Viewed earlier / last viewed / other, slot 1 | 19.4 / 10.2 / 4.2 |
| Popularity inside the last-viewed category | 0.4 → 13.1 (slot 1); flat ~0.9 outside |
| > €100 items | 1.48 vs 0.86–0.94 for €10–100 |
| New products, slot 1 | 7.2 vs 4.7 |

## Run it (Windows, from `t37m4/`)
```powershell
copy ..\.env .env                                   # TEAM_ID, RAWTREE_API_KEY
..\.venv\Scripts\python.exe -m recsys.thompson.setup_data      # once, ~5-10 min (history caches into t37m4\data)
..\.venv\Scripts\python.exe -m unittest tests.test_thompson_state tests.test_thompson_features tests.test_thompson_model tests.test_thompson_ranker tests.test_thompson_learner tests.test_thompson_guards tests.test_thompson_serve tests.test_thompson_report
..\.venv\Scripts\python.exe -m recsys.thompson.serve --dry-run --minutes 3     # no inserts
..\.venv\Scripts\python.exe -m recsys.thompson.serve --minutes 900 --control t37-cf-rot
```
- **Split:** `t37-m4` owns requests with `md5(request_id)[:8] % 2 == 1` (same hash as `engine/experiments.py`).
  Run the engine on the other half: `scripts/run_live.py --arms cf-rot:100 --shard-index 0 --shard-count 2`.
  If another version already answers the odd half, `serve` refuses to start; if > 5 % collide while running, it stops.
- **Guard:** with `--control t37-cf-rot`, two consecutive 30-min windows > 10 % below the control reset the
  model to its starting weights; two more stop it and write `STOP_SUBMIT`. `--no-guard` when someone watches.
- **Stop:** Ctrl-C or create `t37m4\STOP_SUBMIT`.
- **KPIs / weight trajectory:** `python -m recsys.thompson.report`.
- Starting weights: `models/thompson/posterior_latest.pkl` (fitted on 583k shown items, updated live to v4).
  To refit from scratch: `python -m recsys.thompson.learner --init` (~4 min).
- Final round: restart at ~09:30 CET (fresh catalogue/purchases; learned weights are kept).

## Dry-run results (19:00–19:10 CET)
~90 answers/min (our half), 0 late, latency p50 350 ms / p95 640 ms end to end, learner v2 → v4 live.
57 unit tests pass.
