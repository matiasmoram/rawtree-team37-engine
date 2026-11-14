"""Build (and cache) a snapshot at a given UTC time: python scripts/build_snapshot.py [YYYY-MM-DDTHH:MM:SS]"""
import logging, sys, time
from datetime import datetime, timezone
sys.path.insert(0, ".")
from engine.rt import RawTree
from engine.snapshot import build_snapshot
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
T = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=timezone.utc) if len(sys.argv) > 1 else None
t0 = time.time()
snap = build_snapshot(RawTree(timeout=300), T, cache=True)
print("T", snap.T, "secs", round(time.time() - t0, 1), snap.build_secs)
print("products", len(snap.products), "active", sum(p.active for p in snap.products.values()), "new", sum(p.is_new for p in snap.products.values()))
print("stats", len(snap.stats), "carousel", len(snap.carousel), "covis_vv", len(snap.covis_vv), "covis_vb", len(snap.covis_vb))
print("users buy", len(snap.user_buy), "view", len(snap.user_view), "sub", len(snap.user_sub), "price", len(snap.user_price))
print("pop_global", snap.pop_global[:5], "trending", snap.trending[:5])
