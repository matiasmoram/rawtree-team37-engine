"""Knowledge snapshot at time T: everything the recommender knows, built only from data with ts < T.

The same builder serves the live system (T = now) and the offline evaluators (T = a past cutoff),
so offline numbers never use information from the future.
"""
from __future__ import annotations

import logging
import pickle
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .config import CACHE
from .rt import RawTree
from .types import parse_ts, sql_ts

log = logging.getLogger("snapshot")

# Organic events: 60-day history plus the live stream, same schema.
EVENTS = """(
  SELECT ts::DateTime64(3) AS ts, event_type::String AS et, user_id::String AS u, session_id::String AS s, product_id::String AS p
  FROM shop.history_events
  UNION ALL
  SELECT ts::DateTime64(3) AS ts, event_type::String AS et, user_id::String AS u, session_id::String AS s, product_id::String AS p
  FROM shop.events
)"""

# Catalogue keys for joins: base catalogue plus products added during the event.
CATALOG_KEYS = """(
  SELECT product_id::String AS pid, category::String AS cat, subcategory::String AS sub FROM shop.catalog
  UNION ALL
  SELECT product_id::String AS pid, category::String AS cat, subcategory::String AS sub FROM shop.catalog_updates WHERE change::String = 'new_product'
)"""


@dataclass
class Product:
    pid: str
    cat: str
    sub: str
    brand: str
    price: float
    base_price: float
    descr: str
    active: bool
    is_new: bool = False  # added during the event (new_product update)
    added_ts: datetime | None = None
    price_changed_ts: datetime | None = None


@dataclass
class Snapshot:
    T: datetime
    products: dict[str, Product]
    stats: dict[str, dict[str, float]]                 # per product counters (see ITEM_STATS)
    carousel: dict[str, tuple[int, int, int]]          # pid -> (times shown, clicks, purchases) in logged carousel
    covis_vv: dict[str, list[tuple[str, float]]]       # viewed together in a session
    covis_vb: dict[str, list[tuple[str, float]]]       # viewed p, then bought q in the same session
    user_buy: dict[str, dict[str, tuple[int, datetime]]]  # user -> pid -> (purchases, last purchase ts)
    user_view: dict[str, dict[str, tuple[int, datetime]]]  # user -> pid -> (views+carts, last ts), top per user
    user_sub: dict[str, dict[str, float]]              # user -> subcategory -> decayed affinity
    user_cat: dict[str, dict[str, float]]              # user -> category -> decayed affinity
    user_price: dict[str, float]                       # user -> median purchase price
    pop_global: list[str] = field(default_factory=list)
    pop_by_cat: dict[str, list[str]] = field(default_factory=dict)
    pop_by_sub: dict[str, list[str]] = field(default_factory=dict)
    trending: list[str] = field(default_factory=list)
    build_secs: dict[str, float] = field(default_factory=dict)
    # Filled by the live system / policies after building:
    recent_user_buys: dict[str, set[str]] = field(default_factory=dict)  # purchases during the event, refreshed often
    sub_quality: dict[str, float] = field(default_factory=dict)          # subcategory conversion prior

    # ---- helpers used by policies -------------------------------------------------
    def is_valid(self, pid: str) -> bool:
        p = self.products.get(pid)
        return p is not None and p.active

    def pop_score(self, pid: str) -> float:
        """Recent purchase rate per day, blended long/short term. Comparable across products."""
        s = self.stats.get(pid)
        if not s:
            return 0.0
        return 0.5 * s["buy_7d"] / 7.0 + 0.3 * s["buy_all"] / 60.0 + 0.2 * s["buy_1d"]

    def trend_lift(self, pid: str) -> float:
        """Views in the last 3h relative to the 7-day average for a 3h window (1.0 = normal)."""
        s = self.stats.get(pid)
        if not s:
            return 1.0
        base = s["view_7d"] / (7 * 8)
        return (s["view_3h"] + 1.0) / (base + 1.0)


def _paged(rt: RawTree, sql_tpl: str, parts: int, key: str) -> list[dict]:
    rows: list[dict] = []
    for i in range(parts):
        rows.extend(rt.query(sql_tpl.format(part=f"cityHash64({key}) % {parts} = {i}"), timeout=300))
    return rows


