"""Read-only extraction from the RawTree DB (ClickHouse over HTTP) for the Tukey dashboard.

Every query is a SELECT taken from docs/data_inventory.md (verified there) and parametrised by a period.
Credentials are read from the engine repo's .env (never printed, never copied).
Outputs: data/raw/db/{period}/{query}.json  -> {"sql":..., "rows":[...], "secs":...}

Usage (from tukey_dashboard/):
  .venv/Scripts/python.exe pipeline/extract_db.py --period practice
  .venv/Scripts/python.exe pipeline/extract_db.py --period final      # after Sun 11:00 UTC
Periods are UTC (CET = UTC+1). Practice = team start .. final start; final = 09:00-11:00 UTC.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT.parent / ".env"
if not ENV.exists():
    ENV = ROOT.parent / "rawtree_team37_engine" / ".env"
OUT = ROOT / "data" / "raw" / "db"
FORBID = ("insert", "alter", "drop", "delete", "update", "create", "truncate", "optimize", "rename", "kill", "grant")

PERIODS = {
    "practice": ("2026-11-14 12:09:00", "2026-11-15 09:00:00"),
    "final": ("2026-11-15 09:00:00", "2026-11-15 11:00:00"),
}


def load_env() -> dict[str, str]:
    env = {}
    for raw in ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class DB:
    def __init__(self) -> None:
        env = load_env()
        self.url = env.get("RAWTREE_API_URL", "https://api.rawtree.com") + "/v1/query"
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {env['RAWTREE_API_KEY']}"

    def query(self, sql: str) -> list[dict]:
        low = sql.strip().lower()
        assert low.split()[0] in ("select", "with"), "read-only queries only"
        assert not any(f" {w} " in f" {low} " for w in FORBID), "forbidden keyword"
        for attempt in range(3):
            try:
                r = self.s.post(self.url, json={"sql": sql}, timeout=(5, 35))
            except requests.RequestException:
                time.sleep(1 + attempt)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(1 + attempt)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:500]}")
            return r.json()["data"]
        raise RuntimeError("query failed after retries")


NEWP = "(SELECT groupArray(product_id::String) FROM shop.catalog_updates WHERE change::String = 'new_product')"
RV = "JSONExtract(toJSONString(__raw_data), 'recent_views', 'Array(Tuple(product_id String, ts String))')"
FB = """SELECT request_id::String AS rid, ts::DateTime64(3) AS fts, served_by::String AS sb, fallback_reason::String AS fr,
       clicked::String AS clk, purchased::String AS pur, revenue_eur::Float64 AS rev, latency_ms::Nullable(Float64) AS lat,
       shown::Array(String) AS shown_items
FROM team_37.feedback WHERE request_id::String != '__init__'"""


def queries(t0: str, t1: str) -> dict[str, str]:
    req = f"FROM shop.requests WHERE ts::DateTime64(3) >= '{t0}' AND ts::DateTime64(3) < '{t1}'"
    return {
        # 10-minute reliability / outcome series (outage detector, dilution identity)
        "buckets10m": f"""
SELECT intDiv(toUnixTimestamp(r.ts), 600) * 600 AS t, count() AS requests,
       countIf(f.sb = 'team') AS served_team, countIf(f.fr = 'missing') AS missing, countIf(f.fr = 'invalid') AS invalid,
       countIf(f.rid = '') AS no_feedback, countIf(f.clk != '') AS clicks, countIf(f.pur != '') AS purchases,
       round(sum(f.rev), 2) AS revenue, countIf(r.cold) AS cold_requests, countIf(r.cold AND f.pur != '') AS cold_purchases,
       countIf(f.sb = 'team' AND f.pur != '') AS team_purchases, countIf(f.sb != 'team' AND f.pur != '') AS fallback_purchases,
       quantileIf(0.5)(f.lat, f.sb = 'team') AS p50_ms, quantileIf(0.95)(f.lat, f.sb = 'team') AS p95_ms
