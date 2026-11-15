# Brief v0 — Tukey side-challenge dashboard (team_37, RawTree challenge)

## Competition rubric (Side Challenge Tukey, Datathon FME 2026)
"Un dashboard que ajudi a prendre decisions sobre el vostre repte principal."
Expected: select relevant information, show which conclusions it brings and which decisions it supports.
Free format/tool (Power BI, Shiny, Tableau, web app...). Judged on:
1. Utilitat per decidir — helps answer the challenge questions and ground decisions?
2. Adequació dels gràfics — visualizations adequate for the data and comparisons?
3. Coherència dels resultats — indicators, charts and conclusions consistent with each other and the data?
3 finalists (best per main challenge) -> 1 Premi Tukey. Theme: John Tukey (EDA, boxplot): "visualitzar per descobrir, interpretar i decidir".

## Main challenge (RawTree)
Real-time 10-slot carousel recommender. Requests arrive in RawTree DB; we write top-10 lists before a deadline; hidden simulator
decides clicks/purchases. Score: conversion ~50 pts (expected purchases), reliability ~10 (on-time valid lists),
cold start ~10 (new users / new products), jury ~30. Final: Sun 15 Nov 2026 10:00–12:00 CET (~190 purchases expected).

## Decisions the team faces (from ESTRATEGIAS.md, docs/)
D1 Which policy/arm serves the final? (cf-rot, t37-m4 Thompson, lgbm-recent, cf-v1, ...). Live purchases are too few:
   a 50/50 split only detects >26–40 % relative lifts -> decide with replay + surrogate metrics + uncertainty.
D2 What goes in slot 1 / top-3? Relation of item to user (viewed in session not last 2.08 %, cart 0.91 %, discovery 0.75 %,
   last viewed 0.66 %, viewed historically never carted 0.03 % — which took 24 % of slots!, bought before ~0).
D3 Where (if anywhere) to explore? Position curve: slot 1 converts ~4x slots 2–3, ~10x slots 4–10.
D4 Reliability: ~15 % missing requests 13:15–16:25 UTC (network drops + restarts) = biggest point loss.
   Decide: standby writer on other network, single writer no shards, skip stale backlog.
D5 Cold start: new users / new products — content neighbours, priors device×region.
D6 Statistical power: how many requests/purchases to tell arms apart -> freeze config before 10:00.

## Tukey hooks to exploit (statistics-literate jury at FME)
- Boxplots / five-number summaries (latency vs deadline, per-window conversion per arm).
- Median polish (Tukey 1977) on relation × slot two-way table -> additive row + column effects + residuals (tests interaction).
- Jackknife (Tukey named it) / bootstrap CIs for arm differences; Tukey HSD for pairwise arm comparisons.
- "The greatest value of a picture is when it forces us to notice what we never expected to see." (Tukey, EDA 1977)
- Exploratory vs confirmatory: show what we explored vs what we confirmed before committing.
