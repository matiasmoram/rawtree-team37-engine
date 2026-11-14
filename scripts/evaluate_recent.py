"""Train and evaluate on recent real feedback without exposing test to model selection.

All timestamps are UTC; defaults use server time minus 2 minutes for feedback maturity.
This script never submits recommendations or changes live traffic.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import CACHE, LOGS, TEAM
from engine.learn.dataset import build_dataset
from engine.learn.recent import benchmark_serving, evaluate_and_train
from engine.rt import RawTree
from engine.types import parse_ts, sql_ts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", help="UTC interval start; defaults to --hours before until")
    parser.add_argument("--until", help="UTC exclusive end, must be mature")
    parser.add_argument("--hours", type=float, default=2.)
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--model-out")
    parser.add_argument("--benchmark-only", help="read-only prospective latency/validity check for this model path")
    parser.add_argument("--benchmark-requests", type=int, default=100)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.benchmark_only:
        result = benchmark_serving(args.benchmark_only, n_requests=args.benchmark_requests)
        path = LOGS / "recent_serving_benchmark.json"
        path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps(result, indent=2), flush=True)
        return
    rt = RawTree(timeout=180)
    now = parse_ts(rt.query("SELECT toString(now64(3)) AS n")[0]["n"])
    mature = now - timedelta(minutes=2)
    until = parse_ts(args.until) if args.until else mature.replace(second=0, microsecond=0)
    since = parse_ts(args.since) if args.since else until - timedelta(hours=args.hours)
    if not since < until <= mature:
        parser.error("need since < until <= server-now minus 2 minutes")
    print(f"Fixed UTC range {since} -> {until}; server={now}", flush=True)
    window = f"ts::DateTime64(3) >= '{sql_ts(since)}' AND ts::DateTime64(3) < '{sql_ts(until)}'"
    request_audit = rt.query(f"SELECT count() AS rows, uniqExact(request_id::String) AS requests FROM shop.requests WHERE {window}")[0]
    feedback_audit = rt.query(f"SELECT count() AS rows, uniqExact(request_id::String) AS requests, "
                             f"countIf(served_by::String='team') AS served_team FROM {TEAM}.feedback "
                             f"WHERE request_id::String IN (SELECT request_id::String FROM shop.requests WHERE {window})")[0]
    if feedback_audit["rows"] != feedback_audit["requests"]:
        raise ValueError("duplicate feedback rows; resolve deduplication before training")
    df, meta = build_dataset(rt, since, until, cache=not args.no_cache)
    meta["coverage_audit"] = {"requests": request_audit, "feedback": feedback_audit,
                              "feedback_coverage": feedback_audit["requests"] / max(1, request_audit["requests"])}
    model_path = Path(args.model_out) if args.model_out else CACHE / f"lgbm_recent_{until:%Y%m%dT%H%M}.txt"
    report_path = LOGS / f"recent_evaluation_{until:%Y%m%dT%H%M}.json"
    report = evaluate_and_train(df, meta, model_path, report_path, n_boot=args.bootstrap)
    print(json.dumps({"partitions": report["partitions"], "selection": report["selection"]["kind"],
                      "test_all": report["test_segments"]["all"], "ranking": report["test_ranking"],
                      "purchase_delta": report["paired_user_bootstrap"]["purchase_ndcg_vs_logged_order"],
                      "online_trial_eligible": report["online_trial_eligible"],
                      "model": str(model_path), "report": str(report_path)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
