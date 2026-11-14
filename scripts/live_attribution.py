"""Live attribution: per shown item in our feedback, conversion by its relation to the shopper.

    python scripts/live_attribution.py --since "2026-11-14 13:51:00"
Uses the latest cached snapshot for user history. Relations are exclusive, checked in order.
"""
import argparse, glob, pickle, sys
from collections import defaultdict
sys.path.insert(0, ".")
from engine.config import TEAM
from engine.rt import RawTree
from engine.types import Request
from engine.policies.prepare import prepare_snapshot

ap = argparse.ArgumentParser(); ap.add_argument("--since", required=True); ap.add_argument("--model", default="")
a = ap.parse_args()
snap = pickle.load(open(sorted(glob.glob("cache/snapshot_2026111*.pkl"))[-1], "rb")); prepare_snapshot(snap)
rt = RawTree(timeout=120)
mv_filter = f"AND s.mv = '{a.model}'" if a.model else ""
rows = rt.query(f"""
SELECT f.rid AS request_id, f.shown AS shown, f.clk AS clk, f.pur AS pur, s.mv AS mv, r.ts AS ts, r.user_id AS user_id, r.is_new_user AS is_new_user,
       r.page AS page, r.device AS device, r.region AS region, r.recent_views AS recent_views
FROM (SELECT request_id::String AS rid, shown::Array(String) AS shown, ifNull(clicked::Nullable(String),'') AS clk, ifNull(purchased::Nullable(String),'') AS pur
      FROM {TEAM}.feedback WHERE ts::DateTime64(3) > '{a.since}' AND served_by::String = 'team') AS f
INNER JOIN (SELECT request_id::String AS rid, ts::DateTime64(3) AS ts, user_id::String AS user_id, is_new_user::Bool AS is_new_user, context.page::String AS page,
            context.device::String AS device, context.region::String AS region, recent_views FROM shop.requests WHERE ts::DateTime64(3) > toDateTime64('{a.since}', 3) - INTERVAL 1 MINUTE) AS r ON r.rid = f.rid
LEFT JOIN (SELECT request_id::String AS rid, items::Array(String) AS sent_items,
                  if(uniqExact(model_version::String) = 1, any(model_version::String), '(ambiguous)') AS mv
           FROM {TEAM}.submissions GROUP BY rid, sent_items) AS s ON s.rid = f.rid AND s.sent_items = f.shown
WHERE 1 {mv_filter}
SETTINGS max_execution_time = 120""", timeout=150)
agg = defaultdict(lambda: [0, 0, 0]); slot_agg = defaultdict(lambda: [0, 0, 0])
for row in rows:
    req = Request.from_row(row)
    viewed = req.viewed; last = snap.products.get(viewed[0]) if viewed else None
    ubuy = snap.user_buy.get(req.user_id, {}); uview = snap.user_view.get(req.user_id, {})
    vsubs = {snap.products[p].sub for p in viewed if p in snap.products}; vcats = {snap.products[p].cat for p in viewed if p in snap.products}
    for slot, pid in enumerate(row["shown"]):
        p = snap.products.get(pid)
        if pid in viewed: rel = "viewed_last" if pid == viewed[0] else "viewed_earlier"
        elif pid in ubuy: rel = "user_bought_before"
        elif pid in uview: rel = "user_viewed_before"
        elif p and p.sub in vsubs: rel = "same_sub_as_session"
        elif p and p.cat in vcats: rel = "same_cat_as_session"
        else: rel = "other" + ("_home" if not viewed else "")
        a_ = agg[rel]; a_[0] += 1; a_[1] += pid == row["clk"]; a_[2] += pid == row["pur"]
        s_ = slot_agg[slot + 1]; s_[0] += 1; s_[1] += pid == row["clk"]; s_[2] += pid == row["pur"]
print(f"requests={len(rows)}")
print(f"{'relation':24s} {'shown':>7s} {'clicks':>6s} {'buys':>5s} {'ctr%':>6s} {'buy%':>6s}")
for rel, (n, c, b) in sorted(agg.items(), key=lambda x: -x[1][0]):
    print(f"{rel:24s} {n:7d} {c:6d} {b:5d} {100*c/n:6.3f} {100*b/n:6.3f}")
print("by slot:", {k: (v[0], v[1], v[2]) for k, v in sorted(slot_agg.items())})
