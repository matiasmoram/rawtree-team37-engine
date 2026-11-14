"""Build small serving signal artifacts in a separate process; never submit lists.

python scripts/refresh_signals.py --once
python scripts/refresh_signals.py --once --as-of 2026-11-14T14:00:00 --out cache/recent_covis_1400.json
python scripts/refresh_signals.py --every 600
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import CACHE
from engine.content import ContentIndex
from engine.recent_covis import build_recent_covis, save_recent_covis
from engine.rt import RawTree


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--as-of", help="UTC information cutoff, historical replay requires a matching artifact")
    ap.add_argument("--every", type=float, default=600)
    ap.add_argument("--window-hours", type=float, default=6)
    ap.add_argument("--half-life-hours", type=float, default=6)
    ap.add_argument("--out", type=Path, default=CACHE / "recent_covis.json")
    args = ap.parse_args()
    if args.every < 60:
        ap.error("--every must be >= 60 seconds")
    if args.as_of and not args.once:
        ap.error("historical --as-of requires --once")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    while True:
        t0 = time.monotonic()
        try:
            cutoff = (datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of
                      else datetime.now(timezone.utc) - timedelta(seconds=10))
            if cutoff.tzinfo is None:
                cutoff = cutoff.replace(tzinfo=timezone.utc)
            if cutoff > datetime.now(timezone.utc):
                raise ValueError("as-of must not be in the future")
            payload = build_recent_covis(RawTree(timeout=100), cutoff, args.window_hours, args.half_life_hours)
            path = save_recent_covis(payload, args.out)
            index = ContentIndex.load()
            logging.info("saved %s cutoff=%s vv_sources=%d vb_sources=%d content_new=%d seconds=%.2f",
                         path.name, cutoff.isoformat(), len(payload["vv"]), len(payload["vb"]),
                         len(index.forward), time.monotonic() - t0)
        except Exception:
            logging.exception("signal refresh failed; previous atomic artifact is retained")
            if args.once:
                raise
        if args.once:
            return
        time.sleep(max(1.0, args.every - (time.monotonic() - t0)))


if __name__ == "__main__":
    main()
