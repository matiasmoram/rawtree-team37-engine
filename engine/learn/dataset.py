"""Training table from live feedback: one row per item the shopper actually saw.

For every request in [since, until) that has a feedback row (team or fallback) we rebuild the ``Request`` from
``shop.requests`` and featurize its 10 ``shown`` items with their logged positions (``slot`` = 0..9), exactly as the
serving policy featurizes candidates (``engine.features``), plus the labels ``click`` and ``purchase``.

Knowledge used for the features (no leakage: everything is strictly before the request ts):

- ONE snapshot built at T0 = ``since`` (user histories, co-visitation, item counters, carousel stats). Every request
  in the range is at or after T0, so no snapshot feature uses data from after any training request.
  Trade-off: the snapshot gets staler along the range (at most ``until - since``), while the live system rebuilds it
  every hour and refreshes item counters every minute. Features that move fast (``log_view_3h``, ``log_trend``,
  ``log_buy_1d``, user histories of users active during the range) are therefore older in training than in serving.
  Retraining on a short recent window (see docs/live_ranker.md) keeps that gap small.
- Point-in-time catalogue: catalogue updates with ts in [T0, request ts) are replayed in order on a copy of the
  snapshot's products (prices, stock, new products), like the live ``stock`` thread does.
- Point-in-time recent purchases (feature ``bought_in_event``): purchases in [request ts - 6 h, request ts) from
  ``shop.events`` and from our own feedback (feedback ts < request ts), the same sources and lookback as the live
  ``RECENT_BUYS_SQL``.

The table is cached in ``cache/live_ds_<version>_<since>_<until>.pkl``.
"""
from __future__ import annotations

import bisect
import copy
import logging
import pickle
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from ..config import CACHE, TEAM
from ..features import FEATURES, FIDX, build_context, featurize
from ..policies.prepare import prepare_snapshot
from ..rt import RawTree
from ..snapshot import Product, Snapshot, build_snapshot
from ..types import Request, parse_ts, sql_ts

log = logging.getLogger("learn.dataset")

DATASET_VERSION = "v1"
RECENT_BUYS_WINDOW = timedelta(hours=6)   # same lookback as engine.live.RECENT_BUYS_SQL
FEEDBACK_SLACK = timedelta(minutes=10)    # feedback ts is ~4 s after the request ts
META_COLS = ["request_id", "ts", "user_id", "pid", "click", "purchase", "served_by", "fallback_reason", "model_version"]

# Feedback joined with the request (to rebuild it) and our submission (model_version). Aliases never repeat a
# source column name: ClickHouse resolves SELECT aliases inside WHERE.
FEEDBACK_SQL = """
SELECT f.rid AS request_id, f.shown_items AS shown, f.clk AS clicked, f.pur AS purchased, f.sb AS served_by,
       f.fr AS fallback_reason, r.rts AS ts, r.uid AS user_id, r.new_user AS is_new_user, r.pg AS page,
       r.dev AS device, r.reg AS region, r.views AS recent_views,
       if(f.sb != 'team', '', if(s.mv = '', '(unmatched)', s.mv)) AS model_version
FROM (SELECT request_id::String AS rid, shown::Array(String) AS shown_items,
             ifNull(clicked::Nullable(String), '') AS clk, ifNull(purchased::Nullable(String), '') AS pur,
             served_by::String AS sb, ifNull(fallback_reason::Nullable(String), '') AS fr
      FROM {team}.feedback
      WHERE request_id::String != '__init__' AND ts::DateTime64(3) >= '{fb_lo}' AND ts::DateTime64(3) < '{fb_hi}'
        AND cityHash64(request_id::String) % {parts} = {part}) AS f
INNER JOIN (SELECT request_id::String AS rid, ts::DateTime64(3) AS rts, user_id::String AS uid,
                   is_new_user::Bool AS new_user, context.page::String AS pg, context.device::String AS dev,
                   context.region::String AS reg, recent_views AS views
            FROM shop.requests
            WHERE ts::DateTime64(3) >= '{lo}' AND ts::DateTime64(3) < '{hi}'
              AND cityHash64(request_id::String) % {parts} = {part}) AS r ON r.rid = f.rid
LEFT JOIN (SELECT request_id::String AS rid, items::Array(String) AS sent_items,
                  if(uniqExact(model_version::String) = 1, any(model_version::String), '(ambiguous)') AS mv
           FROM {team}.submissions
           WHERE cityHash64(request_id::String) % {parts} = {part} GROUP BY rid, sent_items) AS s
           ON s.rid = f.rid AND s.sent_items = f.shown_items
SETTINGS max_execution_time = 300"""

