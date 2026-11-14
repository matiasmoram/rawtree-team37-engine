# RawTree Challenge · Team 37 engine

Real-time recommender for the RawTree challenge (Datathon FME 2026).

Work in progress. Layout:

- `engine/`: live system (RawTree client, offline feature builders, candidate generation, ranking, live loop).
- `engine/eval/`: offline evaluators built on the challenge data.
- `scripts/`: one-off utilities and probes.
- `docs/`: research notes and design decisions.

Credentials live in `.env` (never committed): `TEAM_ID`, `RAWTREE_API_KEY`, `HELMCODE_API_KEY`.


## Current practice configuration (14 November 2026)

The runner defaults to `lgbm-recent:80,cf-v1:20`: one learned purchase ranker and one cart-first comparator. `cf-v1` uses pending carts, recent session views, content neighbours and bounded historical priors. The weaker Skibidy arm and extra rotation experiment were removed from the default allocation; their code and old submissions remain available for historical analysis. This is a controlled working allocation, not a claim that either arm has won: recent live comparisons are contaminated by concurrent team writers.

The model plan is [Purchase ranker v2](docs/model_architecture_decision.md). The public comparison metric is expected purchases per 100 requests, with cold-request conversion and on-time submission reliability reported separately. Local observed-list NDCG/log loss and serving benchmarks are diagnostics; they are not the hidden simulator conversion metric. See [the recent evaluation](docs/recent_evaluation.md), [cart-first trial](docs/cartfirst.md), and [policy replay](docs/policy_replay.md).
