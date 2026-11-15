# RawTree Challenge · Team 37

Real-time product recommender for the RawTree challenge (Datathon FME 2026). About three shopper requests arrive
per second; each must be answered within 3 seconds with 10 products.

## What is in this repository

| Folder | Content |
|---|---|
| [`fz_adaptive/`](fz_adaptive/README.md) | **The final system** (`model_version = fz-v10-nocorr`): code, trained model, config and the data it needs. Runs from a clone. |
| [`docs/`](docs/README.md) | **Decision record.** [`DECISIONS.md`](docs/DECISIONS.md) lists every decision with its evidence; the other files are the reviews and reports it cites. |
| [`tukey_dashboard/`](tukey_dashboard/README.md) | Decision dashboard (Shiny for Python + Altair): reliability vs. model quality for all teams, per-version comparison, decision register. |

## The final system in short

For each request, two LightGBM models score every active product (~5,000) as `P(click) × P(buy | click)` from 45
features: the shopper's taste profile (updated with every live event), their cart, the current session, and
market signals (popularity, live trends, price changes, new products, stock). The 10 best are sent in about one
second. Products the shopper already bought are pushed to the bottom.

On the last three practice hours it reached 2.23% conversion and 2.74% cold-start conversion (baseline 0.48%,
organisers' reference 1.88%), with 99.5–99.8% of answers on time.

## Run it

```bash
cd fz_adaptive
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # fill in TEAM_ID and RAWTREE_API_KEY
screen -dmS reco ./run.sh       # or: .venv/bin/python serve.py
```

Details, the rebuild-from-scratch steps and the file-by-file description are in
[`fz_adaptive/README.md`](fz_adaptive/README.md). Credentials live in `.env`, which is never committed.

## Earlier systems

The team built several systems before the final one (a policy engine with cart-first and LightGBM policies, and a
Thompson-sampling model). They were removed from `main` to leave only what ran in the final. Their code is kept in
the tag `archive-all-experiments-2026-11-15`, and what we learned from them is in
[`docs/DECISIONS.md`](docs/DECISIONS.md), section B.
