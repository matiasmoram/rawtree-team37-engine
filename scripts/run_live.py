"""Run the live system.

    python scripts/run_live.py                           # current practice allocation
    python scripts/run_live.py --dry-run                 # rank and time everything, push nothing
"""
import argparse, logging, sys
from datetime import datetime, timezone
sys.path.insert(0, ".")
from engine.config import LOGS, TEAM
from engine.live import LiveRunner
from engine.policies.registry import get_policy

ap = argparse.ArgumentParser()
ap.add_argument("--arms", default="lgbm-recent:80,cf-v1:20",
                help="policy:share,... shares add up to 100; one purchase ranker and one cart-first challenger")
ap.add_argument("--dry-run", action="store_true")
ap.add_argument("--shard-index", type=int, default=0, help="exclusive request shard; coordinate on every writer")
ap.add_argument("--shard-count", type=int, default=1, help="all writers must use the same count")
ap.add_argument("--experiment-until", help="fixed UTC ISO deadline; restores --after-arms without restarting")
ap.add_argument("--after-arms", default="lgbm-recent:100")
args = ap.parse_args()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler(LOGS / "live.log", encoding="utf-8")])
def parse_arms(value):
    arms = []
    for part in value.split(","):
        name, share = part.split(":")
        weight = int(share)
        if weight < 0:
            ap.error("arm shares must be nonnegative")
        arms.append((get_policy(name), weight))
    return arms

deadline = None
if args.experiment_until:
    deadline = datetime.fromisoformat(args.experiment_until.replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    deadline = deadline.timestamp()
    if deadline <= datetime.now(timezone.utc).timestamp():
        ap.error("experiment deadline must be in the future")
LiveRunner(parse_arms(args.arms), TEAM, dry_run=args.dry_run, shard_index=args.shard_index,
           shard_count=args.shard_count, experiment_until=deadline,
           after_arms=parse_arms(args.after_arms) if deadline else None).run()