# Purchases that the live system would know as "recent buys" at request time (see engine.live.RECENT_BUYS_SQL),
# restricted to users that appear in the range.
RECENT_BUYS_SQL = """
SELECT u, p, t FROM (
  SELECT user_id::String AS u, product_id::String AS p, ts::DateTime64(3) AS t FROM shop.events
  WHERE event_type::String = 'purchase' AND ts::DateTime64(3) >= '{lo6}' AND ts::DateTime64(3) < '{hi}'
  UNION ALL
  SELECT r.uid AS u, f.pur AS p, f.fts AS t
  FROM (SELECT request_id::String AS rid, ifNull(purchased::Nullable(String), '') AS pur, ts::DateTime64(3) AS fts
        FROM {team}.feedback
        WHERE request_id::String != '__init__' AND ts::DateTime64(3) >= '{lo6}' AND ts::DateTime64(3) < '{hi}') AS f
  INNER JOIN (SELECT request_id::String AS rid, user_id::String AS uid FROM shop.requests
              WHERE ts::DateTime64(3) >= toDateTime64('{lo6}', 3) - INTERVAL 1 HOUR AND ts::DateTime64(3) < '{hi}') AS r
    ON r.rid = f.rid
  WHERE f.pur != ''
) WHERE u IN (SELECT user_id::String FROM shop.requests WHERE ts::DateTime64(3) >= '{lo}' AND ts::DateTime64(3) < '{hi}')
SETTINGS max_execution_time = 300"""

UPDATES_SQL = """
SELECT product_id::String AS pid, change::String AS change, ts::DateTime64(3) AS uts, category::String AS cat,
       subcategory::String AS sub, brand::String AS brand, price_eur::Float64 AS price, description::String AS descr,
       is_active::Bool AS active
FROM shop.catalog_updates WHERE ts::DateTime64(3) >= '{lo}' AND ts::DateTime64(3) < '{hi}' ORDER BY uts"""


# ---- loaders ----------------------------------------------------------------------------------------------------

def load_feedback(rt: RawTree, since: datetime, until: datetime, parts: int = 4) -> list[dict]:
    rows: list[dict] = []
    for part in range(parts):
        rows.extend(rt.query(FEEDBACK_SQL.format(
            team=TEAM, lo=sql_ts(since), hi=sql_ts(until), fb_lo=sql_ts(since), fb_hi=sql_ts(until + FEEDBACK_SLACK),
            parts=parts, part=part), timeout=300))
    return rows


def load_recent_buys(rt: RawTree, since: datetime, until: datetime) -> dict[str, tuple[list[datetime], list[str]]]:
    rows = rt.query(RECENT_BUYS_SQL.format(team=TEAM, lo6=sql_ts(since - RECENT_BUYS_WINDOW), lo=sql_ts(since),
                                           hi=sql_ts(until)), timeout=300)
    by_user: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for r in rows:
        by_user[r["u"]].append((parse_ts(r["t"]), r["p"]))
    out = {}
    for u, events in by_user.items():
        events.sort()
        out[u] = ([t for t, _ in events], [p for _, p in events])
    return out


def recent_buys_at(buys: dict[str, tuple[list[datetime], list[str]]], user: str, ts: datetime) -> set[str]:
    """Products the user bought in [ts - 6 h, ts)."""
    if user not in buys:
        return set()
    times, pids = buys[user]
    lo = bisect.bisect_left(times, ts - RECENT_BUYS_WINDOW)
    hi = bisect.bisect_left(times, ts)
    return set(pids[lo:hi])


