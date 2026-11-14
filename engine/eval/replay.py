"""Point-in-time policy replay on recent observed feedback.

Full-list support/composition and reordering of the observed ten are diagnostics.
Neither estimates the simulator's counterfactual expected conversion. Missing
logging support and position/selection bias cannot be repaired by pretending
unshown items were negatives.
"""
from __future__ import annotations

import copy
import hashlib
import math
import time
from datetime import datetime
from typing import Sequence

import numpy as np

from ..content import known_at
from ..learn.dataset import CatalogReplay, recent_buys_at
from ..learn.recent import paired_cluster_interval
from ..policies.evidence import EvidencePolicy
from ..policies.prepare import prepare_snapshot
from ..snapshot import Snapshot
from ..types import Request, parse_ts


def focused_session_policy() -> EvidencePolicy:
    """A declared hypothesis, not a fitted winner: session versus old-view priority."""
    return EvidencePolicy("ev-v4-session", bought_factor=.02, covis_gain=0.,
                          rel={"earlier_view": 3.0, "user_viewed": 1.0})


def sample_feedback(rows: list[dict], limit: int | None = None, seed: str = "policy-replay-v1") -> list[dict]:
    """A policy-independent deterministic request sample; never oversample positives."""
    if limit is not None and limit < 1:
        raise ValueError("request limit must be positive")
    ids = [str(r["request_id"]) for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate feedback requests; resolve before evaluation")
    if limit and len(rows) > limit:
        rows = sorted(rows, key=lambda r: hashlib.sha256((seed + str(r["request_id"])).encode()).digest())[:limit]
    return sorted(rows, key=lambda r: (Request.from_row(r).ts, str(r["request_id"])))


def valid_list(items: Sequence[str], req: Request, snap: Snapshot) -> bool:
    return len(items) == 10 and len(set(items)) == 10 and all(known_at(pid, snap, req) for pid in items)


def name_has_rerank(policy) -> bool:
    """Policies without scored_candidates/extra_candidates cannot rerank the observed list.

    They still contribute support, latency and hit-proxy metrics; their rerank
    entries stay None and are excluded from paired comparisons automatically.
    """
    return hasattr(policy, "scored_candidates") and hasattr(policy, "extra_candidates")


def rerank_observed(policy, req: Request, snap: Snapshot, shown: list[str]) -> list[str] | None:
    """Score every shown item, even when absent from the policy candidate pool.

    The policy is shallow-copied and its candidate extension adds the observed
    list. Original policy state/hook is preserved. Unsupported catalogue rows are
    explicit and cannot be silently dropped from the ranking denominator.
    """
    if len(shown) != 10 or len(set(shown)) != 10 or not all(known_at(p, snap, req) for p in shown):
        return None
    if not hasattr(policy, "scored_candidates") or not hasattr(policy, "extra_candidates"):
        raise TypeError(f"{policy.name} needs scored_candidates and extra_candidates for observed-list replay")
    copied = copy.copy(policy)
    original_hook = policy.extra_candidates
    copied.extra_candidates = lambda request, snapshot: set(original_hook(request, snapshot)) | set(shown)
    scores = dict((str(pid), float(score)) for score, pid in copied.scored_candidates(req, snap))
    if not set(shown) <= scores.keys():
        raise ValueError(f"{policy.name} omitted valid observed items despite explicit candidate injection")
    if not all(math.isfinite(scores[p]) for p in shown):
        raise ValueError(f"{policy.name} produced nonfinite observed-item scores")
    # Tie policy is the logged slot, so equal scores do not invent a gain/loss.
    slot = {p: i for i, p in enumerate(shown)}
    return sorted(shown, key=lambda p: (-scores[p], slot[p]))


def positive_gain(items: Sequence[str], target: str) -> dict[str, float] | None:
    if not target:
        return None
    if target not in items:
        return {"rank": float("inf"), "ndcg": 0., "top3": 0.}
    rank = list(items).index(target) + 1
    return {"rank": rank, "ndcg": 1. / math.log2(rank + 1), "top3": float(rank <= 3)}


def segment_flags(req: Request, snap: Snapshot, served_by: str) -> dict[str, bool]:
    new_view = any(p in snap.products and snap.products[p].is_new for p in req.viewed)
    return {"all": True, "cold_request": bool(req.is_new_user or new_view),
            "new_user": bool(req.is_new_user), "new_item_request": new_view,
            "home_page": req.page == "home", "no_session_views": not req.recent_views,
            "served_team": served_by == "team", "served_fallback": served_by == "fallback"}


def _mean(values):
    return float(np.mean(values)) if len(values) else None


def _paired(rows, name, reference, label, n_boot, seed):
    eligible = [r for r in rows if r["models"][name]["rerank"][label] is not None
                and r["models"][reference]["rerank"][label] is not None]
    differences = [r["models"][name]["rerank"][label]["ndcg"]
                   - r["models"][reference]["rerank"][label]["ndcg"] for r in eligible]
    return paired_cluster_interval(differences, [r["user_id"] for r in eligible], n_boot=n_boot, seed=seed)


def evaluate_replay(rows: list[dict], snapshot: Snapshot, policies: Sequence,
                    *, updates: list[dict] | None = None, recent_buys: dict | None = None,
                    limit: int | None = None, n_boot: int = 500, seed: int = 37) -> dict:
    """Replay catalog changes and recent purchases, comparing fixed candidate policies.

    Snapshot user profiles, aggregate counters and historical co-visitation remain
    frozen at the snapshot cutoff. This prevents future leakage but understates
    serving freshness. All output quality metrics are observed-label proxies.
    """
    if not policies or len({p.name for p in policies}) != len(policies):
        raise ValueError("at least one uniquely named policy required")
    if n_boot < 0:
        raise ValueError("bootstrap count must be nonnegative")
    t0 = time.monotonic()
    raw_count = len(rows)
    rows = sample_feedback(rows, limit)
    if not rows:
        raise ValueError("no feedback requests to replay")
    requests = [Request.from_row(row) for row in rows]
    if any(req.ts < snapshot.T for req in requests):
        raise ValueError("snapshot cutoff is after an evaluation request")
    replay = CatalogReplay(snapshot, sorted(updates or [], key=lambda row: parse_ts(row["uts"])))
    pit = copy.copy(snapshot)
    pit.products = replay.products
    pit.recent_user_buys = {}
    prepare_snapshot(pit)
    names = [p.name for p in policies]
    control = names[0]
    rerank_unsupported = [p.name for p in policies if not name_has_rerank(p)]
    records = []
    dropped_future_views = 0
    unsupported_observed = 0
    for req, row in zip(requests, rows):
        before = len(req.recent_views)
        req.recent_views = [(pid, ts) for pid, ts in req.recent_views if ts < req.ts]
        dropped_future_views += before - len(req.recent_views)
        replay.advance(req.ts)
        recent = recent_buys_at(recent_buys or {}, req.user_id, req.ts)
        pit.recent_user_buys = {req.user_id: recent}
        shown = [str(p) for p in row.get("shown", [])]
        clicked, purchased = str(row.get("clicked") or ""), str(row.get("purchased") or "")
        if any(target and target not in shown for target in (clicked, purchased)):
            raise ValueError("observed clicked/purchased product is absent from shown list")
        supported = valid_list(shown, req, pit)
        unsupported_observed += not supported
        bought = set(pit.user_buy.get(req.user_id, {})) | recent
        record = {"user_id": req.user_id, "request_id": req.request_id,
                  "segments": segment_flags(req, pit, str(row.get("served_by", ""))),
                  "models": {"logged_order": {"rerank": {label: positive_gain(shown, target) if supported else None
                                                           for label, target in (("click", clicked), ("purchase", purchased))}}}}
        control_items = None
        for policy in policies:
            started = time.perf_counter()
            items = list(policy.recommend(req, pit))
            elapsed = 1000 * (time.perf_counter() - started)
            if supported and name_has_rerank(policy):
                ordered = rerank_observed(policy, req, pit, shown)
            else:
                ordered = None
            if control_items is None:
                control_items = items
            record["models"][policy.name] = {
                "valid": valid_list(items, req, pit), "latency_ms": elapsed,
                "shown_item_support": len(set(items) & set(shown)) / max(1, len(items)),
                "same_slot_support": sum(a == b for a, b in zip(items, shown)) / max(1, len(items)),
                "exact_slate_support": items == shown,
                "top10_overlap_control": len(set(items) & set(control_items)) / max(1, len(items)),
                "bought_share": sum(p in bought for p in items) / max(1, len(items)),
                "click_hit_proxy": float(clicked in items) if clicked else None,
                "purchase_hit_proxy": float(purchased in items) if purchased else None,
                "rerank": {label: positive_gain(ordered, target) if ordered is not None else None
                           for label, target in (("click", clicked), ("purchase", purchased))},
            }
            if hasattr(policy, "index") and hasattr(policy.index, "usable_at"):
                record["models"][policy.name]["recent_matrix_usable"] = policy.index.usable_at(req.ts)
        # Symmetric overlap is composition only, never exposure probability.
        records.append(record)
    segments = {}
    for segment in records[0]["segments"]:
        selected = [r for r in records if r["segments"][segment]]
        models = {}
        for name in names:
            values = [r["models"][name] for r in selected]
            latencies = [v["latency_ms"] for v in values]
            metrics = {"requests": len(values), "invalid_lists": sum(not v["valid"] for v in values),
                       "latency_ms_p50": float(np.percentile(latencies, 50)) if latencies else None,
                       "latency_ms_p95": float(np.percentile(latencies, 95)) if latencies else None}
            for key in ("shown_item_support", "same_slot_support", "exact_slate_support", "top10_overlap_control", "bought_share"):
                metrics[key] = _mean([v[key] for v in values])
            for label in ("click", "purchase"):
                hits = [v[f"{label}_hit_proxy"] for v in values if v[f"{label}_hit_proxy"] is not None]
                gains = [v["rerank"][label] for v in values if v["rerank"][label] is not None]
                metrics[f"observed_{label}_recall_proxy"] = {"value": _mean(hits), "positive_requests": len(hits)}
                metrics[f"observed_list_{label}_ranking"] = {"ndcg": _mean([g["ndcg"] for g in gains]),
                                                            "top3": _mean([g["top3"] for g in gains]),
                                                            "positive_requests": len(gains)}
                for reference in ("logged_order", control):
                    if reference != name:
                        metrics[f"paired_{label}_ndcg_vs_{reference}"] = _paired(selected, name, reference, label, n_boot, seed)
            usable = [v["recent_matrix_usable"] for v in values if "recent_matrix_usable" in v]
            if usable:
                metrics["recent_matrix_usable_requests"] = sum(usable)
            models[name] = metrics
        segments[segment] = {"requests": len(selected), "models": models}
    return {"schema_version": 1, "metric_kind": "observed_feedback_policy_diagnostics",
            "counterfactual_policy_value_estimated": False, "automatic_promotion": False,
            "snapshot_cutoff": snapshot.T.isoformat(), "request_start": requests[0].ts.isoformat(),
            "request_end": requests[-1].ts.isoformat(), "feedback_requests_available": raw_count,
            "requests_evaluated": len(rows), "sampling": "deterministic request hash, no label oversampling",
            "snapshot_staleness_seconds": {"min": (requests[0].ts - snapshot.T).total_seconds(),
                                            "max": (requests[-1].ts - snapshot.T).total_seconds()},
            "catalog_updates_replayed": replay.i, "future_views_dropped": dropped_future_views,
            "unsupported_observed_lists": unsupported_observed, "control": control,
            "policies": names, "rerank_unsupported_policies": rerank_unsupported, "segments": segments,
            "bootstrap": {"unit": "user", "replicates": n_boot, "seed": seed,
                          "scope": "paired observed-list NDCG differences, no simulator probabilities"},
            "runtime_seconds": round(time.monotonic() - t0, 3),
            "limitations": [
                "Observed purchase/click labels depend on the original shown list and position; unshown items are not negatives.",
                "Full-list recall/support and observed-list reranking cannot establish expected conversion for a new policy.",
                "Observed-list scoring injects every shown item; it diagnoses ordering independently of candidate generation.",
                "User histories, counters, historical co-visitation and category priors are frozen at snapshot cutoff; stock/prices/new products and recent buys are replayed.",
                "Interval is a diagnostic development slice, not an untouched test for multiple tuning decisions.",
                "Local policy latency excludes polling, submission, stock propagation and network failures.",
            ]}
