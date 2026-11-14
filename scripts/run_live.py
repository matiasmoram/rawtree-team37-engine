"""Run the live system.

    python scripts/run_live.py --arms ev-v1:100            # live
    python scripts/run_live.py --arms ev-v1:100 --dry-run  # rank and time everything, push nothing
"""
import argparse, logging, sys
sys.path.insert(0, ".")
from engine.config import LOGS, TEAM
from engine.live import LiveRunner
from engine.policies.registry import get_policy

ap = argparse.ArgumentParser()
ap.add_argument("--arms", default="ev-v1:100", help="policy:share,... shares add up to 100")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler(LOGS / "live.log", encoding="utf-8")])
arms = []
for part in args.arms.split(","):
    name, share = part.split(":")
    arms.append((get_policy(name), int(share)))
LiveRunner(arms, TEAM, dry_run=args.dry_run).run()
