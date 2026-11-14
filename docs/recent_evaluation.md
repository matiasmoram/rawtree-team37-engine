# Recent-feedback evaluation and retraining

`python scripts/evaluate_recent.py --since "2026-11-14 13:45:00" --model-out cache/lgbm_recent.txt`

This command reads RawTree requests, accepted `feedback.shown` lists and outcomes,
and submissions for attribution. It builds point-in-time features through the
existing dataset builder, trains small models, and writes an evidence report in
`logs/recent_evaluation_<until>.json` plus a text model and JSON sidecar in `cache/`.
It never submits answers, changes traffic, or promotes a model automatically.

All command times are **UTC**. The default end is server time minus two minutes,
rounded down to a minute, so still-pending feedback is not called a negative.
An explicit end newer than that is rejected. The default start is two hours
before the end. Explicit start/end make a run reproducible.

## What changed relative to the older evaluators

Organic next-purchase recall and old logged-impression metrics remain useful
diagnostics. They cannot reproduce the hidden live simulator: organic repurchases
can receive credit offline even when recommending already-bought products performs
poorly online. The old LightGBM validation also used the same time slice to choose
hyperparameters and to report results, and refitted exported models on those rows.

The new evaluator uses **four chronological, non-overlapping partitions**:

| Partition | Target share of requests | Permitted use |
| --- | ---: | --- |
| Train | 55% | Learn model parameters and baseline rates |
| Tune | 15% | Early stopping and selection among three small tree configurations |
| Calibration | 15% | Probability intercept and residual subcategory/position corrections |
| Test | 15% | One final report, after all previous choices are locked |

Whole requests and equal timestamps stay together. A request's inconsistent
timestamps and partitions without enough distinct times are rejected. The saved
model is the selected training model; it is **not refitted on test**.

Two small two-thread LightGBM models predict clicks and purchases. A factored
click model times the training purchase-given-click rate is also considered.
Selection uses tuning purchase log loss, not the test AUC. A monotone decreasing
slot feature absorbs part of position dependence. Serving-style ranking scores
use slot zero for every candidate; this does not make historical outcomes unbiased.

## Calibration and the serving contract

Calibration data fits a bounded log-odds intercept with a pseudo-exposure prior.
It then fits residual `(observed + 5)/(expected + 5)` multipliers for subcategory
and position band: slots 0-2, 3-5, and 6-9. Groups need at least 200 exposures;
their multipliers stay between 0.5 and 2. The expected quantity is a sum of model
probabilities at **logged positions**, not a heuristic ranking score.

Shared implementations in `engine/calibration.py` define both evaluation and
serving operations. The sidecar contains:

```json
{
  "serving": {"kind": "purchase"},
  "calibration": {
    "kind": "logit_shift",
    "shift": 0.0,
    "groups": {
      "example-subcategory|0": {
        "multiplier": 1.0,
        "n": 200,
        "expected": 1.0,
        "observed": 1
      }
    }
  }
}
```

The exported sidecar specifies `serving.bought_penalty=1.0`: the report does not
apply an extra manual penalty to model predictions. A serving policy must honour
that setting to reproduce the reported ranking; the historical policy default of
3.0 would create a different unvalidated variant.

Factored models instead have `serving.kind="factored"` and a `serving.pc`
constant-rate object. The global intercept belongs in `ServingModel`; group
corrections require actual item subcategories and slots at the policy layer.
The test report uses the same shared functions and the static calibration sidecar.
Later online calibration files must not be read when reproducing this test.

## Report

For the untouched test, report purchase log loss, Brier score, observed/predicted
rate, AUC when defined, and sample support. Compare calibrated/raw predictions
with a smoothed relation-by-slot rate baseline learned only on train. Slices are:
all, platform cold request, platform new user, new shown item, home page, no
session views, bought items, and not-bought items. A slice with fewer than ten
positives is explicitly flagged as insufficient, even if it has many negatives.

Within each request's **actual logged candidate list**, report click and purchase
NDCG and top-3 rate against logged order and relation baselines. Paired differences
use a user-cluster bootstrap: repeated requests from the same user are sampled as
one cluster. Confidence intervals are descriptive for this predeclared comparison,
not a sequential promotion test.