def load_products(rt: RawTree, T: datetime) -> dict[str, Product]:
    base = rt.query(
        "SELECT product_id::String AS pid, category::String AS cat, subcategory::String AS sub, brand::String AS brand, "
        "price_eur::Float64 AS price, description::String AS descr, is_active::Bool AS active FROM shop.catalog"
    )
    products = {
        r["pid"]: Product(r["pid"], r["cat"], r["sub"], r["brand"], float(r["price"]), float(r["price"]), r["descr"], bool(r["active"]))
        for r in base
    }
    updates = rt.query(
        "SELECT product_id::String AS pid, change::String AS change, ts::DateTime64(3) AS ts, category::String AS cat, "
        "subcategory::String AS sub, brand::String AS brand, price_eur::Float64 AS price, description::String AS descr, "
        f"is_active::Bool AS active FROM shop.catalog_updates WHERE ts::DateTime64(3) < '{sql_ts(T)}' ORDER BY ts"
    )
    for r in updates:
        ts = parse_ts(r["ts"])
        p = products.get(r["pid"])
        if p is None:
            p = Product(r["pid"], r["cat"], r["sub"], r["brand"], float(r["price"]), float(r["price"]), r["descr"], bool(r["active"]))
            products[r["pid"]] = p
        if r["change"] == "new_product":
            p.is_new = True
            p.added_ts = ts
            p.base_price = float(r["price"])
        if r["change"] == "price_change" and abs(float(r["price"]) - p.price) > 1e-9:
            p.price_changed_ts = ts
        p.price = float(r["price"])
        p.active = bool(r["active"])
        p.cat, p.sub, p.brand, p.descr = r["cat"], r["sub"], r["brand"], r["descr"]
    return products


def load_stats(rt: RawTree, T: datetime) -> dict[str, dict[str, float]]:
    t = sql_ts(T)
    rows = rt.query(f"""
        SELECT p,
          countIf(et = 'purchase') AS buy_all, countIf(et = 'view') AS view_all, countIf(et = 'add_to_cart') AS cart_all,
          countIf(et = 'purchase' AND ts >= toDateTime64('{t}', 3) - INTERVAL 7 DAY) AS buy_7d,
          countIf(et = 'view' AND ts >= toDateTime64('{t}', 3) - INTERVAL 7 DAY) AS view_7d,
          countIf(et = 'purchase' AND ts >= toDateTime64('{t}', 3) - INTERVAL 1 DAY) AS buy_1d,
          countIf(et = 'view' AND ts >= toDateTime64('{t}', 3) - INTERVAL 1 DAY) AS view_1d,
          countIf(et = 'purchase' AND ts >= toDateTime64('{t}', 3) - INTERVAL 3 HOUR) AS buy_3h,
          countIf(et = 'view' AND ts >= toDateTime64('{t}', 3) - INTERVAL 3 HOUR) AS view_3h,
          countIf(et = 'view' AND ts >= toDateTime64('{t}', 3) - INTERVAL 1 HOUR) AS view_1h
        FROM {EVENTS}
        WHERE ts < '{t}' AND ts >= toDateTime64('{t}', 3) - INTERVAL 60 DAY
        GROUP BY p
        SETTINGS max_execution_time = 300""", timeout=300)
    return {r["p"]: {k: float(v) for k, v in r.items() if k != "p"} for r in rows}


def load_carousel(rt: RawTree, T: datetime) -> dict[str, tuple[int, int, int]]:
    rows = rt.query(f"""
        SELECT item, count() AS shown, countIf(item = clk) AS clicks, countIf(item = pur) AS buys
        FROM (SELECT item, ifNull(clicked::Nullable(String), '') AS clk, ifNull(purchased::Nullable(String), '') AS pur
              FROM shop.history_sessions ARRAY JOIN shown::Array(String) AS item
              WHERE ts::DateTime64(3) < '{sql_ts(T)}')
        GROUP BY item SETTINGS max_execution_time = 300""", timeout=300)
    return {r["item"]: (int(r["shown"]), int(r["clicks"]), int(r["buys"])) for r in rows}


def load_covis(rt: RawTree, T: datetime, top: int = 40) -> tuple[dict, dict]:
    t = sql_ts(T)
    window = f"ts < '{t}' AND ts >= toDateTime64('{t}', 3) - INTERVAL 60 DAY"
    vv = rt.query(f"""
        SELECT p, q, w FROM (
          SELECT a.p AS p, b.p AS q, sum(1 / (1 + abs(dateDiff('second', a.t, b.t)) / 600)) AS w
          FROM (SELECT s, p, min(ts) AS t FROM {EVENTS} WHERE et = 'view' AND {window} GROUP BY s, p) AS a
          INNER JOIN (SELECT s, p, min(ts) AS t FROM {EVENTS} WHERE et = 'view' AND {window} GROUP BY s, p) AS b ON a.s = b.s
          WHERE a.p != b.p GROUP BY p, q
        ) ORDER BY p, w DESC LIMIT {top} BY p SETTINGS max_execution_time = 300""", timeout=300)
    vb = rt.query(f"""
        SELECT p, q, w FROM (
          SELECT a.p AS p, b.p AS q, count() AS w
          FROM (SELECT s, p, min(ts) AS t FROM {EVENTS} WHERE et = 'view' AND {window} GROUP BY s, p) AS a
          INNER JOIN (SELECT s, p, min(ts) AS t FROM {EVENTS} WHERE et = 'purchase' AND {window} GROUP BY s, p) AS b ON a.s = b.s
          WHERE a.p != b.p AND a.t <= b.t GROUP BY p, q
        ) ORDER BY p, w DESC LIMIT {top} BY p SETTINGS max_execution_time = 300""", timeout=300)
    out = []
    for rows in (vv, vb):
        d: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for r in rows:
            d[r["p"]].append((r["q"], float(r["w"])))
        out.append(dict(d))
    return out[0], out[1]


