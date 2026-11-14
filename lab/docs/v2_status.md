# Team 37 — implementation status vs V2 plan (2026-11-14, ~15:45 CET)

Nothing has been submitted from this code. Everything below was run locally / read-only.

## How to run
```
python -m recsys.data                 # pull + cache data (read-only SQL)
python -m recsys.simulator            # train + validate local simulator
python -m recsys.policies             # train A ranker (data before 2026-11-07 only)
python -m recsys.evaluate             # offline + live replay, all policies
python -m recsys.evaluate --v2        # V2 sequence: A0, +P3, +P2, +both (held-out last 40% of live window)
python -m recsys.online_eval          # P2 chronological replay, tuning, learned theta
python -m recsys.dryrun --policy ranker --seconds 60   # live stream, deadline check, NO submit
PYTHONPATH=. python tests/test_a_parity.py
```

## Architecture A (PDF) — what exists
| Component | Status |
|---|---|
| Category head | heuristic weights (session / user / context), not a fitted multinomial LR |
| Candidates: co-views, popularity | done |
| Candidates: text embeddings (cold start) | done as TF-IDF + neighbours, flag `cold_start=True` |
| Candidates: ALS | not built |
| LightGBM ranker P(click)·P(buy\|click) | done, frozen in `models/A/` with manifest + hashes |
| Greedy slate objective | not built (sort + max 6 per category) |
| Thompson slots 9–10 | not built |
| Availability / bought / current-item bans, fallback fill | done |
| Fast loop | dry-run only (no push), p95 ≈ 1.6 s from request ts |

## V2 phases
| Phase | Status | Evidence |
|---|---|---|
| P0 freeze A, parity | done | `models/A/manifest.json`; `tests/test_a_parity.py` passes (flags off == A, θ=0 == A, θ≠0 changes lists) |
| P0 request-level logging | partial (dry-run log) | `data/dryrun_*.pkl` |
| P1 category audit | done | `docs/p1_category_audit.txt` |
| P2 online correction | done, flag `USE_ONLINE_CORRECTION` | `recsys/online_head.py`, `recsys/online_eval.py` |
| P3 cold-start items | done (flag) | Spearman 0.48 vs real live purchases of new products (category avg: 0.39) |
| P3 drift windows / cursors | not built | |
| P4, P5 | not started (optional per plan) | |

## Key findings
1. **History ≠ live on repeat purchases.** History: 62% of carousel purchases are re-buys (21× buy rate). Live: 0 of 82 purchases were re-buys, 14× lower click rate. Bought items are banned; the online head learned this on its own (θ_bought = −0.60).
2. **P1: the "100% same category" is an exposure artifact in history** (old system filled 100% of slots with the last-viewed category). The live fallback (session-blind) shows the preference is real (5.9× buy rate per impression in-category) but not exclusive (58% of fallback purchases were out of category). → keep soft allocation; models trained on history cannot judge out-of-category items, which is why P2 matters.
3. **P2 works:** on the last 40% of the live stream, NLL 0.04542 → 0.04261 (gain +0.0028 ± 0.0012, 95% CI), predicted purchases 57.2 → 36.5 vs 32 real.
4. **Simulator calibration on live:** baseline 0.58 vs leaderboard 0.66–0.70; teammate 0.62 vs leaderboard 0.71.

## V2 sequence (last 40% of live window, 5,585 requests)
| Policy | sim score (0=baseline,100=sim oracle) | cold score | €/req | real buy hit@10 | real click hit@10 |
|---|---|---|---|---|---|
| baseline | 0 | 0 | 0.10 | 71.9 | 54.3 |
| category_first | 37 | 31 | 0.48 | 84.4 | 76.0 |
| A0 ranker | 66 | 52 | 0.73 | 62.5 | 48.1 |
| A0 + cold start | 65 | 52 | 0.72 | 62.5 | 48.1 |
| V2.1 (A0 + online head) | 63 | 52 | 0.44 | 65.6 | 51.9 |
| teammate model (as shown live) | 1 | −5 | 0.18 | — | — |

Caveats: the simulator is trained on history, so it shares A's blind spots (re-buys aside) and is
partial to A; it cannot fairly judge the head, which corrects away from history. Real hit rates are
biased toward items the logging policy showed. Neither is a causal uplift estimate (plan §8).

## Open decision
`category_first` wins every real-outcome metric; the ranker wins the simulator. Candidate next step:
put category_first's score into the ranker (or blend), then let the online head arbitrate on live feedback.

## Live submissions (from 2026-11-14 ~15:50 CET, user-authorised, opaque names)
| version | policy | requests |
|---|---|---|
| t37-m1 | V2.1 + cold start (`--policy v21`) | hash range [0, 0.5) |
| t37-m2 | rank-fusion blend of ranker and category_first, w=0.5 (`--policy blend`) | hash range [0.5, 1) |
Submitter: `recsys/submit.py` (threaded: stock / poll / 4 push workers; late answers are dropped, never sent).
Stop: `touch STOP_SUBMIT`. Logs: `data/submit_<version>.log/.pkl`.

Step 1 result (`recsys/sim_live.py`): a live-calibrated simulator (history sim + small boosted correction) fits
held-out live purchases better (109 vs 89 predicted, 123 real) but rates the teammate's lists ≈ the fallback,
while the leaderboard says ~1.7× better. → no simulator is trusted to rank policies; the per-model
leaderboard (/api/state?by=model) is the judge.
