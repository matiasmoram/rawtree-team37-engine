# team_37 · RawTree challenge · Notion + GitHub digest (for the Tukey dashboard)

Collected 2026-11-15 (Sunday, before the final). Read-only: nothing was created, edited, commented or moved in Notion or GitHub.
Sources: Notion workspace (DATATHON tree, 11 pages + 1 database), repo `matiasmoram/rawtree-team37-engine` (remote via `gh`, local clone), organiser repo `rawtreedb/datathon-fme-2026`, rival `ToniOrtizGil/rawtree-recsys-fme2026` (team_36), public GitHub search.
Times: CET unless marked UTC (commit times are UTC; CET = UTC+1).

**Coverage caveats**
- No Notion page mentions "Tukey" or a dashboard for the side challenge. The only Notion side-challenge page is "7 · Side challenge: Best agentic use of RawTree", which is a different RawTree side challenge.
- The Tukey statement was found verbatim in a public repo of another team that works on a different main challenge (`berta-r/datathon_xusigrupoo`, `side-project/SideChallenge_TukeyFME2026.pptx.md`). See section 1.3.
- The last Notion edit on DATATHON pages is Sat 14 Nov 22:12 CET. Nothing in Notion is dated Sunday.
- Notion pages "5 · Starter kit" and "6 · RawTree (la base de datos)" were found but not read in full. They are reference copies of organiser material.
- The local clone is 1 commit behind `origin/main`. It has 8 modified files and several untracked docs/models. See section 7.

---

## 1. Challenge rules

### 1.1 Main challenge: official wording (organiser README, `rawtreedb/datathon-fme-2026`, last commit 14 Nov 15:46 UTC)

> **Exactly 10 distinct, active product IDs.** Invalid answers are replaced by the fallback. A product that sold out less than 5 seconds before the request still counts (it just cannot be bought), because a stock change can take a moment to show up in `shop.catalog_updates`.
>
> The answer must reach RawTree **within 3 seconds of the request `ts`**, as measured by the organisers' clock (polled every half second). Late answers are replaced by the fallback.
>
> If you send several answers for the same request, only one counts: send one.
>
> Order matters: shoppers look at the first slots much more than at the last ones.

> ### 70 points · Final round (automatic)
> Computed only on the requests of the final round (Sunday 10:00–12:00 CET). The practice round does not count.
>
> | Component | Points | Metric |
> |---|---|---|
> | Conversion | 50 | Expected purchases per 100 requests (see *No luck* below) |
> | Cold start | 10 | The same, restricted to **cold requests**: a new shopper (`is_new_user`), or `recent_views` that include a product added during the event (`new_product` in `shop.catalog_updates`) |
> | Reliability | 10 | Share of requests answered validly and on time |
>
> ```
> score = 100 × (team − baseline) / (oracle − baseline), clipped to [0, 100]
> ```
> - **baseline** (0): the all-time best sellers that are in stock, ranked once at the start of the stream (the starter-kit recommender). It is also the fallback.
> - **oracle** (100): the best list possible, the 10 products the hidden model itself would pick for each shopper.
> - The leaderboard also shows a **reference**: a strong recommender built by the organisers, as a benchmark. **It can be beaten.**
>
> **On the leaderboard** the 70 points are normalised to a score out of 100 (about 71 conversion, 14 cold start, 14 reliability). Your final grade is 70 % of that score plus the jury's 30 points.
>
> **No luck.** Whether a shopper buys is random. To keep luck out of the ranking, the score uses each shopper's *probability* of buying, given the 10 products you showed, as computed by the simulator's hidden model, instead of the coin flip. [...] a shopper who already bought a product tends not to want it again, so what your system sells changes later scores.

> ### 30 points · Presentation (jury)
> | Criterion | Points | What we look at |
> |---|---|---|
> | Method | 10 | Is the approach sound and well justified? How was it validated offline before going live? |
> | Learning from the stream | 10 | How did the system use feedback and live events (exploration, trends, price changes, cold start)? |
> | Use of RawTree | 5 | Features computed in SQL, embeddings, how the pipeline reads and writes |
> | Communication | 5 | Could a product manager understand what the system does and why it works? |
>
> **Tie-breaker:** expected revenue per request in the final round.

> **Status light.** During the final round the leaderboard shows only a green or red light per team: green if more than 90% of your answers in the last 5 minutes were valid and on time. It does not score anything.

> Rules: [...] Recommendations must be produced by code, not by hand. The top teams share their repository with the jury. [...] Anything a team cannot explain in the presentation may be penalised.

**Rule changes after the Notion copy (14 Nov 12:20 CET):**
- 15:46 UTC: 5-second grace after a stock-out. Notion page 1 still says one sold-out item invalidates the whole answer.
- 15:18 UTC: the leaderboard updates every minute, with a "Beta view" to choose the window. Notion pages 2 and 3 say every 10 minutes.

