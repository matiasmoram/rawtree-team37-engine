"""Learn bounded live residual calibration only from predictions actually shown.

Run outside serving: python scripts/refresh_calibration.py --once
Requires a learned policy's exposure_metadata.jsonl. Proposals that lost arbitration,
fallbacks and incomplete/different lists are excluded by matching feedback.shown.
No heuristic ranking score is treated as a probability. No submissions are written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from collections import deque
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.calibration import fit_groups
from engine.config import CACHE, LOGS, TEAM
from engine.experiments import write_health
from engine.rt import RawTree
from engine.types import parse_ts


def build_calibration(records, feedback, model_id, now, min_n=200):
    """Pure join + fit, convenient for regression tests and replays."""
    p, y, subs, slots = [], [], [], []
    seen = set()
    accepted = 0
    for row in records:
        meta = row.get("metadata", {})
        if meta.get("model_id") != model_id or meta.get("propensity_valid") is False:
            continue
        rid = row["request_id"]
        actual = feedback.get(rid)
        if rid in seen or not actual or actual.get("sb") != "team" or row.get("items") != actual.get("shown"):
            continue
        stamp = parse_ts(row["ts"]).timestamp()
        if not now - 7200 <= stamp <= now - 120:
            continue
        items = row["items"]
        if actual.get("purchased") and actual["purchased"] not in items:
            continue  # corrupted labels must not become ten false negatives
        probabilities = meta.get("base_probabilities", [])
        categories = meta.get("subcategories", [])
        if len(items) != 10 or len(set(items)) != 10 or len(probabilities) != 10 or len(categories) != 10:
            continue
        seen.add(rid)
        accepted += 1
        p.extend(probabilities)
        y.extend(int(pid == actual.get("purchased")) for pid in items)
        subs.extend(categories)
        slots.extend(range(10))
    groups = fit_groups(p, y, subs, slots, min_n=min_n, prior=5.0)
    return {"schema_version": 1, "model_id": model_id, "built_at": now,
            "source_until": now - 120, "window_seconds": 7200, "accepted_requests": accepted,
            "expected_purchases": sum(p), "observed_purchases": sum(y), "groups": groups,
            "status": "ready" if groups else "insufficient_support"}


def iteration(args):
    model = args.model
    if not model.exists():
        return {"status": "waiting_for_model"}
    sidecar = json.loads(model.with_suffix(".json").read_text(encoding="utf-8"))
    model_id = hashlib.sha256(model.read_bytes() + json.dumps(sidecar, sort_keys=True).encode()).hexdigest()[:20]
    source = LOGS / "exposure_metadata.jsonl"
    if not source.exists():
        return {"status": "waiting_for_observed_predictions", "model_id": model_id}
    rt = RawTree(timeout=20)
    now = parse_ts(rt.query("SELECT toString(now64(3)) AS n", retries=0)[0]["n"]).timestamp()
    records = []
    with source.open(encoding="utf-8") as f:
        for line in deque(f, maxlen=25000):
            try:
                row = json.loads(line)
                if row.get("metadata", {}).get("model_id") == model_id:
                    records.append(row)
            except (ValueError, TypeError):
                continue
    feedback = {}
    ids = list(dict.fromkeys(r["request_id"] for r in records))
    for start in range(0, len(ids), 250):
        literals = ",".join("'" + str(rid).replace("'", "''") + "'" for rid in ids[start:start + 250])
        rows = rt.query(f"SELECT request_id::String AS rid, shown::Array(String) AS shown, "
                        "served_by::String AS sb, ifNull(purchased::Nullable(String),'') AS purchased "
                        f"FROM {TEAM}.feedback WHERE request_id::String IN ({literals}) "
                        "SETTINGS max_execution_time=15", retries=0)
        for row in rows:
            if row["rid"] in feedback:
                raise ValueError("duplicate feedback is not safe for calibration")
            feedback[row["rid"]] = row
    payload = build_calibration(records, feedback, model_id, now, args.min_n)
    # Low support never replaces a previously valid calibration snapshot.
    if payload["status"] == "ready":
        write_health(CACHE / "online_calibration.json", payload)
    return {key: value for key, value in payload.items() if key != "groups"} | {"groups": len(payload["groups"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", type=Path, default=CACHE / "lgbm_recent.txt")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--every", type=int, default=60)
    ap.add_argument("--min-n", type=int, default=200)
    args = ap.parse_args()
    if args.every < 30 or args.min_n < 50:
        ap.error("every >= 30 and min-n >= 50 are required")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    while True:
        try:
            logging.info("calibration %s", json.dumps(iteration(args)))
        except Exception:
            logging.exception("calibration refresh failed; previous snapshot retained")
            if args.once:
                raise
        if args.once:
            break
        time.sleep(args.every)


if __name__ == "__main__":
    main()
