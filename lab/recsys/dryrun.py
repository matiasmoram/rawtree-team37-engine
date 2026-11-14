"""Dry run against the LIVE stream: pull → predict → (no push). Measures if we would make the 3 s deadline.

    python -m recsys.dryrun --policy ranker --seconds 60

It polls shop.requests like the real system, keeps live stock fresh, computes the 10 items per request and
records latency from each request's own ts. It NEVER writes to team_NN.submissions: there is no insert call
in this file. Answers are saved to data/dryrun_<policy>.pkl for inspection.
"""
from __future__ import annotations

import argparse
import time

import numpy as np
import pandas as pd

from . import data as D
from .features import Store
from .policies import Baseline, CategoryFirst, Ranker

NEW_REQUESTS = """
SELECT request_id::String request_id, toString(ts) ts, user_id::String user_id, is_new_user::Bool is_new_user,
       context, recent_views
FROM shop.requests ORDER BY ts DESC LIMIT 60"""

OUT_OF_STOCK = """
SELECT product_id::String AS product_id FROM shop.catalog_updates
WHERE change::String IN ('out_of_stock', 'back_in_stock')
GROUP BY product_id HAVING argMax(change::String, ts::DateTime64(3)) = 'out_of_stock'"""


def main(policy_name: str, seconds: int) -> None:
    S = Store.build("live")
    policy = {"baseline": Baseline, "category_first": CategoryFirst}.get(policy_name)
    policy = policy(S) if policy else Ranker.load(S)
    inactive = set(np.flatnonzero(~S.items.is_active.to_numpy().astype(bool)))
    seen: set[str] = set(D.sql(NEW_REQUESTS).request_id)       # only answer requests that arrive from now on
    unavailable, stock_t, log = set(), 0.0, []
    t_end = time.time() + seconds
    print(f"dry run: policy={policy.name}, {seconds}s, NOT submitting", flush=True)
    while time.time() < t_end:
        try:
            if time.time() - stock_t >= 1:
                stock_t = time.time()
                unavailable = {S.pid2i[p] for p in D.sql(OUT_OF_STOCK).product_id if p in S.pid2i} | inactive
            df = D.sql(NEW_REQUESTS)
            df = df[~df.request_id.isin(seen)].reset_index(drop=True)
            if len(df):
                seen.update(df.request_id)
                R = S.requests(df)
                lists = policy.recommend(S, R, [unavailable] * len(df))
                done = pd.Timestamp.utcnow().tz_localize(None)
                lat = (done - pd.to_datetime(df.ts)).dt.total_seconds() * 1000
                pid = S.items.product_id.to_numpy()
                for r in range(len(df)):
                    items = list(pid[lists[r]])
                    log.append(dict(request_id=df.request_id[r], ts=df.ts[r], latency_ms=lat[r], items=items,
                                    valid=len(set(items)) == 10 and not (set(lists[r]) & unavailable),
                                    page=df.context[r].get("page") if isinstance(df.context[r], dict) else None))
        except Exception as e:  # keep going, like the real loop
            print("error:", e, flush=True)
            time.sleep(1)
        time.sleep(0.3)
    out = pd.DataFrame(log)
    out.to_pickle(D.DATA / f"dryrun_{policy.name}.pkl")
    if len(out):
        q = out.latency_ms.quantile([0.5, 0.95, 0.99]).round(0).to_dict()
        print(f"answered {len(out)} requests in {seconds}s | valid {100 * out.valid.mean():.1f}% | "
              f"latency from request ts p50 {q[0.5]:.0f} ms, p95 {q[0.95]:.0f} ms, p99 {q[0.99]:.0f} ms | "
              f"within 3 s: {100 * (out.latency_ms <= 3000).mean():.1f}%")
        print(out[["request_id", "page", "latency_ms", "items"]].head(3).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="ranker", choices=["baseline", "category_first", "ranker"])
    ap.add_argument("--seconds", type=int, default=60)
    a = ap.parse_args()
    main(a.policy, a.seconds)