### 1.2 Notion summary of the main challenge (pages 1–4)
- About 3 requests/s. About 5,000 products in 10 categories and 90 subcategories. About 50 live events/s.
- Fallback reasons in `team_NN.feedback`: `missing`, `late`, `invalid`. Ignore the `__init__` placeholder row.
- `/api/state` fields: `mode` (waiting / practice / final_running / final), `teams[]` (`conversion`, `cold_conversion`, `on_time`, `revenue_per_request`, `model_version`), `baseline`, `reference`, `progress` (hourly conversion score 0–100), `hidden`, `lights`.
- The leaderboard shows only 10 versions per team. It hides versions with fewer than 100 requests in the window and greys out 100–299.
- Notion records a source discrepancy. Slides say the baseline is "best sellers of the last-viewed category". The code uses global all-time best sellers in stock.

### 1.3 Tukey side challenge: verbatim (Catalan; from `berta-r/datathon_xusigrupoo/side-project/SideChallenge_TukeyFME2026.pptx.md`, text extracted, images removed)

> **DATATHON FME 2026 · Side Challenge Tukey**
> **Un dashboard que ajudi a prendre decisions sobre el vostre repte principal**
>
> **Què s'espera?** Seleccionar la informació rellevant i mostrar quines conclusions aporta i quines decisions permet fonamentar.
>
> **Format i eina lliures.** Power BI, Shiny, Tableau, una aplicació web… Trieu el format més adequat per comunicar els vostres resultats. El dashboard es vincula al repte principal en què participa el vostre equip.
>
> **Valoració i Premi Tukey**
> **01 Utilitat per decidir.** Ajuda a respondre les preguntes del repte i a fonamentar decisions?
> **02 Adequació dels gràfics.** Les visualitzacions són adequades per a les dades i les comparacions?
> **03 Coherència dels resultats.** Els indicadors, gràfics i conclusions concorden entre si i amb les dades?
>
> **3 finalistes · 1 Premi Tukey.** El millor dashboard de cada repte. El millor dels tres finalistes.
>
> (Header: "Any Tukey a l'FME · Curs 2026–2027 · John W. Tukey 1915–2000 · Estadística per comprendre les dades [...] El seu llegat inspira aquest repte: visualitzar per descubrir, interpretar i decidir.")

**Implication:** one finalist per main challenge. team_37 competes against the other RawTree teams for the RawTree finalist slot. The known RawTree dashboard to beat is team_36's (section 6).

That team's own README interprets the criteria as: (1) usefulness to decision-making, (2) adequacy of representations for the data and comparisons, (3) coherence between indicators, charts, conclusions and data. Their guidance:
- Show denominators.
- Distinguish missing from zero.
- Keep small samples visibly tentative.
- State observed result, conditions and decision for every conclusion.

### 1.4 The other RawTree side challenge (Notion page 7)
"Best agentic use of RawTree". Rules:
- An AI agent that depends on RawTree to store, analyse and act on data.
- "The agent is the protagonist, not a wrapper."
- Deliver a repo with a README and a short demo.
- "A small project with a great story wins."

Notion has no team plan for it.

---

## 2. Timeline

