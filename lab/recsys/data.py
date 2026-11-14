"""Pull everything we need from RawTree once and cache it locally (data/*.pkl).

Read-only: this module only runs SELECTs. Heavy aggregation happens inside RawTree (SQL);
only compact tables come back.

    python -m recsys.data            # pull / refresh the cache
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

for line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
    k, _, v = line.partition("=")
    if k.strip():
        os.environ.setdefault(k.strip(), v.strip())
API = os.environ.get("RAWTREE_API_URL", "https://api.rawtree.com")
TEAM = os.environ["TEAM_ID"]
_http = requests.Session()
_http.headers["Authorization"] = f"Bearer {os.environ['RAWTREE_API_KEY']}"

# History: 2026-09-15 → 2026-11-14 09:00 UTC. Last 7 days are the offline test period.
CUT = "2026-11-07 00:00:00"


def sql(q: str, timeout: int = 300) -> pd.DataFrame:
    if q.lstrip().split()[0].upper() not in {"SELECT", "WITH"}:
        raise ValueError("read-only")
    for attempt in range(3):
        r = _http.post(f"{API}/v1/query", json={"sql": q}, timeout=timeout)
        if r.ok:
            return pd.DataFrame(r.json()["data"])
        if r.status_code in (429, 502, 503, 504) and attempt < 2:
            time.sleep(2 + 3 * attempt)
            continue
        raise RuntimeError(f"{r.status_code}: {r.text[:600]}")
    raise RuntimeError("unreachable")


def paged(template: str, parts: int) -> pd.DataFrame:
    """Run a query split into `parts` by user hash ({part} and {parts} placeholders)."""
    return pd.concat([sql(template.format(part=i, parts=parts)) for i in range(parts)], ignore_index=True)


# ---------------------------------------------------------------- queries

Q = {
    "catalog": """
        SELECT product_id::String product_id, category::String category, subcategory::String subcategory,
               brand::String brand, price_eur::Float64 price, description::String description,
               is_active::Bool is_active, toString(created_at) created_at
        FROM shop.catalog""",

    "catalog_updates": """
        SELECT toString(ts) ts, change::String change, product_id::String product_id, category::String category,
               subcategory::String subcategory, brand::String brand, price_eur::Float64 price,
               description::String description, is_active::Bool is_active
        FROM shop.catalog_updates ORDER BY ts""",

    # user x category activity, split into before/after CUT (pre=1 means before the offline test cut)
    "user_cat": """
        SELECT e.user_id::String user_id, c.category::String category, (e.ts < '{cut}') pre,
               countIf(e.event_type='view') v, countIf(e.event_type='add_to_cart') c, countIf(e.event_type='purchase') p,
               sumIf(e.price_eur::Float64, e.event_type='purchase') spend
        FROM shop.history_events e INNER JOIN shop.catalog c ON c.product_id::String = e.product_id::String
        WHERE cityHash64(e.user_id::String) % {{parts}} = {{part}}
        GROUP BY user_id, category, pre""",

    "user_sub": """
        SELECT e.user_id::String user_id, c.subcategory::String subcategory, (e.ts < '{cut}') pre,
               countIf(e.event_type='view') v, countIf(e.event_type!='view') cp
        FROM shop.history_events e INNER JOIN shop.catalog c ON c.product_id::String = e.product_id::String
        WHERE cityHash64(e.user_id::String) % {{parts}} = {{part}}
        GROUP BY user_id, subcategory, pre
        HAVING cp > 0 OR v >= 2""",

    # item activity before / after CUT
    "item_stats": """
        SELECT product_id::String product_id, (ts < '{cut}') pre,
               countIf(event_type='view') v, countIf(event_type='add_to_cart') c, countIf(event_type='purchase') p,
               uniqExactIf(user_id::String, event_type='purchase') buyers
        FROM shop.history_events GROUP BY product_id, pre""",

    # item activity by context (device / region) for the cold-start prior, before CUT and all
    "ctx_cat": """
        SELECT device::String device, region::String region, c.category::String category, (e.ts < '{cut}') pre,
               countIf(event_type='purchase') p, countIf(event_type='view') v
        FROM shop.history_events e INNER JOIN shop.catalog c ON c.product_id::String = e.product_id::String
        GROUP BY device, region, category, pre""",

    # purchases (who bought what, when): to avoid re-recommending bought items and for item-item co-buys
    "purchases": """
        SELECT user_id::String user_id, product_id::String product_id, toString(ts) ts
        FROM shop.history_events WHERE event_type='purchase' AND cityHash64(user_id::String) % {{parts}} = {{part}}""",

    # co-views: top 30 products viewed in the same session as p (before CUT only, so it is safe for both tests)
    "coview": """
        SELECT p, q, n FROM (
          SELECT a.product_id p, b.product_id q, count() n
          FROM (SELECT session_id::String s, product_id::String product_id FROM shop.history_events
                WHERE event_type::String IN ('view','add_to_cart') AND ts < '{cut}' AND cityHash64(session_id::String) % 4 = {{part}}) a
          INNER JOIN (SELECT session_id::String s, product_id::String product_id FROM shop.history_events
                WHERE event_type::String IN ('view','add_to_cart') AND ts < '{cut}' AND cityHash64(session_id::String) % 4 = {{part}}) b
            ON a.s = b.s
          WHERE a.product_id != b.product_id
          GROUP BY p, q)
        ORDER BY n DESC LIMIT 30 BY p""",

    # carousel impressions: a train sample before CUT and a test sample after
    "sessions_train": """
        SELECT request_id::String request_id, toString(ts) ts, user_id::String user_id, context, recent_views,
               shown, propensity, clicked::String clicked, purchased::String purchased, revenue_eur::Float64 revenue
        FROM shop.history_sessions WHERE ts < '{cut}' AND ts >= '2026-10-10' AND cityHash64(request_id::String) % 20 = {{part}}""",

    "sessions_test": """
        SELECT request_id::String request_id, toString(ts) ts, user_id::String user_id, context, recent_views,
               shown, propensity, clicked::String clicked, purchased::String purchased, revenue_eur::Float64 revenue
        FROM shop.history_sessions WHERE ts >= '{cut}' AND cityHash64(request_id::String) % 20 = {{part}}""",

    # live: the requests our team answered (or the fallback answered), joined with the real outcome
    # live: every request so far, and our team's feedback (real outcome of what was shown); joined locally
    "live_requests": """
        SELECT request_id::String request_id, toString(ts) ts, user_id::String user_id,
               is_new_user::Bool is_new_user, context, recent_views
        FROM shop.requests""",

    "feedback": """
        SELECT request_id::String request_id, toString(ts) fb_ts, shown, served_by::String served_by,
               fallback_reason::String fallback_reason, clicked::String clicked, purchased::String purchased,
               revenue_eur::Float64 revenue, latency_ms
        FROM {team}.feedback WHERE request_id::String != '__init__'""",

    # live organic activity aggregated per user x category (to add to history for the live test)
    "live_user_cat": """
        SELECT e.user_id::String user_id, c.category::String category,
               countIf(e.event_type='view') v, countIf(e.event_type='add_to_cart') c, countIf(e.event_type='purchase') p,
               toString(min(e.ts)) first_ts
        FROM shop.events e INNER JOIN shop.catalog c ON c.product_id::String = e.product_id::String
        WHERE e.ts < '{live_cut}'
        GROUP BY user_id, category""",

    "live_item_stats": """
        SELECT product_id::String product_id, countIf(event_type='view') v, countIf(event_type='add_to_cart') c,
               countIf(event_type='purchase') p
        FROM shop.events WHERE ts < '{live_cut}' GROUP BY product_id""",

    "live_purchases": """
        SELECT user_id::String user_id, product_id::String product_id, toString(ts) ts
        FROM shop.events WHERE event_type='purchase' AND ts < '{live_cut}'""",
}


def pull(name: str, refresh: bool = False, **fmt) -> pd.DataFrame:
    path = DATA / f"{name}.pkl"
    if path.exists() and not refresh:
        return pd.read_pickle(path)
    t = time.time()
    q = Q[name].format(cut=CUT, team=TEAM, **fmt)
    if name in ("user_cat", "user_sub"):
        df = paged(q, parts=8)
    elif name == "purchases":
        df = paged(q, parts=2)
    elif name == "coview":
        df = pd.concat([sql(q.format(part=i)) for i in range(4)], ignore_index=True)
        df = df.groupby(["p", "q"], as_index=False).n.sum()
        df = df.sort_values(["p", "n"], ascending=[True, False]).groupby("p").head(30)
    elif name == "sessions_train":
        df = pd.concat([sql(q.format(part=i)) for i in range(4)], ignore_index=True)   # 20% sample
    elif name == "sessions_test":
        df = pd.concat([sql(q.format(part=i)) for i in range(20)], ignore_index=True)  # all of the last 7 days
    else:
        df = sql(q)
    df.to_pickle(path)
    print(f"{name}: {len(df):,} rows in {time.time() - t:.1f}s", flush=True)
    return df


def live_feedback(refresh: bool = False) -> pd.DataFrame:
    """Live requests our team was scored on, with what was shown and what happened."""
    req, fb = pull("live_requests", refresh), pull("feedback", refresh)
    return req.merge(fb, on="request_id", how="inner").sort_values("ts").reset_index(drop=True)


def live_cut() -> str:
    """Start of the live test window: features for the live test use only events before this."""
    return str(pd.to_datetime(live_feedback().ts).min().floor("min"))


def pull_all(refresh: bool = False) -> None:
    for name in ["catalog", "catalog_updates", "item_stats", "ctx_cat", "user_cat", "user_sub", "purchases",
                 "coview", "sessions_train", "sessions_test", "live_requests", "feedback"]:
        pull(name, refresh=refresh)
    lc = live_cut()
    for name in ["live_user_cat", "live_item_stats", "live_purchases"]:
        pull(name, refresh=refresh, live_cut=lc)


if __name__ == "__main__":
    pull_all(refresh="--refresh" in sys.argv)
