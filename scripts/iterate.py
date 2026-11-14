"""One-command iteration cycle: champion vs challenger(s) on recent real feedback.

python scripts/iterate.py --champion ev-v3 --challengers ev-content,ev-recent-covis,cf-v1 \
    --since 2026-11-14T15:00:00 --until 2026-11-14T15:23:00

Replays a fixed feedback window point-in-time with the champion as control,
attaches point-in-time user carts (cart-first arms need them offline), checks
per-arm artifacts before running, and prints a decision table with paired
user-clustered bootstrap intervals on the observed-list rerank.

Read-only: never submits recommendations or changes live arms. Verdicts are
offline diagnostics on observed labels; they do not estimate the simulator's
expected conversion. A CANDIDATE verdict only justifies a bounded live trial,
never a direct promotion.
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

from engine.cartstate import attach_user_carts
from engine.config import CACHE, LOGS, TEAM
from engine.eval.replay import evaluate_replay, name_has_rerank
from engine.learn.dataset import UPDATES_SQL, load_feedback, load_recent_buys
from engine.policies.registry import get_policy
from engine.rt import RawTree
from engine.snapshot import build_snapshot
from engine.types import parse_ts, sql_ts

TINY_N = 30  # below this many reranked purchases, intervals cannot clear a trial gate


def load_policies(champion: str, challengers: list[str]):
    """Instantiate champion first (it becomes the replay control) plus challengers."""
    names = [champion] + challengers
    if len(set(names)) != len(names):
        raise SystemExit("champion must not appear in challengers")
    policies, skipped = [], []
    for name in names:
        try:
            policies.append(get_policy(name))
        except Exception as exc:  # missing model file, malformed artifact, unknown name
            skipped.append({"policy": name, "reason": f"{type(exc).__name__}: {exc}"})
    if not policies:
        raise SystemExit("no policy could be instantiated")
    if all(p.name != champion for p in policies):
        reasons = "; ".join(f"{s['policy']}: {s['reason']}" for s in skipped if s["policy"] == champion)
        raise SystemExit(f"champion {champion} failed to instantiate; no control, aborting. {reasons}")
    policies.sort(key=lambda p: p.name != champion)
    return policies, skipped


def artifact_warnings(policies: list) -> list[str]:
    """Warn about silently degraded arms (empty index artifacts load without error)."""
    warns = []
    for p in policies:
        index = getattr(p, "index", None)
        forward = getattr(index, "forward", None)
        if index is not None and forward is not None and not forward:
            warns.append(f"{p.name}: index artifact loaded EMPTY; this arm is degraded offline")
    return warns


def load_window(rt: RawTree, since, until, snap, no_cache: bool) -> dict:
    cache = CACHE / f"policy_replay_v1_{snap.T:%Y%m%dT%H%M%S}_{since:%Y%m%dT%H%M%S}_{until:%Y%m%dT%H%M%S}.pkl"
    if cache.exists() and not no_cache:
        with cache.open("rb") as f:
            return pickle.load(f)
    logging.info("querying mature real feedback and point-in-time changes")
    data = {"rows": load_feedback(rt, since, until), "buys": load_recent_buys(rt, since, until),
            "updates": rt.query(UPDATES_SQL.format(lo=sql_ts(snap.T), hi=sql_ts(until)), timeout=120)}
    window = f"ts::DateTime64(3) >= '{sql_ts(since)}' AND ts::DateTime64(3) < '{sql_ts(until)}'"
    data["request_audit"] = rt.query(f"SELECT count() AS rows, uniqExact(request_id::String) AS requests "
                                     f"FROM shop.requests WHERE {window}")[0]
    data["feedback_audit"] = rt.query(f"SELECT count() AS rows, uniqExact(request_id::String) AS requests FROM {TEAM}.feedback "
                                      f"WHERE request_id::String IN (SELECT request_id::String FROM shop.requests WHERE {window})")[0]
    if data["feedback_audit"]["rows"] != data["feedback_audit"]["requests"]:
        raise SystemExit("duplicate feedback rows; resolve before evaluation")
    with cache.open("wb") as f:
        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    return data


def verdict_for(model: dict, champion: str, rerank_supported: bool, deadline_ms: float) -> str:
    if model["invalid_lists"] > 0:
        return "EXECUTION FAIL (invalid lists)"
    if model["latency_ms_p95"] is not None and model["latency_ms_p95"] > deadline_ms:
        return f"EXECUTION FAIL (latency p95 {model['latency_ms_p95']:.0f}ms > {deadline_ms:.0f}ms)"
    paired = model.get(f"paired_purchase_ndcg_vs_{champion}")
    if paired and paired.get("mean") is not None and paired["ci95"][0] is not None:
        lo, hi = paired["ci95"]
        n = paired["requests"]
        if lo > 0:
            base = "CANDIDATE (paired purchase NDCG above champion)"
        elif hi < 0:
            base = "NO-GO (paired purchase NDCG below champion)"
        else:
            base = "INSUFFICIENT EVIDENCE (CI includes 0)"
        if n < TINY_N:
            base += f"; tiny-n ({n} reranked purchases) -> diagnostic only"
        return base
    if not rerank_supported:
        return "DIAGNOSTIC ONLY (no rerank hook): judge via support/latency + evaluate_recent gate"
    return "INSUFFICIENT EVIDENCE (no paired interval available)"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--champion", required=True, help="registry name of the current champion (replay control)")
    parser.add_argument("--challengers", required=True, help="comma-separated registry names to test")
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--snapshot", type=Path, help="cached snapshot pickle; built at --since when omitted")
    parser.add_argument("--max-requests", type=int, default=6000)
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument("--deadline-ms", type=float, default=3000.0)
    parser.add_argument("--skip-carts", action="store_true", help="do not attach point-in-time user carts")
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

    snap = build_snapshot(rt, since, cache=True) if not args.snapshot else pickle.loads(args.snapshot.read_bytes())
    if snap.T > since:
        parser.error("snapshot cutoff must be <= start of evaluation")
    cart_arms = []
    if not args.skip_carts:
        attach_user_carts(rt, snap)
    else:
        logging.warning("carts not attached: any cart-dependent arm will run crippled")

    policies, skipped = load_policies(args.champion, [n.strip() for n in args.challengers.split(",") if n.strip()])
    for p in policies:
        if p.name.startswith("cf") and args.skip_carts:
            logging.warning("%s is cart-dependent but carts were not attached", p.name)
        cart_arms.append(p.name)
    warns = artifact_warnings(policies)
    if skipped:
        logging.warning("skipped arms: %s", json.dumps(skipped))

    data = load_window(rt, since, until, snap, args.no_cache)
    logging.info("replaying %d available requests with policies=%s; fixed snapshot=%s",
                 len(data["rows"]), [p.name for p in policies], snap.T)
    report = evaluate_replay(data["rows"], snap, policies, updates=data["updates"], recent_buys=data["buys"],
                             limit=args.max_requests, n_boot=args.bootstrap)
    report["coverage_audit"] = {"requests": data["request_audit"], "feedback": data["feedback_audit"],
                                "feedback_fraction": data["feedback_audit"]["requests"] / max(1, data["request_audit"]["requests"])}
    report["fixed_query_interval"] = {"since": since.isoformat(), "until": until.isoformat(),
                                      "server_now": server_now.isoformat()}

    champion = args.champion
    unsupported = set(report.get("rerank_unsupported_policies", []))
    verdicts = {}
    for seg in ("all", "cold_request"):
        seg_models = report["segments"][seg]["models"]
        if seg == "cold_request" and report["segments"][seg]["requests"] == 0:
            continue
        verdicts[seg] = {name: verdict_for(seg_models[name], champion, name not in unsupported, args.deadline_ms)
                         for name in seg_models if name != "logged_order"}

    out = {"iteration": {"champion": champion, "challengers": [p.name for p in policies if p.name != champion],
                         "deadline_ms": args.deadline_ms, "carts_attached": not args.skip_carts,
                         "skipped_arms": skipped, "artifact_warnings": warns},
           "verdicts": verdicts, "replay_report": report}
    path = args.out or LOGS / f"iteration_{until:%Y%m%dT%H%M}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, allow_nan=False), encoding="utf-8")

    for w in warns:
        print(f"WARNING: {w}")
    for seg, table in verdicts.items():
        models = report["segments"][seg]["models"]
        print(f"\n== {seg} ({report['segments'][seg]['requests']} requests) ==")
        print(f"{'policy':<18} {'reqs':>5} {'inval':>5} {'p95ms':>7} {'overlap':>7} "
              f"{'pairedNDCG[ci95]':>26} {'n':>4}  verdict")
        for name, m in models.items():
            if name == "logged_order":
                continue
            paired = m.get(f"paired_purchase_ndcg_vs_{champion}")
            cell = "-"
            if paired and paired.get("mean") is not None:
                lo, hi = paired["ci95"]
                cell = f"{paired['mean']:+.4f} [{lo:+.3f},{hi:+.3f}]"
            n = paired["requests"] if paired else 0
            print(f"{name:<18} {m['requests']:>5} {m['invalid_lists']:>5} {m['latency_ms_p95']:>7.0f} "
                  f"{m['top10_overlap_control']:>7.2f} {cell:>26} {n:>4}  {verdicts[seg][name]}")
    print(json.dumps({"verdicts": verdicts["all"], "report": str(path)}, indent=2), flush=True)


if __name__ == "__main__":
    main()