| When (CET) | What |
|---|---|
| Sat 14 Nov 10:00 | Practice stream opens (epoch 1794646800) |
| Sat ~13:02–14:50 | First team launcher `content-session-popularity-v1` live. Stopped at 14:50 when the new engine took over |
| Sat 14:35–15:00 UTC (repo) | Engine scaffold → evidence policy v1 → v2 → LightGBM registered (commits `c72219f`…`044619a`) |
| Sat 16:03 | PR #1 cart-first (M1) merged by Marc |
| Sat 16:09 | Local allocation `ev-v2-nocovis:60, ev-v3:40` |
| Sat ~16:50–17:31 | Lab versions `t37-m1/m2/m3` run live, then stopped (Notion 9) |
| Sat 17:45 | Mix `lgbm-recent:45, cf-v1:20, cf-rot:15, skibidy-v1:20` |
| Sat 18:43 | Architecture decision "Purchase ranker v2" (commit `3a89fb8`) |
| Sat 18:46–18:49 | Local writer fails on transport (timeouts) and is stopped |
| Sat ~19:00–19:10 | `t37-m4` (Thompson, Daniel) dry run. Pushed at 19:23 (`f048535`) |
| Sat 20:00 | Local `run_live` stopped. `t37-m4` still submitting from another machine |
| Sat ~20:30–22:12 | Notion 10 (independent designs, combo ranker offline). Notion "Estrategias para la final" written at 22:02 |
| Sun 00:19 (23:19 UTC) | Daniel pushes `fz_adaptive` (`fz-v9a-xcat1.0`) to `origin/main` (`2bdbaad`). This is the latest team artifact anywhere |
| Sun 09:30 (planned) | Freeze best robust version at 100 % of traffic (Notion 8, Jordi's plan). Notion 9 checklist: rebuild snapshots 09:45–09:55, freeze one version by 09:55 |
| **Sun 10:00–12:00** | **Final round** (epoch 1794733200 → 1794740400). Leaderboard hidden; only status lights |
| Sun 12:00 | Final ranking appears automatically |
| Sun afternoon | Short presentation + demo to the jury. Tukey dashboard judged (date and format of the Tukey judging not documented) |

---

## 3. Team (first names) and roles

| Who | Evidence | Role |
|---|---|---|
| Matías | repo owner, most engine commits, Notion pages 8–10 and Estrategias | Engine (`engine/`), live runner/monitor, reliability fixes, PRs #2/#3, Notion documentation |
| Jordi | Notion "Research recomanador — team_37 (Jordi)", `PLAN.md`, `research/shared/NUMBERS.md` | Research. Cart-first insight, judge emulator plan, proposed splitting traffic by SHA-1(user_id) |
| Marc | merged PR #1 | Cart-first policy (M1), cart state, ridge/LinUCB bandit core (M3) |
| Daniel | commits `f048535`, `2bdbaad` | `t37-m4` Thompson-sampling learner. `fz_adaptive` recommender (fz-v9a), currently the team's best documented live number |
| (handle `fletxer`) | commit `7dc7310` | `money` (revenue-aware) and `skibidy` (online learner) policies. Name not identifiable |

The repo collaborators are three GitHub handles. Matías also runs a "lab" Claude session (branch `lab/claude-findings`) and HelmCode/Claude subagent reports in a folder outside the repo (`DATATHON/helm_harness/reports/`).

---

## 4. Decisions log

| When (CET) | Decision | Evidence / numbers | Source |
|---|---|---|---|
| Sat ~15:50 | **Hard-ban already-bought products** | `ev-v1` gave 15 % of its slots to bought items and scored 0.69, below the 0.75 baseline. Live, bought items convert 0.007 % (1 purchase in 22.4k–24.5k impressions); in history they converted 1.66 %. After the fix, `ev-v2` scored 1.36 | Notion 8, 9, DB |
| Sat ~15:50 | Use the online leaderboard per model (plus own attribution) as the judge, not offline evaluators | All three offline evaluators rewarded re-buys and rated `ev-v1` highly. Category policy beat global best sellers about 2× in all evaluators and on the leaderboard | Notion 8 |
| Sat 16:09 | Allocation `ev-v2-nocovis:60, ev-v3:40`. Retire `ev-v3-lowsess`, `ev-v2-uv`, `ev-v3-uv4` | Window 15:50–16:05: nocovis 1.669 (n=413), v3 1.609 (n=422), lowsess 1.224, uv 1.036, uv4 0.993 | Notion 8, DB |
| Sat 16:09 | Stay on the laptop, not the Hetzner VPS | Operational choice | Notion 8 |
| Sat ~17:30 | Lab models lost; stop them | `t37-m1` 1.13–1.20 (n=950), `t37-m2` 1.35 (n=290) vs nocovis 1.44–1.67. A popularity-leaning ranker loses to session relevance | Notion 9 |
| Sat ~17:30 | Do not trust a local judge with popularity features | Pearson vs leaderboard: history simulator 0.51; LightGBM with all features 0.43; **without popularity 0.82** | Notion 9 |
| Sat 17:45 | Remove `ev-v2-nocovis` from the registry. New trial mix `lgbm-recent:45, cf-v1:20, cf-rot:15, skibidy-v1:20` | Team at 17:33: conversion 1.31, cold 1.76, on-time 83.8 %, rank 11/42. Reference 2.05 | Notion 8 |
| Sat 18:43 | **Architecture: one two-stage purchase ranker** (retrieval → P(purchase)). Keep `lgbm-recent` 80 / `cf-v1` 20. Retire `skibidy-v1`, `cf-rot`. Park co-visitation, Thompson/exploration and auto-promotion | Monitor 18:37: `lgbm-recent` 1.48 (n=2,274), `cf-rot` 1.56 (n=753). Audit: 56 % of requests multi-model in 5 min, 72 % in 15 min; 113/900 missing | Notion 8, commit `3a89fb8` |
| Sat ~18:45 (local doc, uncommitted) | **Conflicts with the row above:** serve `cf-rot:100` | Team-shared window 18:12–18:42: `t37-cf-rot` 1.9204 (n=479), cold 2.7786, €0.864/request. In 120–180 min LGBM and cf-rot were tied | `docs/model_architecture_decision.md` (working tree) |
| Sat 18:49 | Stop local writer until on-time recovers | 1,102 answers: 301 sends, 107 push failures, 787 late; p95 13.5 s; RawTree endpoint timeouts | Notion 8, commit `898b930` |
| Sat ~19:00 | Live comparison only `cf-rot` (even hash half) vs `t37-m4` (odd half: md5(request_id)[:8] % 2) | `t37-m4` dry run: 0 late, p50 350 ms / p95 640 ms. Guard: 2 × 30-min windows more than 10 % below control resets the model | `docs/t37m4_thompson.md` |
| Sat ~19:02 UTC | Do not promote `lgbm-cart-v2` | Purchase AUC 0.904, but purchase NDCG −0.0445 vs logged order, 95 % CI [−0.1065, +0.0152] (6,833 requests, 81 purchases) | `docs/lgbm_cart_v2_2026-11-14.md` |
| Sat 17:30–18:30 UTC (cycles 1–4) | Kill `ev-recent-covis`; park `ev-v2-tier`; stop adding evidence-policy variants | ev-recent-covis ΔNDCG −0.038 [−0.074, −0.010]; ev-v2-tier −0.026 [−0.081, +0.026]; ev-context +0.042 in cycle 1, not replicated in cycle 2 (+0.017) | `docs/cycle_log.md` |
| Sat ~20:30 | Combo ranker built but offline only | History replay: ×1.40 purchases [1.34, 1.48]. Live holdout: ×1.07 [0.90, 1.22], indistinguishable from logged order | Notion 10 |
| Sat 22:02 | **Final-round strategy** (a synthesis, not all executed): reliability first; one writer without shards; no exploration in slots 1–3; decide before 10:00 with paired replay; revenue only as a tie-break; freeze, with the last snapshot before 09:40 | About 15 % missing (4,841 of about 32k, 13:15–16:25 UTC); about 190 purchases expected in the final, so a 50/50 split only detects lifts above 26–40 % | Notion "8 · Estrategias para la final" |
| Sun 00:19 | `fz_adaptive` ranks the **whole catalogue**: no category penalty, no boost, no diversity cap; online correction on | Same-category only 1.38 vs all 2.09. Penalty ×0.5: 1.84 vs 2.09. Boost ×2.5: 1.86 vs 2.49. Diversity cap: 1.42 vs 1.85. Online correction 2.21 vs 2.17 (tie, kept). **Final config `fz-v9a-xcat1.0`: 2.25 % conversion, 2.88 % cold, n=2,657** (baseline 0.59, reference 1.94) | `fz_adaptive/README.md` on `origin/main` |

---

## 5. Experiments and numbers (dashboard-ready)

### 5.1 Model versions on the leaderboard (expected purchases per 100 requests)

Notion DB "Registro de experimentos", plus later numbers from the repo:

| Model | Conv. | Cold | n | Window | Status |
|---|---|---|---|---|---|
| reference (organisers) | 2.191 | 2.103 | 2,700 | 15:50–16:05 | anchor-like benchmark |
| **fz-v9a-xcat1.0** (Daniel) | **2.25** | **2.88** | 2,657 | Sat night (not stated) | latest; not in Notion |
| t37-cf-rot | 1.920 | 2.779 | 479 | 18:12–18:42 | €0.864/request |
| t37-ev-v2-nocovis | 1.669 | 1.698 | 413 | 15:50–16:05 | retired 17:45 |
| t37-ev-v3 | 1.609 | 1.322 | 422 | 15:50–16:05 | — |
| t37-lgbm-recent | 1.48–1.60 | — | 481–3,468 | various | champion at 18:43 |
| t37-cf-v1 | 1.433 | — | 2,557 | rolling 17:51 | — |
| t37-ev-v2-cat | 1.422 | 1.567 | 967 | 14:50–15:50 | retired |
| t37-ev-v2-tier | 1.391 | 1.902 | 1,016 | 14:50–15:50 | cold reserve |
| t37-ev-v2 | 1.364 | 1.758 | 1,092 | 14:50–15:50 | retired |
| t37-m2 (lab) | 1.35 | 2.29 | 290 | ~16:00 | stopped |
| t37-ev-v3-lowsess | 1.224 | 1.814 | 419 | 15:50–16:05 | retired |
| t37-m1 (lab) | 1.13–1.20 | 1.65–1.77 | 950 | ~16:00 | stopped |
| t37-skibidy-v1 | 1.123 | — | 158 | rolling 17:51 | removed 18:43 |
| t37-ev-v2-uv | 1.036 | 1.318 | 424 | 15:50–16:05 | retired |
| t37-ev-v3-uv4 | 0.993 | 1.148 | 431 | 15:50–16:05 | retired |
| content-session-popularity-v1 | 0.752 | 1.168 | 8,251 | 13:02–14:02 | first launcher |
| baseline (official) | 0.748 | 1.250 | 2,700 | 15:50–16:05 | score 0, fallback |
| t37-ev-v1 | 0.69 | 1.527 | 2,288 | 14:50–15:50 | below baseline (re-buys) |

Caveat (repeated across all team docs): windows differ and overlap, and several emitters were active at once. These are not A/B wins. Cold requests convert higher even for the baseline (1.10–1.25 vs 0.67–0.75), so compare cold scores with the cold baseline.

### 5.2 Team leaderboard snapshots

| Time | Team conv. | Cold | On-time | €/request | Rank | Baseline / Reference |
|---|---|---|---|---|---|---|
| 13:16 (window 12:16–13:16) | — | — | — | — | — | 0.659 / 2.088 (leader team_24: 0.850) |
| 15:55–16:55 | 1.24 (score 21) | 1.48 | — | 0.54 | 10 | 0.67 / 2.04 |
| 17:33 | 1.31 | 1.76 | 83.8 % | — | 11/42 | ref 2.05 |
| 17:46 | 1.293 | 1.714 | 80.9 % | — | 10/42 | — |

Competitors at 15:55–16:55 (Notion 9):

| Team | Score | Conv. | Cold | €/request | Notes |
|---|---|---|---|---|---|
| team_06 | 51 | 2.04 | 2.67 | 1.02 | `skore_money_v7–9` at 2.31–2.43, cold 2.8–3.25; revenue-aware |
| team_26 | 41 | 1.78 | 2.24 | — | cold-routing model at 2.8–3.0 on cold-only traffic |
| team_19 | 36 | 1.65 | 2.25 | — | `v1-self` cold 3.83 |
| team_09 | 29 | 1.46 | — | — | — |
| team_23 | 29 | 1.44 | — | — | — |
| team_14 | 27 | 1.40 | — | — | — |
| team_01 | 23 | 1.26 | — | — | — |

### 5.3 What sells: relation of the shown item to the shopper (live feedback)

Notion 8 (16k requests, purchase % per shown item):

| Relation | Purchase % | Shown |
|---|---|---|
| last viewed in session | 0.40 | 994 |
| viewed in history, not bought | 0.39 | 4,392 |
| viewed earlier in session | 0.19 | 1,074 |
| same session category | 0.18 | 10,776 |
| same subcategory | 0.09 | 63,353 |
| unrelated | 0.05 | 36,279 |
| unrelated on home | 0.03 | 27,550 |
| **already bought** | **0.007** | 15,252 |

Jordi (per 1,000 impressions):

| Relation | Purchases per 1,000 |
|---|---|
| cart under 24 h, not bought | about 6.8 (about 25× rest) |
| cart over 24 h | 2.85 |
| viewed in session | 1.68 |
| same category / subcategory | 1.22 / 0.97 |
| rest | 0.27 |
| already bought | 0.05 |

Slot 1 by relation (Estrategias, about 18.5k requests):

| Relation | Purchase % in slot 1 |
|---|---|
| viewed in session, not the last | 2.08 |
| in cart (history), not bought | 0.91 |
| discovery | 0.75 (home 0.46) |
| last viewed | 0.66 |
| history-viewed, never carted | 0.03 (it once took 24 % of slots) |

### 5.4 Position curve

Buys per 1,000 by slot (Notion 9, 36.5k requests; clicks per 1,000 in brackets):

| Slot | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Buys (clicks) | 3.70 (10.5) | 1.33 (4.1) | 1.15 (3.4) | 0.65 (2.2) | 0.78 (2.4) | 0.47 (1.6) | 0.25 (1.4) | 0.34 (1.5) | 0.34 (1.9) | 0.31 (1.6) |

- Slots 1–3 carry about 66 % of purchases. Purchases per click are about 0.33 and flat across slots 1–6.
- Attention model (Notion 10): e_k = 0.27 + 0.73/k. It matches history within about 0.02.
- Item-adjusted attention (Notion 10, design A): 1, .647, .511, .424, .372, .350, .328, .318, .298, .285. Slot 1 over slot 10 is 3.5×, not the raw 6×.
- `t37m4` doc, slot 1: viewed earlier 19.4, last viewed 10.2, other 4.2 per 1,000.

### 5.5 Viewed item × slot (buys per 1,000, Notion 9)

| Slot | Last viewed | Viewed earlier | Other |
|---|---|---|---|
| 1 | 11.3 | 12.5 | 3.3 |
| 2–3 | 3.4 | 6.2 | 1.1 |
| 4–6 | 0.5 | 0.5 | 0.6 |
| 7–10 | 0.0 | 0.8 | 0.3 |

### 5.6 Session category × long-term category share (slots 1–3, buys per 1,000, Notion 9)

| Session \ history share | <10 % | 10–30 % | >30 % |
|---|---|---|---|
| not in session | 0.60 | 0.84 | 2.68 |
| partly in session | 0.74 | 1.41 | 2.48 |
| session's category | 1.06 | 2.31 | **6.89** |

### 5.7 Popularity

- Inside the session category, buys per 1,000 rise with log past purchases: ≤4: 0.13; 4–6: 0.12; 6–7: 1.59; 7–8: 2.64; 8–9: 5.38.
- Outside the category the effect is flat (about 0.9).
- Slots 1–3 popularity percentile: lab `t37-m1` 0.55, `ev-v2-nocovis` 0.35, fallback 0.92. Leaderboard: 1.14 / 1.44 / 0.73.

### 5.8 History vs live: the "the history lied" story (Notion 10, Jordi)

| Signal | History | Live |
|---|---|---|
| Re-buys share of purchases | 65 % | 1 of 493 |
| Same-category slot-1 purchase rate | 0.157 % | 1.12 % |
| Popularity features AUC | 0.76–0.82 | 0.62–0.68 |

- Training/serving skew: 69 % of live requests come from users with events the snapshot did not see.
- Refuted: the "Home & Kitchen / Pets +25 %" trend.
- Live-only drift: subcategory pulses (45 min, every 2 h at :30; views 3–5×, purchases 8–15×), price batches (about 12 % of the catalogue, elasticity about −1.5), new products in batches of 100.
- First-15-minute views of new products predict later purchases: Spearman 0.62–0.77.
- Price promotions: purchases ×1.31 [1.20, 1.43] and ×1.57 [1.43, 1.71] on the first two; no effect on the third.
- New-product text-neighbour prior vs live purchases: Spearman 0.48 (category average 0.39). `qwen3-embedding` nearest neighbour is in the same subcategory for 96 % of products.

### 5.9 Reliability (the largest point loss)

| Measure | Value | Source |
|---|---|---|
| Missing, 13:15–16:25 UTC | 4,841 of about 32k (about 15 %) | Estrategias |
| On-time, 15:05–16:05 | 85.40 % (53.7 % in 15:05–15:20; DNS failures) | Notion 8 |
| On-time, 15:50–16:05 | 100 % | Notion 8 |
| 15-minute sample | 2,101 accepted / 568 missing (78.7 % on-time) | PR #2 |
| Shadow window | 9.9 % missing | Notion 10 |
| Multi-version requests | 22.6 % of requests; 56 % (5 min) and 72 % (15 min) at 18:37; 895/897 in the 15:50 audit | Notion 8, 10, backlog |

- Fallback lists convert 0.72 % vs 1.17 % for ours.
- Latency: the API is the bottleneck. Model ranking takes about 2–45 ms; median end-to-end 1.2 s; p99 2.8 s; `SELECT 1` once took 5 s.
- The first valid answer wins in collisions.
- Clock: the server is +0.93 s ahead of the laptop.

### 5.10 Learning checks (Notion 10)
- Replay of 58k requests, slot-AUC buy, prior → learned:

| Learner | Slot-AUC buy |
|---|---|
| rel-v1 | .697 → .717 |
| rev2-v1 | .718 → .730 |
| skibidy | .681 → .830 |

- Real-time shadow run (13 min, about 9.8k requests): click log-loss improves (rel −18.8 [−32.6, −7.4]). Purchases are undetermined (29 buys).
- Learned multipliers say the hand-set cart (6×) and viewed (4×) lifts are about 2× too high.

---

## 6. Rival and public repos, and dashboards

### 6.1 `ToniOrtizGil/rawtree-recsys-fme2026` (team_36): **has a live dashboard. This is the one to beat**
- Stack: Python package `rtrec`.
  - LightGBM P(purchase) over about 300 candidates.
  - Session KNN (`sknn`). No ID features.
  - `validate.finalize`.
  - Heartbeat/standby in `team_36.scratch`.
  - SQL features in `rtrec/sql/*.sql` (coviews, popularity_by_context, position_bias, trend_lift, user_affinity).
  - Own simulator in `sim/`, used as an offline arbiter.
- Branch `sunday-final` (14 Nov 19:01 UTC) adds `ops/FINAL_PLAN.md`, `go_final.py`, `ab_report.py`, `rtrec/live/decide.py`.
  - **Pre-registered decision rule:** Beta-Binomial P(B > A) ≥ 0.95 **and** bootstrap by shopper (user_id) ≥ 0.90; simplest arm wins otherwise (baseline < v1 < v2).
  - Decision window: 18:09 → 04:00 UTC.
  - Automatic refit at 05:00 CET, switch to one model at 06:30, freeze at 09:00.
  - Offline (last 20 % of history, IPS-conditional purchases/100): baseline 0.53, v1 heuristic 1.03, v2 LightGBM+sKNN 2.36. AUC 0.957.
  - Known limit: history has almost no new users.
- **Dashboard** (`dashboard/`, standard library only, `python -m dashboard serve`; modes `demo` (synthetic, labelled), `fake --with-runtime`, `rawtree` live). Panels:
  1. Alerts, with runbook links (`LIGHT_RED`, `LIGHT_RED_RECOVERING`, …). CLI `dashboard check` exits 0/1/2.
  2. "Organisers' light (our estimate)": green/red/unknown from the 5-minute % valid and on time.
  3. "Conversion by model_version (A/B) and cold vs warm": purchases/100 with 95 % Wilson intervals, lift, a separate fallback row. Overlapping intervals mean "no winner claimed".
  4. "% valid & on time · per minute" with a 90 % line.
  5. "Latency p95 (ms) · per minute" against the 3 s deadline.
  6. "Fallback reasons" table.
  7. "Purchases per 100 · trailing 5 min".
  8. "Trending now": organic views, last 5 min vs the 15 min before, by subcategory.
  9. "Live: the last shoppers and the 10 products they saw", with "why" tags per item (viewed / same subcategory / same category / same brand / new / trending / selling now) and purchased outline.
  10. "Computed inside RawTree (SQL twins of the panels)": every panel has a SQL version, tested against embedded ClickHouse to return the same numbers.
- Presentation kit: `docs/presentation/slides.html` (5 slides), `demo_script.md` (6-minute talk + 3-minute demo, PM language), with a "never estimate, drop the claim" placeholder table.
- **Gaps relative to the Tukey criteria (to exploit):**
  - It is an operations monitor. It does not frame decisions ("what should we do / which config / why").
  - No score translation: baseline/reference/oracle anchors and the 70-point decomposition are not shown.
  - No position curve. No relation × slot evidence. No history-vs-live contrast.
  - No cost-of-fallback in points. No power/sample-size view.
  - The A/B decision rule lives in a CLI report (`ab_report.py`), not in the dashboard.
  - Cold vs warm is not normalised to the cold baseline.

### 6.2 Other public RawTree-challenge repos (none has a dashboard)
| Repo | Content |
|---|---|
| `ReallyTimba/datathon26_epoch1` | Starter fork + XGB ranker, SASRec-context transformer, RL agent (`rl_agent.py`), several recommender versions. Pushed 14 Nov 20:34 UTC |
| `mgcast-dev/TinyBird` | Starter fork + LightGBM/logistic models, pickled features/models. Pushed 22:48 UTC |
| `eyohadrian/datathon-fme-2026` | Starter fork + item2vec + LightGBM ranker. Pushed 19:00 UTC |
| `rawtreedb/datathon-fme-2026` | Organiser repo (README, starter recommender, queries.sql, offline_eval.ipynb) |

### 6.3 Other FME 2026 repos (not RawTree)
- `berta-r/datathon_xusigrupoo` and `elenagotlost/brainrot_coders`: math copilot on Arduino UNO Q.
  - berta-r has the Tukey brief and a `side-project/dashboard.html` (+ `dashboard_data.js`) for their own challenge.
  - That README lists the decisions it wants to support: config choice via accuracy vs latency scatter, paired before/after deltas, accuracy by segment with counts, latency distribution vs the limit, bias check.
- `ThorinOakenShield97/DatathonFME2026`: energy/battery challenge.
- `Joanfmir/DreamTeam`: prep repo with a Streamlit demo template.
- `linkyless/datathon-FME-2026-mental-descent`: empty.

---

## 7. Repo state (`matiasmoram/rawtree-team37-engine`, private)

- **Branches:** `main`, `feat/cartfirst-lints`, `fix/duplicate-writers-cold-start-20261114`, `fix/reliability-backpressure-20261114`, `lab/claude-findings`. Local-only branch `sim/judge` points at `f048535`.
- **PRs:**
  - #1 cart-first (M1) + cart state + ridge bandit core (M3): MERGED 14 Nov 16:03 UTC.
  - #2 "Diagnose missing submissions, bound pushes, and experiment with cold-start semantic neighbours": OPEN. Adds `scripts/diagnose_reliability.py`, `RAWTREE_OWNER_BUCKETS`, opt-in `ev-v2-cold`. Not run end to end.
  - #3 "Prevent deadline misses from unbounded RawTree HTTP push queue": OPEN. Adds a `BoundedSemaphore(4)` and tests. Not deployed or benchmarked live.
- **Issues:** none.
- **Commits (`origin/main`, UTC):** 19 commits, 13:35 → 23:19 on 14 Nov.
  - The last two are by Daniel: `f048535` t37-m4 (18:23) and `2bdbaad` fz_adaptive (23:19).
  - **The local clone stops at `f048535`; `2bdbaad` is not pulled.**
  - Local working tree: 8 modified files (README, docs/model_architecture_decision.md, engine/features.py, engine/learn/{dataset,scoring}.py, engine/policies/registry.py, scripts/{iterate,run_live}.py).
  - Untracked: docs/{backlog, cycle_log, iteration, lgbm_cart_v2_2026-11-14, review_20261114}.md, engine/online/, models/lgbm_cart_v2_*, scripts/train_tslogit.py.
- **Engine docs useful for the dashboard:**
  - `docs/recent_evaluation.md`, `policy_replay.md`, `cartfirst.md`, `live_ranker.md`, `experiments.md` (exploration propensities and the promotion gate).
  - `review_2026-11-14.md` / `review_20261114.md`, `strategy_review_2026-11-14.md`, `t37m4_thompson.md`, `cycle_log.md`, `backlog.md`.
  - `fz_adaptive/README.md` (remote only).
- **Data artifacts mentioned (local, not in Notion):**
  - `logs/*.csv` from `scripts/monitor.py` (leaderboard per model every 5 minutes, feedback).
  - `logs/iteration_*.json`.
  - `cache/live_snapshot.pkl`, `cache/new_product_neighbors.json`.
  - `fz_adaptive/results/` (ablation, model-size benchmark).

---

## 8. Open questions for the final

1. **Which model serves at 10:00, and from which machine (single writer)?**
   - Candidates with evidence: `fz-v9a-xcat1.0` (2.25 / cold 2.88, n=2,657, Daniel's machine), `cf-rot` (1.92 / 2.78, n=479), `t37-m4`, `lgbm-recent` (about 1.48–1.60).
   - No document after 00:19 CET records the final choice or who owns the writer.
   - Notion (18:43) and the local doc (`cf-rot:100`) contradict each other on `cf-rot`.
2. **Exploration in the final.** `fz-v9a` explores the last slot on about 30 % of requests. Notion "Estrategias" says exploration 0, or at most 5 % in slots 9–10.
3. **Standby writer on another network (E1, lease in `team_37.scratch`).** Proposed and estimated at 3–5 h. No evidence that it was built.
4. Freeze timing: 09:30 (Notion 8 / Jordi) vs a snapshot rebuild at 09:45–09:55 (Notion 9 checklist) vs the last snapshot before 09:40 (Estrategias).
5. Revenue tie-breaker: team_06 earns about 2× our €/request. Our policy is P̂·price only for near-ties (E8, `t37-m4` uses price^0.1). Is this enough?
6. The cold-start component is our weakest relative score. Is there a dedicated cold route (`ev-context` / content neighbours)? It was never confirmed live.
7. Tests A–J from Estrategias (saturation, position × relation, P(buy | click) by slot, satiety scope, price, device/region, last-view, θ shape) are not reported as run.
8. Repo hygiene before the jury: open PRs #2/#3, uncommitted working tree, local clone behind remote, earlier `MERGE_HEAD` issue. The top teams must share their repo.
9. Presentation: Notion Estrategias §6 has story bullets ("24 % of slots went to a relation that buys at 0.03 %", "the history lied, the stream told the truth", position curve from old-carousel randomness, reliability before/after). No slides or demo script exist for team_37. team_36 has both.
10. **Tukey dashboard:** no Notion or GitHub plan exists. Judging date and format are not documented.

---

## 9. Links

**Notion (DATATHON tree)**
- DATATHON (index): https://app.notion.com/p/418c8c86cbf080358b34fed8ae07991a
- 1 · El reto y las reglas: https://app.notion.com/p/418c8c86cbf081149e78fa4437d49bc3
- 2 · Timeline: https://app.notion.com/p/418c8c86cbf08172aba9f48678651fe6
- 3 · Evaluación y leaderboard: https://app.notion.com/p/418c8c86cbf081d297adcf70e0d15cc3
- 4 · Datos (tablas en RawTree): https://app.notion.com/p/418c8c86cbf0816f9b44d2aa7efa3f22
- 5 · Starter kit (repo): https://app.notion.com/p/418c8c86cbf081778f84ece9cc4153ec
- 6 · RawTree (la base de datos): https://app.notion.com/p/418c8c86cbf08158a598eaf65f9e76bb
- 7 · Side challenge: Best agentic use of RawTree: https://app.notion.com/p/418c8c86cbf081708d16f9bc1f148bc5
- 8 · Team 37 · Motor, pruebas y hallazgos: https://app.notion.com/p/418c8c86cbf081ba8cd7f1e99e51c16e
  - DB Registro de experimentos: https://app.notion.com/p/418c8c86cbf081bba6d0ddf1c714896d (data source `collection://418c8c86-cbf0-8109-94d7-000b3f72f224`)
- 8 · Estrategias para la final: https://app.notion.com/p/418c8c86cbf081d4a00fde91fb46eed8
- 9 · Team 37 · Lab: hallazgos, competencia y mejoras: https://app.notion.com/p/418c8c86cbf0816b966fc08b3a0f0c09
- 10 · Team 37 · Independent designs, learning checks and spec compliance: https://app.notion.com/p/418c8c86cbf081799005ca6f67cbd95a
- Research recomanador — team_37 (Jordi): https://app.notion.com/p/418c8c86cbf0811dbceef898148d4939

**GitHub**
- Team repo: https://github.com/matiasmoram/rawtree-team37-engine (PRs: /pull/1, /pull/2, /pull/3; lab: /tree/lab/claude-findings)
- fz_adaptive README: https://github.com/matiasmoram/rawtree-team37-engine/blob/main/fz_adaptive/README.md
- Organiser repo: https://github.com/rawtreedb/datathon-fme-2026
- Rival team_36: https://github.com/ToniOrtizGil/rawtree-recsys-fme2026 (dashboard: /tree/main/dashboard; final plan: /blob/sunday-final/ops/FINAL_PLAN.md; presentation: /tree/main/docs/presentation)
- Tukey brief source: https://github.com/berta-r/datathon_xusigrupoo/tree/main/side-project
- Other RawTree repos: https://github.com/ReallyTimba/datathon26_epoch1 · https://github.com/mgcast-dev/TinyBird · https://github.com/eyohadrian/datathon-fme-2026

**Challenge**
- https://datathon.rawtree.dev · leaderboard https://datathon.rawtree.dev/leaderboard · JSON https://datathon.rawtree.dev/api/state (per model: `?by=model&from=EPOCH&to=EPOCH`)

**Local copies in this scratchpad** (read-only downloads)
- `rival/` (README, dashboard files, presentation, HANDOFF)
- `tukey/` (Tukey brief and berta-r dashboard)
- `organizer_README.md`
