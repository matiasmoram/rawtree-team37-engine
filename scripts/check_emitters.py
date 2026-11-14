"""Read-only audit of competing submissions and actual shown-list attribution.

python scripts/check_emitters.py --minutes 5,15
Windows end ten seconds before server now so requests have time to receive feedback.
No keys, user IDs, request IDs or full item lists are written to the report.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.config import LOGS, TEAM
from engine.rt import RawTree
from engine.types import parse_ts, sql_ts


def audit_window(rt, start, end, team: str = TEAM) -> dict:
    if not re.fullmatch(r"team_\d+", team):
        raise ValueError("unexpected team identifier")
    if not start < end or (end - start).total_seconds() > 10800:
        raise ValueError("audit window must be positive and at most three hours")
    lo, hi = sql_ts(start), sql_ts(end)
    recent = ("SELECT request_id::String AS rid FROM shop.requests "
              f"WHERE ts::DateTime64(3) >= '{lo}' AND ts::DateTime64(3) < '{hi}'")
    submissions = (f"SELECT request_id::String AS rid, count() AS n, uniqExact(model_version::String) AS nv "
                   f"FROM {team}.submissions WHERE request_id::String IN ({recent}) GROUP BY rid")
    counts = rt.query(f"""
        SELECT count() AS requests, countIf(s.n > 0) AS requests_with_submission,
               countIf(s.n = 0) AS missing_submissions, countIf(s.n > 1) AS duplicated_requests,
               countIf(s.nv > 1) AS multi_model_requests, max(s.n) AS max_submissions,
               sum(s.n) AS total_submissions
        FROM ({recent}) AS r LEFT JOIN ({submissions}) AS s ON s.rid = r.rid
        SETTINGS max_execution_time = 25""", timeout=30, retries=0)[0]
    versions = rt.query(f"""
        SELECT model_version::String AS model, count() AS submissions, uniqExact(request_id::String) AS requests
        FROM {team}.submissions WHERE request_id::String IN ({recent}) GROUP BY model ORDER BY submissions DESC
        SETTINGS max_execution_time = 25""", timeout=30, retries=0)
    attribution = rt.query(f"""
        SELECT if(f.sb != 'team', '(fallback)', if(s.nv = 0, '(unmatched)',
               if(s.nv > 1, '(ambiguous)', s.mv))) AS attributed_model,
               count() AS feedback_requests, countIf(f.sb = 'team') AS served_team,
               countIf(f.reason = 'late') AS late, countIf(f.reason = 'invalid') AS invalid,
               countIf(f.reason = 'missing') AS missing,
               countIf(f.purchased_item != '') AS purchases,
               quantile(0.95)(f.lat) AS p95_ms
        FROM (SELECT request_id::String AS rid, served_by::String AS sb,
                     shown::Array(String) AS shown_items, fallback_reason::String AS reason,
                     ifNull(purchased::Nullable(String), '') AS purchased_item, latency_ms::Float64 AS lat
              FROM {team}.feedback WHERE request_id::String IN ({recent})) AS f
        LEFT JOIN (SELECT request_id::String AS rid, items::Array(String) AS sent_items,
                          uniqExact(model_version::String) AS nv, any(model_version::String) AS mv
                   FROM {team}.submissions WHERE request_id::String IN ({recent}) GROUP BY rid, sent_items) AS s
             ON s.rid = f.rid AND s.sent_items = f.shown_items
        GROUP BY attributed_model ORDER BY feedback_requests DESC
        SETTINGS max_execution_time = 25""", timeout=30, retries=0)
    n = int(counts.get("requests", 0))
    return {"from": start.isoformat(), "to": end.isoformat(), "counts": counts,
            "multi_model_request_share": int(counts.get("multi_model_requests", 0)) / n if n else None,
            "versions": versions, "feedback_attribution": attribution,
            "feedback_coverage": sum(int(r["feedback_requests"]) for r in attribution) / n if n else None,
            "warning": "Version counts do not identify machines. Overlap is not proof of a latency cause."}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", default="5,15", help="comma-separated bounded windows, up to 180 minutes")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    minutes = [int(x) for x in args.minutes.split(",")]
    if any(not 0 < m <= 180 for m in minutes):
        ap.error("window minutes must be in 1..180")
    rt = RawTree(timeout=30)
    end = parse_ts(rt.query("SELECT toString(now64(3)) AS ts", retries=0)[0]["ts"]) - timedelta(seconds=10)
    report = {"team": TEAM, "source": "live_rawtree_read_only", "as_of": end.isoformat(),
              "windows": {str(m): audit_window(rt, end - timedelta(minutes=m), end) for m in minutes}}
    out = Path(args.out) if args.out else LOGS / f"emitters_audit_{end:%Y%m%dT%H%M%S}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(report, indent=2, allow_nan=False))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