def load_users(rt: RawTree, T: datetime, parts: int = 4) -> tuple[dict, dict, dict, dict, dict]:
    t = sql_ts(T)
    buys = _paged(rt, f"""
        SELECT u, p, count() AS n, max(ts) AS last FROM {EVENTS}
        WHERE et = 'purchase' AND ts < '{t}' AND {{part}} GROUP BY u, p SETTINGS max_execution_time = 300""", parts, "u")
    views = _paged(rt, f"""
        SELECT u, p, count() AS n, max(ts) AS last FROM {EVENTS}
        WHERE et IN ('view', 'add_to_cart') AND ts < '{t}' AND {{part}} GROUP BY u, p
        ORDER BY u, n DESC, last DESC LIMIT 25 BY u SETTINGS max_execution_time = 300""", parts * 2, "u")
    aff = _paged(rt, f"""
        SELECT e.u AS u, k.sub AS sub, k.cat AS cat,
               sum(multiIf(e.et = 'purchase', 5, e.et = 'add_to_cart', 3, 1)
                   * exp(-dateDiff('hour', e.ts, toDateTime64('{t}', 3)) / 336)) AS w
        FROM {EVENTS} AS e INNER JOIN {CATALOG_KEYS} AS k ON k.pid = e.p
        WHERE e.ts < '{t}' AND {{part}} GROUP BY u, sub, cat SETTINGS max_execution_time = 300""", parts, "e.u")
    price = _paged(rt, f"""
        SELECT u, quantile(0.5)(price_eur::Float64) AS med FROM (
          SELECT user_id::String AS u, price_eur, ts::DateTime64(3) AS ts FROM shop.history_events WHERE event_type::String = 'purchase'
          UNION ALL SELECT user_id::String AS u, price_eur, ts::DateTime64(3) AS ts FROM shop.events WHERE event_type::String = 'purchase')
        WHERE ts < '{t}' AND {{part}} GROUP BY u SETTINGS max_execution_time = 300""", parts, "u")

    user_buy: dict[str, dict] = defaultdict(dict)
    for r in buys:
        user_buy[r["u"]][r["p"]] = (int(r["n"]), parse_ts(r["last"]))
    user_view: dict[str, dict] = defaultdict(dict)
    for r in views:
        user_view[r["u"]][r["p"]] = (int(r["n"]), parse_ts(r["last"]))
    user_sub: dict[str, dict] = defaultdict(dict)
    user_cat: dict[str, dict] = defaultdict(lambda: defaultdict(float))
    for r in aff:
        user_sub[r["u"]][r["sub"]] = float(r["w"])
        user_cat[r["u"]][r["cat"]] += float(r["w"])
    user_price = {r["u"]: float(r["med"]) for r in price}
    return dict(user_buy), dict(user_view), dict(user_sub), {u: dict(v) for u, v in user_cat.items()}, user_price


def _rank_lists(snap: Snapshot) -> None:
    active = [pid for pid, p in snap.products.items() if p.active]
    scored = sorted(active, key=lambda pid: (snap.pop_score(pid), pid), reverse=True)
    snap.pop_global = scored[:300]
    by_cat: dict[str, list[str]] = defaultdict(list)
    by_sub: dict[str, list[str]] = defaultdict(list)
    for pid in scored:
        p = snap.products[pid]
        by_cat[p.cat].append(pid)
        by_sub[p.sub].append(pid)
    snap.pop_by_cat = {k: v[:100] for k, v in by_cat.items()}
    snap.pop_by_sub = {k: v[:60] for k, v in by_sub.items()}
    trend = [(snap.stats[pid]["view_3h"] * snap.trend_lift(pid), pid) for pid in active if pid in snap.stats]
    snap.trending = [pid for _, pid in sorted(trend, reverse=True)[:200]]


