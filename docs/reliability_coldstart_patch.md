# Operational patch for team_37 (14 November 2026)

This branch **does not change** the live traffic allocation or start any process. It adds a
read-only reliability diagnostic, optional request-ownership configuration, bounded push
concurrency and an **opt-in** cold-start policy.

## 1. Diagnose missing requests before touching ranking

From the project root, with the existing local `.env`:

```powershell
.\.venv\Scripts\python.exe scripts/diagnose_reliability.py --minutes 20
.\.venv\Scripts\python.exe scripts/diagnose_reliability.py --minutes 20 --duplicates
```

Check which UTC minutes have `missing` / `late` spikes, and compare them against
`logs/live.log` (DNS errors, `push_fail`, `poll error`, `dropped_late`). The last
15-minute sample supplied by the team had 2,101 accepted, 568 missing: 78.7% reliability.
A 1.919 s p95 among successful responses does not explain missing submissions.

**Do not start an extra serving instance.** The review in `docs/review_2026-11-14.md`
already documents overlapping remote emitters (`t37-m1`, `t37-m2`).
One process must own each request. The new `RAWTREE_OWNER_BUCKETS` setting can
divide request ids between *coordinated* deployments, using `arm_bucket(request_id)`.
Examples: machine A `0:50`, B `50:100`. The default `0:100` preserves previous
behaviour; configuring only one machine is insufficient if the other continues
submitting all requests. For final-round reliability, a **single writer** is simpler.

## 2. Bounded pushes

The live pusher previously created an unrestricted number of queued executor tasks
during network disruptions. It now admits at most `PUSH_WORKERS` in-flight HTTP batches.
Pending records stay in the outbox and are reconsidered against the deadline before
resubmission. This avoids queueing stale work behind blocked network calls.
This is a code-level safeguard, **not a measured improvement**; check the same
per-minute diagnostics after deploying.

## 3. Cold-start experiment (do not promote without live evidence)

The existing `cache/new_product_neighbors.json` was built by
`scripts/build_embeddings.py` but not used for serving. The optional
`ev-v2-cold` policy loads the cache at initialization, introduces same-subcategory
new/warm neighbours and uses a bounded similarity boost of at most 35%.
It requires the cache and does not change the default `ev-v2-nocovis:60,ev-v3:40` mix.

To compare locally without writing submissions:

```powershell
.\.venv\Scripts\python.exe -m compileall -q engine scripts
.\.venv\Scripts\python.exe scripts/run_live.py --dry-run --arms ev-v2-cold:100
```

**Caution:** the dry-run still polls and computes snapshots, but does not insert
submissions. Stop it after it has demonstrated valid ranking and normal p95 latency.

Before real A/B, arrange mutually exclusive request ownership across **all** machines;
then start a controlled single-runner comparison with fixed arms such as
`--arms ev-v2-nocovis:90,ev-v2-cold:10` (after an explicit deliberate handover).
Do not infer a winner from the organic replay evaluator or simple click hit-rates.
Prefer non-overlapping exact time windows from `scripts/analyze_windows.py` and
the organizers' per-model expected conversion + cold conversion. Statistical
uncertainty and shared request composition still matter.

## 4. Safety / rollback

- Existing default serving model allocation is unchanged.
- Existing `ev-v2-nocovis` and `ev-v3` calculations are unchanged when
  `content_neighbors=False` (default).
- No credentials, API keys, or customer data are in this patch.
- If an experimental deployment degrades, restore the previous serving process
  with its original `--arms` and keep one writer only.
- Files have been reviewed at source level; there has been **no end-to-end live
  deployment** and no claim of measured conversion lift.