FROM (SELECT request_id::String AS rid, ts::DateTime64(3) AS ts,
             is_new_user::Bool OR hasAny({RV}.product_id, {NEWP}) AS cold {req}) AS r
LEFT JOIN ({FB}) AS f ON f.rid = r.rid
GROUP BY t ORDER BY t SETTINGS max_execution_time = 28""",
        # Tukey five-number(+) summaries of latency per hour, team-served answers only
        "latency_hourly": f"""
SELECT toUnixTimestamp(toStartOfHour(f.fts)) AS t, count() AS n,
       quantilesExact(0, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1)(f.lat) AS q,
       countIf(f.lat > 3000) AS over_3000
FROM ({FB}) AS f WHERE f.sb = 'team' AND f.fts >= '{t0}' AND f.fts < '{t1}'
GROUP BY t ORDER BY t SETTINGS max_execution_time = 28""",
        # raw latency sample for the strip/raincloud layer (deterministic hash sample)
        "latency_sample": f"""
SELECT toUnixTimestamp(f.fts) AS t, f.lat AS lat
FROM ({FB}) AS f WHERE f.sb = 'team' AND f.fts >= '{t0}' AND f.fts < '{t1}' AND cityHash64(f.rid) % 40 = 0
ORDER BY t SETTINGS max_execution_time = 28""",
        # relation of each shown item to the shopper x slot (first match wins), team vs fallback
        "relation_slot": f"""
WITH {NEWP} AS newp
SELECT sb, slot, relation, count() AS impressions, countIf(clk = pid) AS clicks, countIf(pur = pid) AS purchases
FROM (
  SELECT s.sb AS sb, s.slot AS slot, s.pid AS pid, s.clk AS clk, s.pur AS pur,
         multiIf(arrayExists(x -> x < s.rts, e.buys), 'bought_before',
                 arrayExists(x -> x < s.rts, e.carts), 'carted_not_bought',
                 length(s.rv) = 0, 'no_session_views',
                 s.pid = s.rv[length(s.rv)], 'session_last_view',
                 has(s.rv, s.pid), 'session_earlier_view',
                 has(newp, s.pid), 'new_product_other', 'other') AS relation
  FROM (
    SELECT f.sb AS sb, r.uid AS uid, r.rts AS rts, r.rv AS rv, f.clk AS clk, f.pur AS pur, pid, slot
    FROM ({FB}) AS f
    INNER JOIN (SELECT request_id::String AS rid, user_id::String AS uid, ts::DateTime64(3) AS rts,
                       arrayMap(x -> x.1, arraySort(x -> x.2, {RV})) AS rv {req}) AS r ON r.rid = f.rid
    ARRAY JOIN f.shown_items AS pid, arrayEnumerate(f.shown_items) AS slot
  ) AS s
  LEFT JOIN (
    SELECT u, p, groupArrayIf(t, et = 'purchase') AS buys, groupArrayIf(t, et = 'add_to_cart') AS carts
    FROM (
      SELECT user_id::String AS u, product_id::String AS p, ts::DateTime64(3) AS t, event_type::String AS et FROM shop.history_events
      WHERE event_type::String IN ('purchase', 'add_to_cart') AND user_id::String IN (SELECT user_id::String {req})
      UNION ALL
      SELECT user_id::String AS u, product_id::String AS p, ts::DateTime64(3) AS t, event_type::String AS et FROM shop.events
      WHERE event_type::String IN ('purchase', 'add_to_cart') AND ts::DateTime64(3) < '{t1}'
        AND user_id::String IN (SELECT user_id::String {req})
    ) GROUP BY u, p
  ) AS e ON e.u = s.uid AND e.p = s.pid
)
GROUP BY sb, slot, relation ORDER BY sb, relation, slot SETTINGS max_execution_time = 28""",
        # share of team-served slots by relation, per hour (before/after the re-buy ban)
        "relation_hourly": f"""
