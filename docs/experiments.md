# Bounded exploration and ownership

`engine.policies.explore.TailExplorePolicy` wraps a validated base policy. It
keeps the first eight valid, non-purchased base candidates and chooses an ordered
pair for slots 9-10. By default, 95% of requests keep the clean base tail; 5%
sample two items uniformly without replacement from a bounded eligible pool.
Previously purchased, recent purchased, duplicate and inactive candidates are
excluded when a full clean list is possible. If not, the wrapper preserves the
base policy and disables exploration explicitly.

This intentionally simple initial policy has probabilities that can be checked
exactly. It does not describe a Thompson posterior draw as an action propensity.

For pool size M, mixture rate e, base tail (a0,b0), and selected pair (a,b):

```text
P(a,b) = (1-e) * I[(a,b)=(a0,b0)] + e / (M*(M-1))
P(a)   = (1-e) * I[a=a0] + e/M
P(b|a) = P(a,b)/P(a)
```

`recommend_with_metadata(request, snapshot)` returns the selected items together
with the full clean base slate, candidate pool, epsilon, randomization salt ID,
selected pair, joint propensity and conditional slot probabilities. These are
conditional on this owning arm, prefix and candidate pool. The runner must log
its arm-assignment probability separately. Final stock filtering or replacement
changes the slate: mark those records invalid for propensity-based evaluation.
For attribution, join the selected ordered list with the actual feedback list;
merely having submitted the list does not establish that the shopper saw it.

Randomization is stable within a deployment by hashing a randomly generated
deployment salt and request ID. Explicit seeds reproduce an experiment for tests.
No network calls are made in the exploration wrapper.

## Multiple emitters

Run the read-only audit:

```powershell
.venv/Scripts/python.exe scripts/check_emitters.py --minutes 5,15
```

It uses fixed windows ending ten seconds before server now and records total
requests, missing submissions, duplicate submissions, distinct-version overlap,
per-version send counts and feedback attribution by the actual ordered shown list.
It stores aggregate JSON under ignored `logs/`; no keys or user/request IDs are
included. A version is not a machine identity, and overlap does not itself prove
the cause of a latency problem.

`engine.experiments.owns_request` provides explicit, disjoint request shards.
Every machine must agree on shard count and use a distinct index. Its default
single shard preserves the existing runner. A machine ignoring the contract can
still compete; this helper cannot remotely stop it. `health_snapshot` and
`write_health` provide an atomic local status file, explicitly labelled as not a
distributed lease. They must not be used to claim safe cross-host failover.

## Promotion

The offline `promotion_gate` fails closed for insufficient sample, competing
emitters, invalid lists, poor reliability/latency, model-estimated offline value,
unverified randomization, mismatched/incomplete windows and repeatedly checked
ordinary intervals. A positive effect bound is accepted for review only from a
single predeclared fixed-horizon same-window randomized comparison with uncertainty
clustered by user. It never mutates serving allocations. The 900-request threshold
is a minimum operational guard, not a power calculation or proof of significance.

Before canary exploration, agree on writer ownership and a fixed experiment end,
keep most traffic on the validated control and persist complete propensity data.
Do not promote based on a high AUC or raw purchases alone. Offline evaluations of
shown-list reranking do not identify the hidden simulator's conversion for new
slates.