`online_trial_eligible` requires at least 30 purchased test requests, an entirely
positive purchase-NDCG difference interval against logged order, and purchase log
loss no worse than the relation baseline. It means eligibility to consider a
bounded online trial after latency, valid-list and exclusive-writer checks. It
does not authorize automatic deployment or prove higher simulator conversion.

## Limits that must remain visible

- Historical lists have selection and position bias. No logging propensity is
  available for their deterministic choices. The evaluator does not invent IPS
  weights or claim a counterfactual conversion value for an unshown product.
- The local report is **not** the competition's expected purchases per 100 requests.
  That number still requires a controlled online comparison in a common window.
- Request and feedback counts are queried before training. Coverage and duplicates
  are recorded; duplicate feedback causes the run to fail rather than multiply
  labels. A mature but missing request is not silently counted as a zero-purchase
  observed exposure.
- Catalogue updates and recent purchases are replayed before each request. Heavy
  user/item-history and co-visitation tables stay at interval start; this avoids
  future leakage but introduces staleness versus serving. A future snapshot must
  never be substituted simply to improve this report.
- The holdout ceases to be untouched if developers repeatedly adjust models after
  inspecting it. Use a later sealed interval for the next model-selection cycle.

Regression checks: `python -m unittest discover -s tests -p test_recent.py -v`.

## First measured run: 14 November 2026

The fixed interval **13:45-15:23 UTC** contained 17,640 requests, all with mature
feedback: 176,400 shown items, 660 clicks and 195 purchases. No unknown products
or duplicate shown items were dropped. The catalogue replay applied 220 updates.
The expensive point-in-time snapshot was built at exactly 13:45 UTC; a later
live snapshot was not substituted.

The untouched test covered **15:08:18-15:22:59 UTC**, 2,646 requests and 35
purchases. Tuning selected the factored click model; global calibration shift
was -0.09988. The model has not been deployed.

| Purchase diagnostic | New model | Baseline |
| --- | ---: | ---: |
| Observed-list NDCG | 0.7319 | 0.6952, logged order |
| Observed-list top-3 | 0.8000 | 0.6857, logged order |
| Exposure log loss | 0.008301 | 0.009852, train relation/slot rates |
| Exposure Brier | 0.0013083 | 0.0013188, train relation/slot rates |

The paired purchase-NDCG difference was **+0.0367**, user-cluster bootstrap
95% interval **[-0.0623, +0.1536]**. It includes zero, so the predeclared
`online_trial_eligible` gate is **false**. This is a promising probability model,
not evidence of a reliable policy improvement. Purchase AUC was 0.9001, but AUC
does not overrule the ranking comparison or the support limitation.

Artifacts (ignored local outputs): `cache/lgbm_recent.txt`,
`cache/lgbm_recent.json`, `logs/recent_evaluation_20261114T1523.json`.
No subsequent model choices were made from this test. A serving-parity check
compares the exported scorer and shared group corrections with the reported
held-out log loss; metadata schema normalization does not retrain the model.

## Prospective serving check

`python scripts/evaluate_recent.py --benchmark-only cache/lgbm_recent.txt --benchmark-requests 100`

The read-only check loads the latest snapshot and applies a live delta, then
collects fresh requests **strictly after** that cutoff. It replays subsequent
catalogue changes before each request and runs the content-enabled policy with
`bought_penalty=1`, two prediction threads, and the exported static calibration.
It measures both ranking and exposure-probability metadata, checks ten unique
active products, and verifies metadata against the shared probability helpers.
No submissions are sent and no purchase outcomes are used for this check.

Measured snapshot cutoff: **15:35:00.963 UTC**; 100 requests from
**15:35:01.025 to 15:35:34.045 UTC**, all strictly after the cutoff. There were
zero invalid recommendation lists. Ranking p50/p95 were **9.85/14.93 ms**;
ranking plus metadata p50/p95 were **11.24/17.22 ms**, maximum **21.02 ms**.
Candidate counts had median 125.5 and maximum 197. Exported static probability
parity had maximum absolute error **zero**.

The execution check passes for considering a bounded online canary, with a strong
control retained and one coordinated writer. It does not change the statistical
holdout result or prove content-candidate uplift. Local timings exclude network
polling, queueing and submission; inspect actual feedback to enforce the full
three-second service deadline. Evidence: `logs/recent_serving_benchmark.json`.
