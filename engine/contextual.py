"""PIT context priors and subcategory/brand share trends, computed off the serving path.

Signals are weighted organic intent, not calibrated carousel purchase probabilities.
Context smoothing and trend comparisons use distributions, so a change in total
event throughput between history and live traffic does not masquerade as a lift.
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import CACHE
from .snapshot import load_products
from .types import sql_ts


def pair_key(device: str, region: str) -> str:
    return json.dumps([str(device), str(region)], ensure_ascii=False, separators=(",", ":"))


def _bounded(value, low=.5, high=2.):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("nonfinite contextual signal")
    return min(high, max(low, value))


def context_tables(rows: list[dict], *, top=80, prior_mass=25.) -> tuple[dict, dict]:
    """Hierarchical intent distributions. Sparse groups remain available but fail lookup support checks."""
    if not 10 <= top <= 200 or not math.isfinite(prior_mass) or prior_mass <= 0:
        raise ValueError("invalid context smoothing bounds")
    mass = {level: defaultdict(lambda: defaultdict(float)) for level in ("global", "device", "region", "pair")}
    support = {level: defaultdict(lambda: {"events": 0, "mass": 0.}) for level in mass}
    for row in rows:
        pid, dev, reg = str(row["pid"]), str(row["device"]), str(row["region"])
        weight, n = float(row["weight"]), int(row["events"])
        if not math.isfinite(weight) or weight < 0 or n < 0:
            raise ValueError("invalid context aggregation")
        for level, key in (("global", "*"), ("device", dev), ("region", reg), ("pair", pair_key(dev, reg))):
            mass[level][key][pid] += weight
            support[level][key]["events"] += n
            support[level][key]["mass"] += weight
    global_mass = mass["global"].get("*", {})
    total = sum(global_mass.values())
    if not global_mass or total <= 0:
        return {level: {} for level in mass}, {level: dict(values) for level, values in support.items()}
    # A unit of prior intent shared uniformly across items keeps finite tail priors.
    count = len(global_mass)
    global_prior = {pid: (w + 1. / count) / (total + 1.) for pid, w in global_mass.items()}
    posterior = {"global": {"*": global_prior}, "device": {}, "region": {}, "pair": {}}
    for level in ("device", "region"):
        for key, values in mass[level].items():
            denominator = support[level][key]["mass"] + prior_mass
            posterior[level][key] = {pid: (values.get(pid, 0.) + prior_mass * prior) / denominator
                                     for pid, prior in global_prior.items()}
    for key, values in mass["pair"].items():
        dev, reg = json.loads(key)
        d = posterior["device"].get(dev, global_prior)
        r = posterior["region"].get(reg, global_prior)
        denominator = support["pair"][key]["mass"] + prior_mass
        posterior["pair"][key] = {
            pid: (values.get(pid, 0.) + prior_mass * (d.get(pid, 0.) + r.get(pid, 0.)) / 2.) / denominator
            for pid in global_prior}
    tables = {level: {key: [[pid, p] for pid, p in sorted(values.items(), key=lambda x: (-x[1], x[0]))[:top]]
                      for key, values in groups.items()} for level, groups in posterior.items()}
    return tables, {level: dict(values) for level, values in support.items()}


def share_lifts(recent_rows, baseline_rows, products, *, attr, min_events=100, prior_mass=100.):
    """Bounded compositional lift relative to the preceding baseline distribution."""
    if attr not in ("sub", "brand") or min_events < 1 or prior_mass <= 0:
        raise ValueError("invalid trend grouping/support")
    grouped = []
    for rows in (recent_rows, baseline_rows):
        groups = defaultdict(lambda: [0., 0])
        for row in rows:
            product = products.get(str(row["pid"]))
            if product is None:
                continue
            weight, events = float(row["weight"]), int(row["events"])
            if not math.isfinite(weight) or weight < 0 or events < 0:
                raise ValueError("invalid trend aggregation")
            key = str(getattr(product, attr))
            groups[key][0] += weight
            groups[key][1] += events
        grouped.append(groups)
    recent, baseline = grouped
    recent_total = sum(v[0] for v in recent.values())
    base_total = sum(v[0] for v in baseline.values())
    if recent_total <= 0 or base_total <= 0:
        return {}
    groups = set(recent) | set(baseline)
    # Tiny compositional baseline prior prevents division by zero, but groups
    # without real baseline/recent support still retain identity.
    result = {}
    for key in sorted(groups):
        rw, rn = recent.get(key, [0., 0])
        bw, bn = baseline.get(key, [0., 0])
        base_share = (bw + 1. / len(groups)) / (base_total + 1.)
        current_share = (rw + prior_mass * base_share) / (recent_total + prior_mass)
        lift = _bounded(current_share / base_share) if min(rn, bn) >= min_events else 1.
        result[key] = {"lift": lift, "recent_events": rn, "baseline_events": bn,
                       "recent_mass": rw, "baseline_mass": bw}
    return result


@dataclass(frozen=True)
class ContextIndex:
    built_at: datetime | None = None
    tables: dict = field(default_factory=dict)
    support: dict = field(default_factory=dict)
    subcategory_lift: dict = field(default_factory=dict)
    brand_lift: dict = field(default_factory=dict)
    max_age_hours: float = 2.

    @classmethod
    def load(cls, path: str | Path | None = None):
        path = Path(path) if path is not None else CACHE / "contextual.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if raw.get("version") != 1 or raw.get("source_kind") != "organic_contextual":
                return cls()
            cutoff = datetime.fromisoformat(raw["as_of"].replace("Z", "+00:00"))
            if cutoff.tzinfo is None:
                return cls()
            tables = {}
            for level in ("global", "device", "region", "pair"):
                tables[level] = {}
                for key, rows in raw.get("tables", {}).get(level, {}).items():
                    valid = {}
                    for pid, probability in rows:
                        probability = float(probability)
                        if not isinstance(pid, str) or not math.isfinite(probability) or not 0 < probability <= 1:
                            raise ValueError("invalid context prior")
                        valid[pid] = max(valid.get(pid, 0.), probability)
                    tables[level][key] = tuple(sorted(valid.items(), key=lambda x: (-x[1], x[0]))[:200])
            support = raw.get("support", {})
            for groups in support.values():
                for row in groups.values():
                    if int(row["events"]) < 0 or not math.isfinite(float(row["mass"])) or float(row["mass"]) < 0:
                        raise ValueError("invalid group support")
            def lifts(key):
                return {str(group): _bounded(row["lift"]) for group, row in raw.get(key, {}).items()}
            return cls(cutoff.astimezone(timezone.utc), tables, support,
                       lifts("subcategory_lift"), lifts("brand_lift"))
        except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
            return cls()

    def usable_at(self, ts):
        return bool(ts.tzinfo is not None and self.built_at is not None
                    and 0 <= (ts - self.built_at).total_seconds() <= self.max_age_hours * 3600)

    def context(self, req):
        if not self.usable_at(req.ts):
            return (), "unavailable"
        levels = (("pair", pair_key(req.device, req.region), 500, 10.),
                  ("device", req.device, 200, 5.), ("region", req.region, 200, 5.),
                  ("global", "*", 0, 0.))
        for level, key, min_events, min_mass in levels:
            counts = self.support.get(level, {}).get(key, {})
            rows = self.tables.get(level, {}).get(key, ())
            if rows and counts.get("events", 0) >= min_events and counts.get("mass", 0.) >= min_mass:
                return rows, level
        return (), "unavailable"

    def trend(self, subcategory, brand, ts):
        if not self.usable_at(ts):
            return 1.
        return _bounded(math.sqrt(self.subcategory_lift.get(str(subcategory), 1.) * self.brand_lift.get(str(brand), 1.)))


def build_contextual(rt, as_of: datetime, *, window_hours=6., baseline_days=7., top=80):
    if (as_of.tzinfo is None or not 0 < window_hours <= 24 or not 1 <= baseline_days <= 30
            or not 10 <= top <= 200):
        raise ValueError("invalid contextual PIT range/bounds")
    as_of = as_of.astimezone(timezone.utc)
    recent_start = as_of - timedelta(hours=window_hours)
    base_start = recent_start - timedelta(days=baseline_days)
    weight = "multiIf(et = 'purchase', 1.0, et = 'add_to_cart', 0.25, et = 'view', 0.02, 0.0)"
    recent = rt.query(f"""
        SELECT p AS pid, dev AS device, reg AS region, count() AS events,
               sum({weight} * exp2(-dateDiff('second', event_ts, toDateTime64('{sql_ts(as_of)}', 3)) / 10800.0)) AS weight
        FROM (SELECT product_id::String AS p, device::String AS dev, region::String AS reg,
                     event_type::String AS et, ts::DateTime64(3) AS event_ts
              FROM shop.events WHERE ts::DateTime64(3) >= '{sql_ts(recent_start)}'
                AND ts::DateTime64(3) < '{sql_ts(as_of)}')
        WHERE et IN ('purchase', 'add_to_cart', 'view') GROUP BY p, dev, reg
        SETTINGS max_execution_time = 60, max_threads = 2""", timeout=70, retries=0)
    branches = " UNION ALL ".join(
        f"SELECT product_id::String AS p, event_type::String AS et FROM {table} "
        f"WHERE ts::DateTime64(3) >= '{sql_ts(base_start)}' AND ts::DateTime64(3) < '{sql_ts(recent_start)}'"
        for table in ("shop.history_events", "shop.events"))
    baseline = rt.query(f"""
        SELECT p AS pid, count() AS events, sum({weight}) AS weight FROM ({branches})
        WHERE et IN ('purchase', 'add_to_cart', 'view') GROUP BY p
        SETTINGS max_execution_time = 60, max_threads = 2""", timeout=70, retries=0)
    products = load_products(rt, as_of)
    tables, support = context_tables(recent, top=top)
    return {"version": 1, "source_kind": "organic_contextual", "as_of": as_of.isoformat(),
            "recent_from": recent_start.isoformat(), "baseline_from": base_start.isoformat(),
            "baseline_to": recent_start.isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(),
            "intent_weights": {"purchase": 1., "add_to_cart": .25, "view": .02},
            "half_life_hours": 3., "context_prior_mass": 25., "top": top,
            "recent_aggregate_rows": len(recent), "baseline_aggregate_rows": len(baseline),
            "tables": tables, "support": support,
            "subcategory_lift": share_lifts(recent, baseline, products, attr="sub"),
            "brand_lift": share_lifts(recent, baseline, products, attr="brand")}


def save_contextual(payload, path: str | Path | None = None):
    path = Path(path) if path is not None else CACHE / "contextual.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()
    return path
