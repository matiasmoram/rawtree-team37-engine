"""Keep cache/live_snapshot.pkl fresh in a separate process, so live restarts only download a small delta.

    python scripts/refresh_cache.py --every 1800
Every `every` seconds: load the persisted snapshot, apply the live delta, save it atomically.
Once a day (or if the cache is missing/too old) it does a full rebuild, which also refreshes co-visitation.
"""
import argparse, logging, sys, time
sys.path.insert(0, ".")
from engine.config import LOGS
from engine.rt import RawTree
from engine.snapshot import apply_delta, build_snapshot, latest_cached, save_live

ap = argparse.ArgumentParser(); ap.add_argument("--every", type=float, default=1800); ap.add_argument("--once", action="store_true")
args = ap.parse_args()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler(LOGS / "refresh_cache.log", encoding="utf-8")])
log = logging.getLogger("refresh")
while True:
    try:
        rt = RawTree(timeout=300)
        snap = latest_cached(max_age_hours=24)
        if snap is None:
            log.info("no usable cache: full rebuild")
            snap = build_snapshot(rt)
        else:
            t0 = time.time(); n = apply_delta(rt, snap); log.info("delta %d rows in %.1fs -> T=%s", n, time.time() - t0, snap.T)
        save_live(snap)
        log.info("saved cache/live_snapshot.pkl at T=%s", snap.T)
    except Exception as e:
        log.warning("refresh failed: %s", str(e)[:300])
    if args.once:
        break
    time.sleep(args.every)