class CatalogReplay:
    """Point-in-time catalogue: a private copy of the snapshot's products, advanced update by update."""

    def __init__(self, snap: Snapshot, updates: list[dict]) -> None:
        self.products: dict[str, Product] = {pid: copy.copy(p) for pid, p in snap.products.items()}
        self.updates = [(parse_ts(u["uts"]), u) for u in updates]
        self.i = 0

    def advance(self, ts: datetime) -> None:
        """Apply every update with ts < ``ts`` (same rules as ``snapshot.load_products``)."""
        while self.i < len(self.updates) and self.updates[self.i][0] < ts:
            uts, r = self.updates[self.i]
            self.i += 1
            p = self.products.get(r["pid"])
            if p is None:
                p = Product(r["pid"], r["cat"], r["sub"], r["brand"], float(r["price"]), float(r["price"]), r["descr"],
                            bool(r["active"]))
                self.products[r["pid"]] = p
            if r["change"] == "new_product":
                p.is_new = True
                p.added_ts = uts
                p.base_price = float(r["price"])
            if r["change"] == "price_change" and abs(float(r["price"]) - p.price) > 1e-9:
                p.price_changed_ts = uts
            p.price = float(r["price"])
            p.active = bool(r["active"])
            p.cat, p.sub, p.brand, p.descr = r["cat"], r["sub"], r["brand"], r["descr"]


# ---- builder ----------------------------------------------------------------------------------------------------

def cache_path(since: datetime, until: datetime):
    return CACHE / f"live_ds_{DATASET_VERSION}_{since:%Y%m%dT%H%M%S}_{until:%Y%m%dT%H%M%S}.pkl"


