"""Run a trained LgbmPolicy on recent live requests (no submission): latency and composition of its lists.

    python -m engine.learn.live_check --model cache/lgbm_live_<stamp>.txt [--n 300] [--snapshot PATH] [--compare ev-v2]

The snapshot defaults to cache/live_snapshot.pkl (kept by the live system) or the newest cache/snapshot_*.pkl.
Like the live runner, the catalogue and item counters are then refreshed (as of the first request) and recent
purchases are loaded with the live RECENT_BUYS_SQL; user tables stay as of the snapshot T (the live system
rebuilds them hourly). This is a serving simulation (latency, list composition), not an outcome evaluation.
"""
from __future__ import annotations

import argparse
import logging
import pickle
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from ..config import CACHE, TEAM
from ..features import build_context, featurize
from ..live import POLL_SQL, RECENT_BUYS_SQL
from .dataset import relation
from ..policies.lgbm import LgbmPolicy
from ..policies.prepare import prepare_snapshot
from ..rt import RawTree
from ..snapshot import Snapshot, _rank_lists, load_products, load_stats
from ..types import Request, sql_ts


def default_snapshot() -> Path:
    live = CACHE / "live_snapshot.pkl"
    if live.exists():
        return live
    return sorted(CACHE.glob("snapshot_*.pkl"))[-1]


def composition(lists: list[list[str]], reqs: list[Request], snap: Snapshot) -> dict[str, float]:
    n = len(lists)
    slot1_sess = slot1_last = slot1_uview = slot1_bought = 0
    bought = uview = sess = total = 0
    with_views = 0
    for items, req in zip(lists, reqs):
        viewed = req.viewed
        vset = set(viewed)
        ubuy = set(snap.user_buy.get(req.user_id, {})) | snap.recent_user_buys.get(req.user_id, set())
        uv = set(snap.user_view.get(req.user_id, {}))
        with_views += bool(viewed)
        first = items[0]
        slot1_sess += first in vset
        slot1_last += bool(viewed) and first == viewed[0]
        slot1_uview += first in uv
        slot1_bought += first in ubuy
        for pid in items:
            total += 1
            sess += pid in vset
            bought += pid in ubuy
            uview += pid in uv
    # exclusive relation of the slot-1 item (same definition as the training report)
    rel1: dict[str, int] = {}
    for items, req in zip(lists, reqs):
        r = str(relation(featurize(build_context(req, snap), snap, items[:1]))[0])
        rel1[r] = rel1.get(r, 0) + 1
    return {
        **{f"slot1_rel_{k}": v / n for k, v in sorted(rel1.items(), key=lambda x: -x[1])},
        "requests": n, "requests_with_session_views": with_views,
        "last_view_is_active_product": sum(bool(r.viewed) and snap.is_valid(r.viewed[0]) for r in reqs) / n,
        "slot1_session_view": slot1_sess / n, "slot1_session_view_given_views": slot1_sess / max(1, with_views),
        "slot1_last_view": slot1_last / n, "slot1_user_viewed_before": slot1_uview / n, "slot1_bought_before": slot1_bought / n,
        "items_session_view": sess / total, "items_bought_before": bought / total, "items_user_viewed_before": uview / total,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--snapshot", default=None)
    ap.add_argument("--compare", default="ev-v2", help="registry policy to compare with ('' to skip)")
    ap.add_argument("--bought-penalty", type=float, default=3.0)
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)

    rt = RawTree(timeout=120)
    path = Path(a.snapshot) if a.snapshot else default_snapshot()
    t0 = time.time()
    with path.open("rb") as f:
        snap: Snapshot = pickle.load(f)
    T_users = snap.T
    since = datetime.now(timezone.utc) - timedelta(minutes=max(3, a.n // 60))
    req_rows = rt.query(POLL_SQL.format(since=sql_ts(since)), timeout=60)
    reqs = [Request.from_row(r) for r in req_rows][-a.n:]
    # Same state as the live runner: catalogue (stock thread) and item counters (refresher) current as of the first
    # request, user tables from the last full snapshot, recent purchases from RECENT_BUYS_SQL.
    now = reqs[0].ts
    snap.products = load_products(rt, now)
    snap.stats = load_stats(rt, now)
    snap.T = now
    _rank_lists(snap)
    rows = rt.query(RECENT_BUYS_SQL.format(team=TEAM), timeout=60)
    snap.recent_user_buys = {r["u"]: set(r["ps"]) for r in rows}
    print(f"snapshot {path.name} users T={T_users:%Y-%m-%d %H:%M:%S}, catalogue/counters as of {now:%H:%M:%S} "
          f"(ready in {time.time() - t0:.1f}s); recent-buy users={len(snap.recent_user_buys)}; "
          f"requests={len(reqs)} from {reqs[0].ts:%H:%M:%S} to {reqs[-1].ts:%H:%M:%S}")

    policy = LgbmPolicy("lgbm-live", a.model, bought_penalty=a.bought_penalty)
    print(f"model {policy.model.path.name} kind={policy.model.kind}")
    t = time.perf_counter()
    prepare_snapshot(snap)
    print(f"prepare_snapshot (one-off; the live runner keeps these tables fresh): {1000 * (time.perf_counter() - t):.1f} ms")
    policy.recommend(reqs[0], snap)  # warm-up (LightGBM first call)

    def timed(pol):
        lists, lat, ncand = [], [], []
        for req in reqs:
            t1 = time.perf_counter()
            items = pol.recommend(req, snap)
            lat.append(1000 * (time.perf_counter() - t1))
            lists.append(items)
            assert len(items) == 10 and len(set(items)) == 10, (pol.name, req.request_id, items)
        return lists, np.asarray(lat)

    lists, lat = timed(policy)
    ncand = [len(policy.score_candidates(r, snap)[0]) for r in reqs]
    print(f"\nLATENCY lgbm ({len(reqs)} requests): p50={np.percentile(lat, 50):.1f} ms p95={np.percentile(lat, 95):.1f} ms "
          f"max={lat.max():.1f} ms mean={lat.mean():.1f} ms; candidates p50={int(np.median(ncand))} max={max(ncand)}")
    comp = {"lgbm": composition(lists, reqs, snap)}
    other = None
    if a.compare:
        from ..policies.registry import get_policy
        try:
            other = get_policy(a.compare)
            lists_o, lat_o = timed(other)
            comp[a.compare] = composition(lists_o, reqs, snap)
            print(f"LATENCY {a.compare}: p50={np.percentile(lat_o, 50):.1f} ms p95={np.percentile(lat_o, 95):.1f} ms max={lat_o.max():.1f} ms")
        except KeyError as e:
            print(f"compare policy unavailable: {e}")
            other = None
    print("\nCOMPOSITION (shares; slot1_rel_* = exclusive relation of the slot-1 item)")
    keys = list(dict.fromkeys(k for c in comp.values() for k in c))
    print(f"  {'metric':<34s} " + " ".join(f"{k:>10s}" for k in comp))
    for k in keys:
        vals = [c.get(k, 0.0) for c in comp.values()]
        print(f"  {k:<34s} " + " ".join(f"{v:>10.3f}" if isinstance(v, float) else f"{v:>10d}" for v in vals))
    if other is not None:
        overlap = np.mean([len(set(x) & set(y)) / 10 for x, y in zip(lists, lists_o)])
        same1 = np.mean([x[0] == y[0] for x, y in zip(lists, lists_o)])
        print(f"  overlap with {a.compare}: top-10 {overlap:.3f}, same slot-1 item {same1:.3f}")


if __name__ == "__main__":
    main()
