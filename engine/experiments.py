"""Request ownership, local health and conservative experiment promotion checks.

Explicit shards prevent competing writers only when every writer uses the same
contract. A heartbeat file is observability, not a distributed lease or failover.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import tempfile
import time
from pathlib import Path


def request_bucket(request_id: str, buckets: int = 100) -> int:
    if isinstance(buckets, bool) or not isinstance(buckets, int) or buckets < 1:
        raise ValueError("buckets must be a positive integer")
    return int(hashlib.md5(str(request_id).encode()).hexdigest()[:8], 16) % buckets


def owns_request(request_id: str, shard_index: int = 0, shard_count: int = 1) -> bool:
    if (isinstance(shard_index, bool) or not isinstance(shard_index, int)
            or isinstance(shard_count, bool) or not isinstance(shard_count, int)
            or shard_count < 1 or not 0 <= shard_index < shard_count):
        raise ValueError("ownership requires 0 <= shard_index < shard_count")
    return request_bucket(request_id, shard_count) == shard_index


def health_snapshot(stats: dict, *, shard_index: int = 0, shard_count: int = 1,
                    arms: list | None = None, now: float | None = None,
                    last_success_at: float | None = None) -> dict:
    owns_request("validation", shard_index, shard_count)
    return {"schema_version": 1, "updated_at": time.time() if now is None else now,
            "host": socket.gethostname(), "pid": os.getpid(),
            "shard_index": shard_index, "shard_count": shard_count,
            "arms": arms or [], "stats": dict(stats), "last_success_at": last_success_at,
            "distributed_lease": False}


def write_health(path: str | Path, payload: dict) -> None:
    """Atomic replace; consumers see either the previous complete document or the new one."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=target.name + ".", suffix=".tmp", delete=False) as f:
            name = Path(f.name)
            json.dump(payload, f, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        name.replace(target)
    finally:
        if name is not None and name.exists():
            name.unlink()


def promotion_gate(evidence: dict, *, min_requests: int = 900,
                   max_p95_ms: float = 2500.0, min_on_time: float = 0.99) -> dict:
    """Fail closed. A pass is review evidence, never an automatic serving mutation.

    The effect bound must come from one predeclared fixed-horizon, same-window,
    randomized comparison with clustering by user. Repeated ordinary 95% intervals
    and model-based offline value estimates cannot authorize promotion.
    """
    def finite_number(value):
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)

    reasons = []
    for key in ("candidate_requests", "control_requests"):
        value = evidence.get(key)
        if not finite_number(value) or value < min_requests:
            reasons.append(f"insufficient_{key}")
    if evidence.get("metric") != "simulator_expected_conversion":
        reasons.append("requires_online_simulator_metric")
    for key in ("preregistered", "window_complete", "same_window", "randomization_verified"):
        if evidence.get(key) is not True:
            reasons.append(f"requires_{key}")
    if (evidence.get("ci_method") != "fixed_horizon_user_clustered"
            or type(evidence.get("looks")) is not int or evidence.get("looks") != 1):
        reasons.append("requires_single_predeclared_clustered_comparison")
    lower = evidence.get("difference_lower_bound")
    if not finite_number(lower) or lower <= 0:
        reasons.append("positive_effect_not_established")
    overlap = evidence.get("multi_model_requests")
    if not finite_number(overlap) or overlap != 0:
        reasons.append("competing_emitters_or_missing_audit")
    if not finite_number(evidence.get("invalid_answers")) or evidence.get("invalid_answers") != 0:
        reasons.append("invalid_answers_or_missing_validation")
    on_time = evidence.get("on_time_share")
    if not finite_number(on_time) or on_time < min_on_time:
        reasons.append("reliability_below_threshold")
    p95 = evidence.get("p95_ms")
    if not finite_number(p95) or p95 > max_p95_ms:
        reasons.append("latency_above_threshold")
    return {"allow_promotion_review": not reasons, "automatic_promotion": False,
            "reasons": reasons, "min_requests_per_arm": min_requests}