def build_dataset(rt: RawTree, since: datetime, until: datetime, snap: Snapshot | None = None,
                  cache: bool = True) -> tuple[pd.DataFrame, dict]:
    """Return (table, meta). ``table`` has FEATURES (float32) + META_COLS; one row per shown item."""
    since = since.astimezone(timezone.utc)
    until = until.astimezone(timezone.utc)
    path = cache_path(since, until)
    if cache and path.exists():
        with path.open("rb") as f:
            obj = pickle.load(f)
        log.info("dataset from cache %s", path.name)
        return obj["df"], obj["meta"]

    t0 = time.time()
    if snap is None:
        snap = build_snapshot(rt, since, cache=True)
    if snap.T != since:
        raise ValueError(f"snapshot T={snap.T} must equal the start of the range {since}")
    prepare_snapshot(snap)
    t_snap = time.time() - t0

    t1 = time.time()
    fb = load_feedback(rt, since, until)
    buys = load_recent_buys(rt, since, until)
    updates = rt.query(UPDATES_SQL.format(lo=sql_ts(since), hi=sql_ts(until)), timeout=120)
    t_load = time.time() - t1
    log.info("loaded feedback=%d recent-buy users=%d catalogue updates=%d in %.1fs", len(fb), len(buys), len(updates), t_load)

    reqs = []
    for row in fb:
        req = Request.from_row(row)
        if since <= req.ts < until:
            reqs.append((req, row))
    reqs.sort(key=lambda x: (x[0].ts, x[0].request_id))

    replay = CatalogReplay(snap, updates)
    pit = copy.copy(snap)              # shallow copy: shares the heavy tables, owns its products and recent buys
    pit.products = replay.products
    pit.recent_user_buys = {}

    t2 = time.time()
    blocks: list[np.ndarray] = []
    meta_rows: dict[str, list] = {c: [] for c in META_COLS}
    n_unknown_items = n_dup_items = n_empty = 0
    for req, row in reqs:
        shown = [str(p) for p in (row["shown"] or [])]
        if not shown:
            n_empty += 1
            continue
        replay.advance(req.ts)
        ctx = build_context(req, pit)
        ctx.recent_buys = recent_buys_at(buys, req.user_id, req.ts)
        # Keep each known product once, at its first position (the slot the shopper saw it in).
        items, slots, seen = [], [], set()
        for slot, pid in enumerate(shown):
            if pid in seen:
                n_dup_items += 1
                continue
            seen.add(pid)
            if pid not in pit.products:
                n_unknown_items += 1   # featurize would leave an all-zero row: drop it
                continue
            items.append(pid)
            slots.append(slot)
        if not items:
            continue
        blocks.append(featurize(ctx, pit, items, slots=slots))
        clicked, purchased = str(row["clicked"] or ""), str(row["purchased"] or "")
        for pid in items:
            meta_rows["request_id"].append(req.request_id)
            meta_rows["ts"].append(req.ts)
            meta_rows["user_id"].append(req.user_id)
            meta_rows["pid"].append(pid)
            meta_rows["click"].append(int(pid == clicked))
            meta_rows["purchase"].append(int(pid == purchased))
            meta_rows["served_by"].append(str(row["served_by"]))
            meta_rows["fallback_reason"].append(str(row["fallback_reason"]))
            meta_rows["model_version"].append(str(row["model_version"]))
    t_feat = time.time() - t2

    X = np.vstack(blocks) if blocks else np.zeros((0, len(FEATURES)), dtype=np.float32)
    df = pd.DataFrame(X, columns=FEATURES)
    for c in META_COLS:
        df[c] = meta_rows[c]
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["click"] = df["click"].astype(np.int8)
    df["purchase"] = df["purchase"].astype(np.int8)

    # Requests whose clicked / purchased id is not among the kept shown items (should not happen).
    per_req = df.groupby("request_id")[["click", "purchase"]].sum()
    fb_clicks = sum(1 for _, r in reqs if r["clicked"])
    fb_buys = sum(1 for _, r in reqs if r["purchased"])
    meta = {
        "version": DATASET_VERSION, "since": since.isoformat(), "until": until.isoformat(), "snapshot_T0": snap.T.isoformat(),
        "requests": int(df["request_id"].nunique()), "rows": int(len(df)),
        "clicks": int(df["click"].sum()), "purchases": int(df["purchase"].sum()),
        "feedback_clicks": fb_clicks, "feedback_purchases": fb_buys,
        "requests_multi_click": int((per_req["click"] > 1).sum()),
        "rows_team": int((df["served_by"] == "team").sum()), "rows_fallback": int((df["served_by"] == "fallback").sum()),
        "unknown_items_dropped": n_unknown_items, "duplicate_items_dropped": n_dup_items, "empty_shown": n_empty,
        "catalog_updates_replayed": replay.i, "recent_buy_users": len(buys),
        "rows_bought_in_event": int((df["bought_in_event"] > 0).sum()),
        "secs": {"snapshot": round(t_snap, 1), "load": round(t_load, 1), "featurize": round(t_feat, 1)},
    }
    log.info("dataset: %s", {k: v for k, v in meta.items() if k != "secs"})
    if cache:
        with path.open("wb") as f:
            pickle.dump({"df": df, "meta": meta}, f, protocol=pickle.HIGHEST_PROTOCOL)
    return df, meta


def relation(X: np.ndarray) -> np.ndarray:
    """Exclusive relation of each item to the shopper (same order as scripts/live_attribution.py)."""
    F = FIDX
    conds = [
        X[:, F["is_last_view"]] > 0,
        X[:, F["view_rank"]] < 9,
        (X[:, F["user_bought_n"]] > 0) | (X[:, F["bought_in_event"]] > 0),
        X[:, F["user_viewed_n"]] > 0,
        X[:, F["sess_sub_share"]] > 0,
        X[:, F["sess_cat_share"]] > 0,
        X[:, F["n_session_views"]] == 0,
    ]
    names = ["viewed_last", "viewed_earlier", "user_bought", "user_viewed", "same_sub", "same_cat", "other_home"]
    return np.select(conds, names, default="other")
