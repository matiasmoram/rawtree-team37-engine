"""Shared building blocks for the offline evaluators.

Every evaluator follows the same recipe:

1. ``pull``: fetch evaluation cases (a ``Request`` plus a label) for [T, T + window) from RawTree, aggregating
   server-side, and cache them to ``cache/``. Cases are policy independent, so one pull serves every policy.
2. ``score``: run each policy on each case with the snapshot built at T. Since T <= every request ts and the
   request only carries information from before its ts, the policy never sees the future.
3. ``summarize`` (see ``stats.py``): per segment, ratio metrics with a paired bootstrap CI and the lift vs the baseline.
"""
from __future__ import annotations

import hashlib
import json
import logging
import pickle
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from ..config import CACHE
from ..policies.base import Policy
from ..rt import RawTree
from ..snapshot import Snapshot
from ..types import Request, parse_ts, sql_ts

log = logging.getLogger("eval")

# Position examination weights (logged clicks by slot, normalised to slot 1).
THETA = np.array([1.0, 0.559, 0.410, 0.318, 0.262, 0.235, 0.207, 0.183, 0.162, 0.152])
K = len(THETA)

SEGMENTS = ("all", "new_user", "home", "product_page", "category_page", "cold_item")
EVENT_TABLES = ("shop.history_events", "shop.events")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
SETTINGS = "SETTINGS max_execution_time = 300"


# ---- small helpers ----------------------------------------------------------------------------------------------

def theta_at(items: Sequence[str], target: str) -> float:
    """THETA weight of ``target``'s slot in ``items`` (0 if absent)."""
    for i, pid in enumerate(items[:K]):
        if pid == target:
            return float(THETA[i])
    return 0.0


def from_ms(ms: int | float) -> datetime:
    return EPOCH + timedelta(milliseconds=int(ms))


def to_ms(dt: datetime) -> int:
    return int(round((dt - EPOCH).total_seconds() * 1000))


def is_unknown_user(user_id: str, snap: Snapshot) -> bool:
    """New user = no organic event before T in the snapshot (not in user_buy nor user_view)."""
    return user_id not in snap.user_buy and user_id not in snap.user_view


def views_before(views: list[tuple[str, datetime]], ts: datetime) -> list[tuple[str, datetime]]:
    """Keep only views strictly before the request time (defensive: the policy must never see the future)."""
    return [(p, t) for p, t in views if t < ts]


def paged(rt: RawTree, sql_tpl: str, parts: int, key: str) -> list[dict]:
    """Run ``sql_tpl`` once per hash bucket ``cityHash64(key) % parts = i`` (placeholder ``{part}``) and concatenate."""
    rows: list[dict] = []
    for i in range(parts):
        rows.extend(rt.query(sql_tpl.replace("{part}", f"cityHash64({key}) % {parts} = {i}"), timeout=300))
    return rows


def hash_sample(key: str, rate: float, salt: str = "eval") -> str:
    """SQL predicate keeping a deterministic pseudo-random ``rate`` share of rows (salted so it is independent of paging)."""
    if rate >= 1.0:
        return "1"
    return f"cityHash64(concat({key}, '{salt}')) % 1000000 < {max(1, int(rate * 1_000_000))}"


def load_new_products(rt: RawTree) -> set[str]:
    """Products added during the event (catalog_updates 'new_product'), used only to define the cold_item segment.

    A product can only appear in a request's recent views after it exists, so using the full list does not leak
    future information into the segment. The snapshot's ``is_new`` flag alone misses products added at or after T.
    """
    rows = rt.query("SELECT DISTINCT product_id::String AS pid FROM shop.catalog_updates WHERE change::String = 'new_product'")
    return {r["pid"] for r in rows}


def event_source(rt: RawTree, start: datetime, end: datetime) -> tuple[str | None, datetime | None]:
    """SQL subquery over the organic event tables that overlap [start, end), filtered to that range in each branch.

    Columns: ts, et, u, s, p, dev, reg. Returns (sql or None if no table overlaps, latest event ts across tables).
    The latest ts tells the caller whether a live window is complete yet.
    """
    branches: list[str] = []
    latest: datetime | None = None
    for tbl in EVENT_TABLES:
        r = rt.query(f"SELECT count() AS n, min(ts::DateTime64(3)) AS lo, max(ts::DateTime64(3)) AS hi FROM {tbl}")[0]
        if not int(r["n"]):
            continue
        lo, hi = parse_ts(r["lo"]), parse_ts(r["hi"])
        latest = hi if latest is None else max(latest, hi)
        if lo < end and hi >= start:
            branches.append(
                "SELECT ts::DateTime64(3) AS ts, event_type::String AS et, user_id::String AS u, session_id::String AS s, "
                "product_id::String AS p, device::String AS dev, region::String AS reg "
                f"FROM {tbl} WHERE ts::DateTime64(3) >= '{sql_ts(start)}' AND ts::DateTime64(3) < '{sql_ts(end)}'"
            )
    if not branches:
        return None, latest
    return "(" + " UNION ALL ".join(branches) + ")", latest


# ---- data containers --------------------------------------------------------------------------------------------

@dataclass
class Case:
    """One evaluation unit: the request the policy sees and the evaluator-specific label (never shown to the policy)."""
    req: Request
    label: Any