SELECT h, sb, relation, count() AS impressions, countIf(pur = pid) AS purchases
FROM (
  SELECT s.h AS h, s.sb AS sb, s.pid AS pid, s.pur AS pur,
         multiIf(arrayExists(x -> x < s.rts, e.buys), 'bought_before',
                 arrayExists(x -> x < s.rts, e.carts), 'carted_not_bought', 'other') AS relation
  FROM (
    SELECT toUnixTimestamp(toStartOfHour(r.rts)) AS h, f.sb AS sb, r.uid AS uid, r.rts AS rts, f.pur AS pur, pid
    FROM ({FB}) AS f
    INNER JOIN (SELECT request_id::String AS rid, user_id::String AS uid, ts::DateTime64(3) AS rts {req}) AS r ON r.rid = f.rid
    ARRAY JOIN f.shown_items AS pid
  ) AS s
  LEFT JOIN (
    SELECT u, p, groupArrayIf(t, et = 'purchase') AS buys, groupArrayIf(t, et = 'add_to_cart') AS carts
    FROM (
      SELECT user_id::String AS u, product_id::String AS p, ts::DateTime64(3) AS t, event_type::String AS et FROM shop.history_events
      WHERE event_type::String IN ('purchase', 'add_to_cart') AND user_id::String IN (SELECT user_id::String {req})
      UNION ALL
      SELECT user_id::String AS u, product_id::String AS p, ts::DateTime64(3) AS t, event_type::String AS et FROM shop.events
      WHERE event_type::String IN ('purchase', 'add_to_cart') AND ts::DateTime64(3) < '{t1}'
        AND user_id::String IN (SELECT user_id::String {req})
    ) GROUP BY u, p
  ) AS e ON e.u = s.uid AND e.p = s.pid
)
GROUP BY h, sb, relation ORDER BY h, sb, relation SETTINGS max_execution_time = 28""",
        # realised outcomes by request segment (cold start, page, views)
        "segments": f"""
SELECT dim, val, sb, count() AS requests, countIf(clk != '') AS clicks, countIf(pur != '') AS purchases, round(sum(rev), 2) AS revenue
FROM (
  SELECT r.page, r.device, r.nu, r.cold, r.nviews, f.sb, f.clk, f.pur, f.rev
  FROM (SELECT request_id::String AS rid, context.page::String AS page, context.device::String AS device, is_new_user::Bool AS nu,
               {RV}.product_id AS rv, length(rv) AS nviews, nu OR hasAny(rv, {NEWP}) AS cold {req}) AS r
  INNER JOIN ({FB}) AS f ON f.rid = r.rid
) ARRAY JOIN ['page', 'device', 'new_user', 'cold', 'n_views', 'page_x_new_user'] AS dim,
             [page, device, toString(nu), toString(cold), multiIf(nviews = 0, '0', nviews = 1, '1', nviews <= 3, '2-3', '4+'), concat(page, '|new=', toString(nu))] AS val
GROUP BY dim, val, sb ORDER BY dim, val, sb SETTINGS max_execution_time = 28""",
        # arm attribution per hour (submission items == shown list)
        "model_hourly": f"""
SELECT toUnixTimestamp(toStartOfHour(f.fts)) AS t,
       if(f.sb != 'team', concat('(', f.sb, ':', f.fr, ')'), if(s.mv = '', '(unmatched)', s.mv)) AS model_version,
       count() AS requests, countIf(f.clk != '') AS clicks, countIf(f.pur != '') AS purchases, round(sum(f.rev), 2) AS revenue
FROM ({FB}) AS f
LEFT JOIN (SELECT request_id::String AS rid, items::Array(String) AS sent_items,
                  if(uniqExact(model_version::String) = 1, any(model_version::String), '(ambiguous)') AS mv
           FROM team_37.submissions GROUP BY rid, sent_items) AS s ON s.rid = f.rid AND s.sent_items = f.shown_items
WHERE f.fts >= '{t0}' AND f.fts < '{t1}'
GROUP BY t, model_version ORDER BY t, requests DESC SETTINGS max_execution_time = 28""",
        # multi-writer contamination per hour
        "writers_hourly": f"""
