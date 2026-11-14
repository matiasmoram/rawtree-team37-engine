"""Per-user "carted, not bought" state, kept apart from views.

`snapshot.user_view` mixes views and add_to_cart events. Live feedback shows the two behave very
differently (carted-not-bought ~8x the base rate, viewed-only ~1x), so the cart-first policy needs carts alone.

    snap.user_cart: user -> {product_id: ts of the latest add_to_cart}

Items the user ever bought are excluded here and again in the policy (hard exclusion).
All writes are copy-on-write per user so request threads never iterate a dict that is changing.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from .rt import RawTree
from .snapshot import EVENTS, Snapshot, _paged
from .types import parse_ts, sql_ts

log = logging.getLogger("cartstate")

MAX_CARTS_PER_USER = 40


def load_user_carts(rt: RawTree, T: datetime, parts: int = 4) -> dict[str, dict[str, datetime]]:
    """Latest add_to_cart per (user, product) strictly before T, newest 40 per user (history + live events)."""
    t = sql_ts(T)
    rows = _paged(rt, f"""
        SELECT u, p, max(ts) AS last FROM {EVENTS}
        WHERE et = 'add_to_cart' AND ts < '{t}' AND {{part}} GROUP BY u, p
        ORDER BY u, last DESC LIMIT {MAX_CARTS_PER_USER} BY u SETTINGS max_execution_time = 300""", parts, "u")
    carts: dict[str, dict[str, datetime]] = defaultdict(dict)
    for r in rows:
        carts[r["u"]][r["p"]] = parse_ts(r["last"])
    return dict(carts)


def drop_bought(carts: dict[str, dict[str, datetime]], user_buy: dict[str, dict]) -> dict[str, dict[str, datetime]]:
    out: dict[str, dict[str, datetime]] = {}
    for u, items in carts.items():
        bought = user_buy.get(u)
        kept = {p: ts for p, ts in items.items() if not bought or p not in bought}
        if kept:
            out[u] = kept
    return out


def attach_user_carts(rt: RawTree, snap: Snapshot) -> None:
    snap.user_cart = drop_bought(load_user_carts(rt, snap.T), snap.user_buy)
    log.info("user_cart attached for %d users", len(snap.user_cart))


def refresh_user_carts(rt: RawTree, snap: Snapshot, since: datetime, until: datetime | None = None) -> datetime:
    """Fold new live add_to_cart events (ts >= since) into snap.user_cart. Returns the new watermark.

    Purchases seen in the same window remove the matching cart item, so a bought item stops being a candidate
    within one refresh. Callers pass a small overlap for `since`; re-applying an event is harmless.
    """
    until = (until or datetime.now(timezone.utc)).astimezone(timezone.utc)
    rows = rt.query(f"""
        SELECT user_id::String AS u, product_id::String AS p, event_type::String AS et, max(ts::DateTime64(3)) AS last
        FROM shop.events
        WHERE event_type::String IN ('add_to_cart', 'purchase')
          AND ts::DateTime64(3) >= '{sql_ts(since)}' AND ts::DateTime64(3) < '{sql_ts(until)}'
        GROUP BY u, p, et SETTINGS max_execution_time = 10""", timeout=8, retries=0)
    by_user: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_user[r["u"]].append(r)
    cart_state = getattr(snap, "user_cart", None)
    if cart_state is None:
        cart_state = snap.user_cart = {}
    for u, items in by_user.items():
        cur = dict(cart_state.get(u, {}))
        for r in items:
            ts = parse_ts(r["last"])
            if r["et"] == "add_to_cart":
                if ts > cur.get(r["p"], datetime.min.replace(tzinfo=timezone.utc)):
                    cur[r["p"]] = ts
            else:
                cur.pop(r["p"], None)
        if len(cur) > MAX_CARTS_PER_USER:
            cur = dict(sorted(cur.items(), key=lambda kv: kv[1], reverse=True)[:MAX_CARTS_PER_USER])
        if cur:
            cart_state[u] = cur
        else:
            cart_state.pop(u, None)
    return until - timedelta(seconds=2)