@dataclass
class EvalSet:
    """Pulled evaluation data for one evaluator, cutoff T and window. ``complete`` = safe to cache."""
    evaluator: str
    T: datetime
    window_hours: float
    cases: list[Case]
    info: dict[str, Any] = field(default_factory=dict)
    complete: bool = True
    new_products: set[str] = field(default_factory=set)  # for the cold_item segment only


@dataclass
class PolicyRun:
    lists: list[list[str]]
    ms_per_call: float
    invalid: int  # answers that were not K distinct ids active in the snapshot


@dataclass
class Report:
    evaluator: str
    rows: list  # list[stats.Row]
    info: dict[str, Any]
    secs: dict[str, float]
    policy_runs: dict[str, dict[str, float]] = field(default_factory=dict)


# ---- policy execution and segments ----------------------------------------------------------------------------

def run_policies(policies: Sequence[Policy], reqs: Sequence[Request], snap: Snapshot) -> dict[str, PolicyRun]:
    """Call every policy on every request. Errors propagate: a crashing policy should fail the evaluation loudly."""
    out: dict[str, PolicyRun] = {}
    for pol in policies:
        t0 = time.perf_counter()
        lists: list[list[str]] = []
        invalid = 0
        for req in reqs:
            items = [str(p) for p in pol.recommend(req, snap)]
            if len(items) != K or len(set(items)) != K or not all(snap.is_valid(p) for p in items):
                invalid += 1
            lists.append(items[:K])
        secs = time.perf_counter() - t0
        out[pol.name] = PolicyRun(lists, 1000 * secs / max(1, len(reqs)), invalid)
        if invalid:
            log.warning("%s: %d/%d answers are not %d distinct active ids", pol.name, invalid, len(reqs), K)
    return out


def segment_masks(reqs: Sequence[Request], snap: Snapshot, new_products: set[str]) -> dict[str, np.ndarray]:
    """Boolean masks per segment (segments overlap; 'all' is every case).

    new_user: user unknown to the snapshot. home: no recent views. product_page / category_page: request context page.
    cold_item: a recent view is a product added during the event.
    """
    cold = {pid for pid, p in snap.products.items() if p.is_new} | new_products
    masks = {
        "all": [True for _ in reqs],
        "new_user": [is_unknown_user(r.user_id, snap) for r in reqs],
        "home": [not r.recent_views for r in reqs],
        "product_page": [r.page == "product" for r in reqs],
        "category_page": [r.page == "category" for r in reqs],
        "cold_item": [any(p in cold for p, _ in r.recent_views) for r in reqs],
    }
    return {k: np.array(v, dtype=bool) for k, v in masks.items()}


# ---- evaluator base -------------------------------------------------------------------------------------------

class Evaluator:
    """Base class. Subclasses set ``name`` and implement ``params``, ``pull`` and ``score``."""

    name = "base"

    def __init__(self, window_hours: float, n_boot: int = 500, seed: int = 0) -> None:
        self.window_hours = float(window_hours)
        self.n_boot = n_boot
        self.seed = seed

    def params(self) -> dict[str, Any]:
        """Parameters that change the pulled data (part of the cache key)."""
        return {}

    def window(self, T: datetime) -> tuple[datetime, datetime]:
        return T, T + timedelta(hours=self.window_hours)

    def pull(self, rt: RawTree, snap: Snapshot) -> EvalSet:
        raise NotImplementedError

    def score(self, policies: Sequence[Policy], snap: Snapshot, es: EvalSet) -> tuple[list, dict[str, PolicyRun]]:
        raise NotImplementedError

    def cache_path(self, T: datetime) -> Path:
        h = hashlib.md5(json.dumps(self.params(), sort_keys=True, default=str).encode()).hexdigest()[:8]
        return CACHE / f"eval_{self.name}_{T.strftime('%Y%m%dT%H%M%S')}_w{self.window_hours:g}h_{h}.pkl"

    def load(self, rt: RawTree, snap: Snapshot, use_cache: bool = True) -> EvalSet:
        path = self.cache_path(snap.T)
        if use_cache and path.exists():
            with path.open("rb") as f:
                log.info("%s: cached eval set %s", self.name, path.name)
                return pickle.load(f)
        es = self.pull(rt, snap)
        if use_cache and es.complete and es.cases:
            with path.open("wb") as f:
                pickle.dump(es, f, protocol=pickle.HIGHEST_PROTOCOL)
        elif not es.complete:
            log.warning("%s: window not complete yet (live data still arriving), eval set not cached", self.name)
        return es

    def run(self, rt: RawTree, snap: Snapshot, policies: Sequence[Policy], use_cache: bool = True) -> Report:
        t0 = time.time()
        es = self.load(rt, snap, use_cache)
        t1 = time.time()
        rows, runs = self.score(policies, snap, es) if es.cases else ([], {})
        t2 = time.time()
        if not es.cases:
            log.warning("%s: no cases in [%s, +%gh)", self.name, snap.T, self.window_hours)
        return Report(
            evaluator=self.name,
            rows=rows,
            info=es.info,
            secs={"load": round(t1 - t0, 1), "score": round(t2 - t1, 1)},
            policy_runs={p: {"ms_per_call": round(r.ms_per_call, 3), "invalid": r.invalid} for p, r in runs.items()},
        )
