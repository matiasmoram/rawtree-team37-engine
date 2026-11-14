"""Refresh bounded context priors/trends outside serving. Never submit recommendations.

python scripts/refresh_context.py --once
python scripts/refresh_context.py --every 600
python scripts/refresh_context.py --once --as-of 2026-11-14T15:00:00Z --out cache/context_1500.json
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.contextual import build_contextual, save_contextual
from engine.rt import RawTree
from engine.types import parse_ts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--as-of")
    ap.add_argument("--every", type=float, default=600)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.every < 120 or (args.as_of and not args.once):
        ap.error("--every must be >=120; historical --as-of requires --once")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    while True:
        t0 = time.monotonic()
        try:
            rt = RawTree(timeout=70)
            server_now = parse_ts(rt.query("SELECT toString(now64(3)) AS ts", retries=0)[0]["ts"])
            cutoff = parse_ts(args.as_of) if args.as_of else server_now - timedelta(seconds=10)
            if cutoff > server_now:
                raise ValueError("as-of must not be in the future")
            payload = build_contextual(rt, cutoff)
            path = save_contextual(payload, args.out)
            logging.info("saved %s cutoff=%s context_groups=%s subcategories=%d brands=%d seconds=%.2f",
                         path.name, cutoff.isoformat(), {k: len(v) for k, v in payload["tables"].items()},
                         len(payload["subcategory_lift"]), len(payload["brand_lift"]), time.monotonic() - t0)
        except Exception:
            logging.exception("context refresh failed; previous atomic artifact retained")
            if args.once:
                raise
        if args.once:
            return
        time.sleep(max(1., args.every - (time.monotonic() - t0)))


if __name__ == "__main__":
    main()