def build_snapshot(rt: RawTree, T: datetime | None = None, cache: bool = False) -> Snapshot:
    T = (T or datetime.now(timezone.utc)).astimezone(timezone.utc)
    path = CACHE / f"snapshot_{T.strftime('%Y%m%dT%H%M%S')}.pkl"
    if cache and path.exists():
        with path.open("rb") as f:
            return pickle.load(f)
    secs: dict[str, float] = {}

    def timed(name, fn, *args):
        t0 = time.time()
        out = fn(*args)
        secs[name] = round(time.time() - t0, 1)
        log.info("snapshot %s: %.1fs", name, secs[name])
        return out

    products = timed("products", load_products, rt, T)
    stats = timed("stats", load_stats, rt, T)
    carousel = timed("carousel", load_carousel, rt, T)
    covis_vv, covis_vb = timed("covis", load_covis, rt, T)
    user_buy, user_view, user_sub, user_cat, user_price = timed("users", load_users, rt, T)
    snap = Snapshot(T, products, stats, carousel, covis_vv, covis_vb, user_buy, user_view, user_sub, user_cat, user_price,
                    build_secs=secs)
    _rank_lists(snap)
    if cache:
        with path.open("wb") as f:
            pickle.dump(snap, f, protocol=pickle.HIGHEST_PROTOCOL)
    return snap


def refresh_fast(rt: RawTree, snap: Snapshot, now: datetime | None = None) -> None:
    """Cheap refresh for the live system: catalogue (stock, prices, new products) and item counters."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    snap.products = load_products(rt, now)
    snap.stats = load_stats(rt, now)
    snap.T = now
    _rank_lists(snap)


DELTA_WEIGHTS = {"purchase": 5.0, "add_to_cart": 3.0, "view": 1.0}


def apply_delta(rt: RawTree, snap: Snapshot, until: datetime | None = None) -> int:
    """Bring a snapshot forward to `until` using only live events since snap.T (small download).

    User tables are updated copy-on-write per user (a new dict is assigned), so a policy reading a
    user's dict in another thread never sees it change size mid-iteration. Co-visitation is kept as is.
    Returns the number of (user, product, event type) rows applied.
    """
    until = (until or datetime.now(timezone.utc)).astimezone(timezone.utc)
    rows = rt.query(f"""
        SELECT user_id::String AS u, product_id::String AS p, event_type::String AS et, count() AS n, max(ts::DateTime64(3)) AS last
        FROM shop.events WHERE ts::DateTime64(3) >= '{sql_ts(snap.T)}' AND ts::DateTime64(3) < '{sql_ts(until)}'
        GROUP BY u, p, et SETTINGS max_execution_time = 120""", timeout=150)
    products = load_products(rt, until)
    by_user: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_user[r["u"]].append(r)
    for u, items in by_user.items():
        ubuy = dict(snap.user_buy.get(u, {}))
        uview = dict(snap.user_view.get(u, {}))
        usub = dict(snap.user_sub.get(u, {}))
        ucat = dict(snap.user_cat.get(u, {}))
        for r in items:
            n, last, pid = int(r["n"]), parse_ts(r["last"]), r["p"]
            if r["et"] == "purchase":
                old = ubuy.get(pid, (0, last))
                ubuy[pid] = (old[0] + n, max(old[1], last))
            else:
                old = uview.get(pid, (0, last))
                uview[pid] = (old[0] + n, max(old[1], last))
            p = products.get(pid)
            if p is not None:
                w = DELTA_WEIGHTS.get(r["et"], 1.0) * n
                usub[p.sub] = usub.get(p.sub, 0.0) + w
                ucat[p.cat] = ucat.get(p.cat, 0.0) + w
        if ubuy:
            snap.user_buy[u] = ubuy
        if uview:
            snap.user_view[u] = uview
        snap.user_sub[u] = usub
        snap.user_cat[u] = ucat
    snap.products = products
    snap.stats = load_stats(rt, until)
    snap.T = until
    _rank_lists(snap)
    return len(rows)


def latest_cached(max_age_hours: float = 12.0) -> Snapshot | None:
    """Most recent pickled live snapshot (cache/live_snapshot.pkl) if not too old."""
    path = CACHE / "live_snapshot.pkl"
    if not path.exists():
        return None
    with path.open("rb") as f:
        snap = pickle.load(f)
    if (datetime.now(timezone.utc) - snap.T).total_seconds() > max_age_hours * 3600:
        return None
    return snap


def save_live(snap: Snapshot) -> None:
    tmp = CACHE / "live_snapshot.pkl.tmp"
    with tmp.open("wb") as f:
        pickle.dump(snap, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(CACHE / "live_snapshot.pkl")
