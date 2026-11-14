# RawTree Challenge · Team 37 engine

Real-time recommender for the RawTree challenge (Datathon FME 2026).

Work in progress. Layout:

- `engine/`: live system (RawTree client, offline feature builders, candidate generation, ranking, live loop).
- `engine/eval/`: offline evaluators built on the challenge data.
- `scripts/`: one-off utilities and probes.
- `docs/`: research notes and design decisions.

Credentials live in `.env` (never committed): `TEAM_ID`, `RAWTREE_API_KEY`, `HELMCODE_API_KEY`.
