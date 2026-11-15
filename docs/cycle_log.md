# Cycle log

One paragraph per iteration cycle (see `docs/iteration.md` for the procedure). All times UTC (server clock); local machine runs CET — always schedule windows against server time.

## Cycle 1 — 2026-11-14, window 15:30→16:45

Setup: champion `ev-v3`; challengers `ev-v2-cat`, `ev-recent-covis`, `ev-context` (newly registered), `ev-v2`. Fresh snapshot at 15:30, fresh `recent_covis.json` as-of 15:30 (the previous artifact was built at 15:58, i.e. future-built for the replayed requests and unusable — the harness warning caught it), PIT carts attached for 62,429 users. 3,000 of 13,471 requests replayed; report `logs/iteration_20261114T1645.json`.

| challenger | paired ΔNDCG vs ev-v3 [ci95] | n | verdict |
|---|---|---|---|
| ev-context | +0.0422 [+0.006, +0.089] | 40 | **CANDIDATE** |
| ev-v2-cat | +0.0365 [−0.006, +0.090] | 40 | INSUFFICIENT (second positive window in a row) |
| ev-v2 | +0.0394 [−0.002, +0.093] | 40 | INSUFFICIENT |
| ev-recent-covis | −0.0384 [−0.074, −0.010] | 40 | **NO-GO** |

Decisions: **kill `ev-recent-covis`** (with a fresh, usable matrix it still orders observed lists below the champion — the signal does not help ordering here); `ev-context` advances to a confirmation window before any live trial; `ev-v2-cat` keeps accumulating. Post-hoc slices (exploratory, tiny-n, no decisions taken from them): the ev-context gain concentrates on home/no-session requests (where only context priors differentiate, +0.033) and ev-v2-cat/ev-v2 gains concentrate on new-user requests (+0.05); the mechanism is consistent with the cold-start component of the metric. Latencies p95 ≤ 7 ms for all arms; zero invalid lists.

## Cycle 2 — 2026-11-14, window 16:45→17:02 (virgin)

Champion `ev-v3`; challengers `ev-context`, `ev-context-cat` (new hybrid: context priors + same_cat/same_sub on the nocovis base), `ev-v2-cat`. Snapshot at 16:45. 3,000 of 3,072 requests; report `logs/iteration_20261114T1702.json` (overwritten later by the cycle-3 pooled run — verdicts preserved here).

| challenger | paired ΔNDCG [ci95] | n | verdict |
|---|---|---|---|
| ev-context | +0.0172 [−0.020, +0.063] | 36 | INSUFFICIENT |
| ev-context-cat | +0.0121 [−0.021, +0.051] | 36 | INSUFFICIENT |
| ev-v2-cat | +0.0018 [−0.042, +0.053] | 36 | INSUFFICIENT |

No confirmation; the cycle-1 CANDIDATE did not replicate. Per the loop, no live trial was started.

## Cycle 3 — 2026-11-14, pooled window 15:30→17:02 (both disjoint cycle windows)

Same champion; challengers plus never-offline-tested `ev-v2-tier` and `ev-v3-aff`. 6,000 of 16,543 requests, 77 reranked purchases; report `logs/iteration_20261114T1702.json`.

| challenger | paired ΔNDCG [ci95] | n | read |
|---|---|---|---|
| ev-context-cat | +0.0266 [−0.001, +0.057] | 77 | positive, misses by 0.001 |
| ev-v2-cat | +0.0238 [−0.007, +0.057] | 77 | positive, misses |
| ev-context | +0.0230 [−0.003, +0.053] | 77 | positive, misses |
| ev-v3-aff | +0.0099 [−0.007, +0.028] | 77 | negligible |
| ev-v2-tier | −0.0261 [−0.081, +0.026] | 77 | negative mean in both segments — its live cold number does not translate to ordering quality |

Decisions: **park `ev-v2-tier` offline** (do not spend a cold shard on it without a mechanism that explains the live/offline gap). `ev-context`, `ev-context-cat`, `ev-v2-cat` stay in the keep-collecting pool — three arms, consistently positive means (+0.02–0.03), n=77. Next higher-expected-value work: cart candidates/features into the LGBM ranker (P1-1) rather than more evidence-policy variants.

## Cycle 4 — 2026-11-14, window 17:02→17:17 (virgin)

Champion `ev-v3`; challengers `ev-context`, `ev-context-cat`, `ev-v2-cat`, `ev-content` (first offline test; overlap 0.99 with champion — its content neighbours essentially never change ordering on this window's traffic). 2,829 requests, n=36; report `logs/iteration_20261114T1717.json`.

All challengers flat: ev-context/ev-context-cat +0.003, ev-v2-cat −0.004, ev-content +0.000. Accumulated across cycles 1-4 the keep-collecting arms sit around +0.01–0.02 pooled — consistently non-negative, never confirmed at n≥30. The observed-label rerank diagnostic is saturating: slates differ a lot (overlap 0.73–0.91) but ordering quality on observed labels barely separates arms.

Standing decision: stop adding evidence-policy variants to the pool (diminishing returns); the differentiating levers left are (a) the other session's `engine/online/tslogit.py` cart+Thompson model — gate it with this harness when it lands, and (b) a bounded live arm for `ev-context-cat`, blocked on the single-writer P0, not on offline evidence.
