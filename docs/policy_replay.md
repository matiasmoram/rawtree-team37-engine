# Point-in-time policy replay

`scripts/evaluate_policies.py` compares heuristic candidate policies on recent real
requests and the feedback lists shoppers actually saw. It never submits or
changes traffic. The separate recent-model evaluator remains responsible for
training/calibration/test splits and probability diagnostics.

```powershell
.venv/Scripts/python.exe scripts/evaluate_policies.py `
  --since 2026-11-14T15:00:00 --until 2026-11-14T15:23:00 `
  --snapshot cache/snapshot_20261114T134500.pkl `
  --max-requests 3000 --bootstrap 300
```

All times are UTC. The script queries server time and requires the end to be at
least two minutes in the past. It audits request/feedback coverage and rejects
duplicate feedback. Query inputs are cached under ignored `cache/`; aggregate
reports are written under ignored `logs/`. User/request IDs do not appear in the
aggregate report.

## What is measured

- Full recommendation lists: ten distinct active/available IDs, local latency,
  overlap with the control, support in the actually shown list, same-slot and
  exact-slate matches, and previously bought item share.
- Observed-click/purchase recall **proxies**: among requests with that observed
  positive, does the candidate list contain it? A product never shown by the
  historical policy cannot be labelled as an unsuccessful recommendation.
- Reordering exactly the observed ten items: NDCG and top-three placement of the
  observed positive, paired against logged order and the control. Every observed
  item is injected through a copied policy's `extra_candidates` hook, so a missing
  candidate cannot quietly become a zero score. Invalid/inactive/unknown observed
  lists are counted and excluded from this ordering comparison for every policy.
- User-cluster bootstrap intervals on paired observed-list NDCG differences.
  Slices include platform-new users, sessions viewing a new product, their union
  (official cold definition), home, empty-session context, team and fallback lists.

**None of these is a counterfactual estimate of the simulator's expected
conversion.** Position and exposure selection bias remain. A better replay score
may justify an online experiment; it does not demonstrate higher competition
score. This is a development interval, not a fresh holdout after arbitrary tuning.

## First actual replay: 14 November, 15:00–15:23 UTC

The query returned feedback for all 4,140 requests in the interval. A deterministic
sample of 3,000 included 1,073 cold requests, 139 observed clicks and 36 observed
purchases (21 in cold requests). All four policies produced valid lists; every
observed list had complete known/active product support for reordering. Runtime
was 124.4 seconds. The snapshot was 75–98 minutes old, which is a material limit.

| Policy | Observed-list purchase NDCG | Cold purchase NDCG | Previously bought item share | Local p95 |
| --- | ---: | ---: | ---: | ---: |
| nocovis | 0.6402 | 0.6820 | 0.413% | 7.8 ms |
| v3 | 0.6283 | 0.6623 | 1.890% | 8.4 ms |
| content | 0.6283 | 0.6623 | 1.960% | 17.2 ms |
| v4-session | 0.6191 | 0.6656 | 0.117% | 8.1 ms |

The v4-minus-nocovis paired purchase NDCG difference was -0.0211, with a user
bootstrap 95% interval [-0.0612, +0.0104]. Cold top-three placement rose from
61.9% to 66.7%, but that represents only 21 purchases and does not establish an
improvement. **This replay does not justify promoting v4 or content above
nocovis.** Their online simulator conversion remains an independent question.
The detailed ignored artifact is `logs/policy_replay_20261114T1523.json`.

## Information cutoff

The supplied snapshot must predate every request. Catalogue updates are replayed
strictly before request time on a private copy: stock, prices and new products.
Recent organic/feedback purchases are also filtered strictly before each request,
and future/current-time views are removed. The source snapshot is not mutated.

User profiles, counters, historical co-visitation and category priors remain
frozen at the snapshot cutoff. The report records snapshot staleness explicitly;
this is conservative against leakage but not a perfect reproduction of the live
refresh cadence. Content embeddings are content-only, and unavailable/future
products cannot become candidates. Recent co-visitation artifacts must have an
information cutoff no later than the request: otherwise that signal is disabled
and its usable-request count is reported when the policy is included.

## Initial declared hypotheses

Defaults compare `ev-v2-nocovis`, `ev-v3`, `ev-content` and the evaluator-only
`ev-v4-session`. The last keeps nocovis's repurchase suppression and changes the
session/history balance to `earlier_view=3.0`, `user_viewed=1.0`. It is a named
hypothesis, not a fitted or automatically promoted policy. Further tunings should
use a subsequent untouched interval and a bounded online test on the simulator
metric before adoption.
