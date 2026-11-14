"""Run the offline evaluators on registered policies.

Examples (from the project root):
  .venv/Scripts/python.exe scripts/run_eval.py --T 2026-11-07T07:00:00 --window-hours 168 --evals logged
  .venv/Scripts/python.exe scripts/run_eval.py --T 2026-11-14T10:00:00 --window-hours 3 --evals organic,live

Builds (or loads from cache/) the snapshot at T, runs the evaluators on data in [T, T + window), prints a table per
evaluator and metric, and appends every result row to logs/eval_results.jsonl.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import LOGS  # noqa: E402
from engine.eval import LiveRequestEval, LoggedImpressionEval, OrganicNextPurchaseEval, make_policies  # noqa: E402
from engine.eval.registry import POLICIES  # noqa: E402
from engine.eval.report import append_jsonl, format_report  # noqa: E402
from engine.rt import RawTree  # noqa: E402
from engine.snapshot import build_snapshot  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--T", required=True, help="cutoff, UTC, e.g. 2026-11-14T10:00:00")
    ap.add_argument("--window-hours", type=float, default=3.0)
    ap.add_argument("--evals", default="logged,organic,live", help="comma list of logged, organic, live")
    ap.add_argument("--policies", default=",".join(POLICIES), help=f"comma list from {sorted(POLICIES)}")
    ap.add_argument("--bootstrap", type=int, default=500, help="bootstrap replicates (0 = no CI)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-cache", action="store_true", help="re-pull evaluation sets (snapshot cache is still used)")
    ap.add_argument("--max-clicked", type=int, default=20000, help="logged: cap on impressions with a click")
    ap.add_argument("--nonclick-sample", type=int, default=30000, help="logged: sampled impressions without click")
    ap.add_argument("--max-weight", type=float, default=None, help="logged: clip SNIPS weights 1/propensity")
    ap.add_argument("--max-sessions", type=int, default=20000, help="organic: cap on purchasing sessions")
    ap.add_argument("--horizon-minutes", type=float, default=30.0, help="live: label horizon after the request")
    ap.add_argument("--out", default=str(LOGS / "eval_results.jsonl"))
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    T = datetime.fromisoformat(args.T).replace(tzinfo=timezone.utc)
    policies = make_policies([p.strip() for p in args.policies.split(",") if p.strip()])
    common = {"window_hours": args.window_hours, "n_boot": args.bootstrap, "seed": args.seed}
    factories = {
        "logged": lambda: LoggedImpressionEval(max_clicked=args.max_clicked, nonclick_sample=args.nonclick_sample,
                                               max_weight=args.max_weight, **common),
        "organic": lambda: OrganicNextPurchaseEval(max_sessions=args.max_sessions, **common),
        "live": lambda: LiveRequestEval(horizon_minutes=args.horizon_minutes, **common),
    }
    names = [e.strip() for e in args.evals.split(",") if e.strip()]
    bad = [e for e in names if e not in factories]
    if bad:
        ap.error(f"unknown evals {bad}; choose from {sorted(factories)}")

    rt = RawTree(timeout=300)
    t0 = time.time()
    snap = build_snapshot(rt, T, cache=True)
    print(f"snapshot T={snap.T} ready in {time.time() - t0:.1f}s; policies: {[p.name for p in policies]}")

    reports = []
    for name in names:
        rep = factories[name]().run(rt, snap, policies, use_cache=not args.no_cache)
        reports.append(rep)
        print(format_report(rep), flush=True)
    n = append_jsonl(Path(args.out), reports, T, args.window_hours)
    print(f"\nrun times: " + ", ".join(f"{r.evaluator} load {r.secs['load']}s + score {r.secs['score']}s" for r in reports))
    print(f"appended {n} rows to {args.out}")


if __name__ == "__main__":
    main()
