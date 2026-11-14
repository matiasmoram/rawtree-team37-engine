"""Train the live-feedback LightGBM ranker.

    python scripts/train_live_ranker.py --since "2026-11-14 12:10:00"
    python scripts/train_live_ranker.py --since "2026-11-14 12:10:00" --until "2026-11-14 14:15:00" --out cache/lgbm_live_x.txt

Builds (or loads from cache/) the snapshot at T0 = --since and the feedback training table for [since, until),
trains click / purchase / factored LightGBM models with a time-based split, prints the validation report and saves
the serving model (--out), the component models and a JSON sidecar with metrics and the feature list.
All times are UTC. --until defaults to now minus 2 minutes (feedback lands ~4 s after each request).
"""
import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, ".")
from engine.config import CACHE  # noqa: E402
from engine.learn.dataset import build_dataset  # noqa: E402
from engine.learn.train import run  # noqa: E402
from engine.rt import RawTree  # noqa: E402
from engine.snapshot import build_snapshot  # noqa: E402


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("T", " ")).replace(tzinfo=timezone.utc)


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--since", required=True, help="UTC start of the training range (= snapshot T0)")
ap.add_argument("--until", default=None, help="UTC end of the range (exclusive); default now - 2 min")
ap.add_argument("--out", default=None, help="serving model path; default cache/lgbm_live_<until stamp>.txt")
ap.add_argument("--valid-frac", type=float, default=0.25, help="last share of requests (by ts) used for validation")
ap.add_argument("--no-cache", action="store_true", help="rebuild the training table even if cached")
args = ap.parse_args()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logging.getLogger("learn.train").setLevel(logging.WARNING)
since = utc(args.since)
until = utc(args.until) if args.until else (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(microsecond=0)
out = Path(args.out) if args.out else CACHE / f"lgbm_live_{until:%Y%m%dT%H%M}.txt"

t0 = time.time()
rt = RawTree(timeout=300)
snap = build_snapshot(rt, since, cache=True)
df, meta = build_dataset(rt, since, until, snap=snap, cache=not args.no_cache)
print(f"data ready in {time.time() - t0:.0f}s")
run(df, meta, out, valid_frac=args.valid_frac)
print(f"total {time.time() - t0:.0f}s")
