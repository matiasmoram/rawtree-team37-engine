"""Compare fixed policies on actual recent feedback using a past snapshot.

python scripts/evaluate_policies.py --since 2026-11-14T15:00:00 --until 2026-11-14T15:23:00 --snapshot cache/snapshot_20261114T134500.pkl

This script reads RawTree; it never submits recommendations or changes live arms.
All times are UTC. Quality outputs are observed-label proxies, not simulator CVR.
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import CACHE, LOGS, TEAM
from engine.eval.replay import evaluate_replay, focused_session_policy
from engine.learn.dataset import UPDATES_SQL, load_feedback, load_recent_buys
from engine.policies.registry import get_policy
from engine.rt import RawTree
from engine.snapshot import build_snapshot
from engine.types import parse_ts, sql_ts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--policies", default="ev-v2-nocovis,ev-v3,ev-content,ev-v4-session")
    parser.add_argument("--max-requests", type=int, default=6000)
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    rt = RawTree(timeout=180)
    server_now = parse_ts(rt.query("SELECT toString(now64(3)) AS n")[0]["n"])
    since, until = parse_ts(args.since), parse_ts(args.until)
    if not since < until <= server_now - timedelta(minutes=2):
        parser.error("need since < until <= server-now minus two minutes")
    if args.max_requests < 1 or args.bootstrap < 0:
        parser.error("max-requests > 0 and bootstrap >= 0 required")
    if args.snapshot:
        with args.snapshot.open("rb") as f:
            snap = pickle.load(f)
    else:
        snap = build_snapshot(rt, since, cache=True)
    if snap.T > since:
        parser.error("snapshot cutoff must be <= start of evaluation")
    cache = CACHE / f"policy_replay_v1_{snap.T:%Y%m%dT%H%M%S}_{since:%Y%m%dT%H%M%S}_{until:%Y%m%dT%H%M%S}.pkl"
    if cache.exists() and not args.no_cache:
        with cache.open("rb") as f:
            data = pickle.load(f)
    else:
        logging.info("querying mature real feedback and point-in-time changes")
        data = {"rows": load_feedback(rt, since, until), "buys": load_recent_buys(rt, since, until),
                "updates": rt.query(UPDATES_SQL.format(lo=sql_ts(snap.T), hi=sql_ts(until)), timeout=120)}
        window = f"ts::DateTime64(3) >= '{sql_ts(since)}' AND ts::DateTime64(3) < '{sql_ts(until)}'"
        data["request_audit"] = rt.query(f"SELECT count() AS rows, uniqExact(request_id::String) AS requests FROM shop.requests WHERE {window}")[0]
        data["feedback_audit"] = rt.query(f"SELECT count() AS rows, uniqExact(request_id::String) AS requests FROM {TEAM}.feedback "
                                          f"WHERE request_id::String IN (SELECT request_id::String FROM shop.requests WHERE {window})")[0]
        if data["feedback_audit"]["rows"] != data["feedback_audit"]["requests"]:
            raise ValueError("duplicate feedback rows; resolve before caching/evaluation")
        with cache.open("wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    names = [name.strip() for name in args.policies.split(",") if name.strip()]
    policies = [focused_session_policy() if name == "ev-v4-session" else get_policy(name) for name in names]
    logging.info("replaying %d available requests with policies=%s; fixed snapshot=%s", len(data["rows"]), names, snap.T)
    report = evaluate_replay(data["rows"], snap, policies, updates=data["updates"], recent_buys=data["buys"],
                             limit=args.max_requests, n_boot=args.bootstrap)
    report["coverage_audit"] = {"requests": data["request_audit"], "feedback": data["feedback_audit"],
                                "feedback_fraction": data["feedback_audit"]["requests"] / max(1, data["request_audit"]["requests"])}
    report["fixed_query_interval"] = {"since": since.isoformat(), "until": until.isoformat(), "server_now": server_now.isoformat()}
    path = args.out or LOGS / f"policy_replay_{until:%Y%m%dT%H%M}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"requests": report["requests_evaluated"], "snapshot": report["snapshot_cutoff"],
                      "unsupported_lists": report["unsupported_observed_lists"], "all": report["segments"]["all"],
                      "report": str(path)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
