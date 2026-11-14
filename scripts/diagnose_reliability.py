"""Read-only breakdown of RawTree serving gaps and competing submitters.

Usage:
  python scripts/diagnose_reliability.py --minutes 20
  python scripts/diagnose_reliability.py --minutes 20 --duplicates

Never writes submissions or changes the live runner.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import TEAM
from engine.rt import RawTree


def _num(value: object) -> int:
    return int(value or 0)


def minute_report(rt: RawTree, minutes: int) -> None:
    sql = f"""
    SELECT toStartOfMinute(ts::DateTime64(3)) AS minute,
           count() AS n,
           countIf(served_by::String = 'team') AS accepted,
           countIf(fallback_reason::String = 'missing') AS missing,
           countIf(fallback_reason::String = 'late') AS late,
           countIf(fallback_reason::String = 'invalid') AS invalid,
           quantileIf(0.95)(latency_ms::Float64, served_by::String = 'team') AS p95_ms
    FROM {TEAM}.feedback
    WHERE request_id::String != '__init__'
      AND ts::DateTime64(3) > now() - INTERVAL {minutes} MINUTE
    GROUP BY minute ORDER BY minute
    """
    print(f"Feedback, last {minutes} min (times UTC; includes partial minutes):")
    print(f"{'minute':20s} {'all':>5s} {'team':>5s} {'miss':>5s} {'late':>5s} {'inv':>4s} {'ok%':>7s} {'p95ms':>8s}")
    total = ok = miss = late = invalid = 0
    for row in rt.query(sql, timeout=35):
        n = _num(row.get('n'))
        good = _num(row.get('accepted'))
        m = _num(row.get('missing'))
        l = _num(row.get('late'))
        inv = _num(row.get('invalid'))
        total += n
        ok += good
        miss += m
        late += l
        invalid += inv
        print(f"{str(row['minute']):20s} {n:5d} {good:5d} {m:5d} {l:5d} {inv:4d} {100*good/max(n,1):6.1f}% {float(row.get('p95_ms') or 0):8.0f}")
    print(f"TOTAL n={total} team={ok} ({100*ok/max(total,1):.1f}%) missing={miss} late={late} invalid={invalid}")
    if total and miss / total > .02:
        print("WARNING: More than 2% missing. Correlate the affected UTC minutes with logs/live.log.")
    print("A stable low on-time rate after startup is NOT attributable to old misses.")


def duplicate_report(rt: RawTree, minutes: int) -> None:
    # Filter by recent request ids, not an assumed submission timestamp: the submissions table
    # does not promise to contain a timestamp.
    sql = f"""
    SELECT rid, count() AS writes, uniqExact(mv) AS distinct_versions,
           groupUniqArray(mv) AS versions
    FROM (
      SELECT request_id::String AS rid, model_version::String AS mv
      FROM {TEAM}.submissions
      WHERE request_id::String IN (
        SELECT request_id::String FROM shop.requests
        WHERE ts::DateTime64(3) > now() - INTERVAL {minutes} MINUTE
      )
    )
    GROUP BY rid HAVING count() > 1
    ORDER BY writes DESC LIMIT 20
    """
    print("\nRecent requests with multiple submissions (sample of max 20):")
    rows = rt.query(sql, timeout=60)
    if not rows:
        print("None found in sample.")
        return
    for row in rows:
        print(f"  {row['rid']}: {row['writes']} writes, {row['distinct_versions']} versions: {row['versions']}")
    print("Multiple senders can corrupt attribution and overwrite experiments. Coordinate one writer.")
    print("Identical versions do not prove there is only one process.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--minutes", type=int, default=20)
    ap.add_argument("--duplicates", action="store_true", help="expensive extra read-only duplicate query")
    args = ap.parse_args()
    if not 1 <= args.minutes <= 180:
        ap.error("--minutes must be between 1 and 180")
    rt = RawTree(timeout=40)
    minute_report(rt, args.minutes)
    if args.duplicates:
        duplicate_report(rt, min(args.minutes, 30))


if __name__ == "__main__":
    main()