SELECT toUnixTimestamp(toStartOfHour(r.ts)) AS t, count() AS requests,
       countIf(s.n = 0) AS no_submission, countIf(s.n = 1) AS one_submission, countIf(s.n > 1) AS multi_submission,
       countIf(s.nv > 1) AS multi_version
FROM (SELECT request_id::String AS rid, ts::DateTime64(3) AS ts {req}) AS r
LEFT JOIN (SELECT request_id::String AS rid, count() AS n, uniqExact(model_version::String) AS nv FROM team_37.submissions GROUP BY rid) AS s ON s.rid = r.rid
GROUP BY t ORDER BY t SETTINGS max_execution_time = 28""",
        # organic stream per hour x category (promotions and trends the system must learn from)
        "events_category_hourly": f"""
SELECT toUnixTimestamp(toStartOfHour(e.ts)) AS t, c.cat AS category,
       countIf(e.et = 'view') AS views, countIf(e.et = 'add_to_cart') AS carts, countIf(e.et = 'purchase') AS purchases
FROM (SELECT ts::DateTime64(3) AS ts, product_id::String AS pid, event_type::String AS et FROM shop.events
      WHERE ts::DateTime64(3) >= '{t0}' AND ts::DateTime64(3) < '{t1}') AS e
INNER JOIN (SELECT product_id::String AS pid, category::String AS cat FROM shop.catalog) AS c ON c.pid = e.pid
GROUP BY t, category ORDER BY t, category SETTINGS max_execution_time = 28""",
        "price_changes_hourly": f"""
SELECT toUnixTimestamp(toStartOfHour(u.ts)) AS t, u.cat AS category, count() AS price_changes,
       round(avg(u.price / c.price - 1) * 100, 2) AS avg_pct_vs_catalog
FROM (SELECT product_id::String AS pid, ts::DateTime64(3) AS ts, price_eur::Float64 AS price, category::String AS cat
      FROM shop.catalog_updates WHERE change::String = 'price_change' AND ts::DateTime64(3) >= '{t0}' AND ts::DateTime64(3) < '{t1}') AS u
INNER JOIN (SELECT product_id::String AS pid, price_eur::Float64 AS price FROM shop.catalog) AS c ON c.pid = u.pid
GROUP BY t, category ORDER BY t, category SETTINGS max_execution_time = 25""",
    }


STATIC = {
    # old carousel (60 days before the event): clicks/purchases by clicked slot; 2M impressions per slot
    "history_slots": """
SELECT indexOf(shown::Array(String), clicked::String) AS slot, count() AS rows_, countIf(purchased::String != '') AS purchases
FROM shop.history_sessions GROUP BY slot ORDER BY slot SETTINGS max_execution_time = 28""",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=list(PERIODS), default="practice")
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    t0, t1 = PERIODS[args.period]
    now = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=30)
    t1 = min(t1, now.strftime("%Y-%m-%d %H:%M:%S"))
    out = OUT / args.period
    out.mkdir(parents=True, exist_ok=True)
    db = DB()
    qs = queries(t0, t1)
    if args.period == "practice":
        qs.update(STATIC)
    meta = {"period": args.period, "t0_utc": t0, "t1_utc": t1, "extracted_at_utc": now.strftime("%Y-%m-%d %H:%M:%S")}
    for name, sql in qs.items():
        if args.only and name not in args.only:
            continue
        t = time.time()
        try:
            rows = db.query(sql)
            err = None
        except Exception as e:  # keep going; a failed query is reported, never silently replaced
            rows, err = [], str(e)[:500]
        secs = round(time.time() - t, 1)
        (out / f"{name}.json").write_text(json.dumps({"meta": meta, "sql": sql, "err": err, "secs": secs, "rows": rows}, default=str))
        print(f"{name:24s} {secs:5.1f}s rows={len(rows)}" + (f" ERR {err[:200]}" if err else ""))
        time.sleep(0.3)
    (out / "_meta.json").write_text(json.dumps(meta))


if __name__ == "__main__":
    main()
