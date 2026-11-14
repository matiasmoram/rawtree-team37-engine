# Bounded HTTP submission queue: operational notes

RawTree has a strict three-second deadline measured from each `shop.requests.ts`.
The previous `pusher` used `ThreadPoolExecutor(max_workers=4)` but called
`pool.submit()` without checking queue length. During a DNS outage or a slow
RawTree POST, the executor queues arbitrarily many jobs. By the time older jobs
execute, they cannot meet the deadline.

This change caps submitted HTTP jobs at four. When all four slots are busy,
queued records remain in `outbox`, and the next cycle checks the deadline
again. They expire instead of spawning thousands of stale HTTP requests.
The `_send` method still checks freshness before each actual POST, just as
on main. The original default model allocation, hash sharding, timers and
all policies are unchanged.

## Verification on the user's machine

Run in a *separate checkout* while the existing live service stays running:

```powershell
python -m unittest discover -s tests -p test_push_backpressure.py -v
python -m unittest discover -s tests -p test_live_integration.py -v
python -m compileall -q engine scripts
```

Then coordinate a deliberate process handover to the patched runner and
compare `scripts/check_emitters.py --minutes 5,15` and
`scripts/monitor.py --once --minutes 15` against the previous window.
Keep only one writer per request or configure all writers with the same
`--shard-count` and distinct `--shard-index` values.

This patch does **not** address another host that sends the same request.
It does not make the API faster and cannot guarantee 99% on-time if DNS/API
problems persist; measure whether `push_fail`, `late`, and
`push_saturated` are occurring. The new counter is initialized lazily in
`stats`, so no existing reporter/schema needs changing.

The change is proposed, not deployed. Never switch the active service
without verifying its snapshot, credentials and heartbeat.
