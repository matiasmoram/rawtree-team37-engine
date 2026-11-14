"""LIVE submitter: pull -> predict -> push into team_NN.submissions.

Authorised by the user on 2026-11-14 (practice round), opaque model_version names. Two of our versions split
the requests by a fixed request_id hash range, so together they still answer 100% of requests:

    python -m recsys.submit --arms t37-m1:v21,t37-m2:blend,t37-m3:viewed

One process serves every version (one poll + one stock check: the RawTree API is the bottleneck).

Design (the RawTree API, not our model, is the bottleneck: queries 0.2-2 s, inserts sometimes > 5 s):
  - stock thread   refreshes out-of-stock products every second; serving never waits for it
  - main loop      polls only the last few seconds of shop.requests, scores new requests (~10 ms),
                   enqueues the batch
  - push workers   3 threads with their own HTTP sessions insert batches in parallel; an answer that is
                   already past the deadline is dropped instead of sent (it would only be replaced by the
                   fallback), and a failed insert is never retried
Latency is measured on the server clock (now64() returned with each poll), so a local clock skew cannot hide
lateness.

Stop: Ctrl-C, or create the file STOP_SUBMIT in the project root.
Log: data/submit_live.pkl (+ stdout)
"""
from __future__ import annotations

import argparse
import hashlib
import queue
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import data as D
from .config import V2
from .features import Store
from .online_head import OnlineHead
from .policies import Blend, Ranker, ViewedFirst

ROOT = Path(__file__).resolve().parent.parent
STOP = ROOT / "STOP_SUBMIT"
DEADLINE_S = 2.8          # organisers poll every 0.5 s; keep margin under 3 s
WORKERS = 4

NEW_REQUESTS = """
SELECT request_id::String request_id, toString(ts) ts, user_id::String user_id, is_new_user::Bool is_new_user,
       context, recent_views, toString(now64(3)) srv_now
FROM shop.requests WHERE ts::DateTime64(3) > now64(3) - INTERVAL 6 SECOND"""

OUT_OF_STOCK = """
SELECT product_id::String AS product_id FROM shop.catalog_updates
WHERE change::String IN ('out_of_stock', 'back_in_stock')
GROUP BY product_id HAVING argMax(change::String, ts::DateTime64(3)) = 'out_of_stock'"""


def mine(request_id: str, lo: float, hi: float) -> bool:
    """Fixed hash range of request_ids, so two of our versions never answer the same request."""
    h = int(hashlib.md5(request_id.encode()).hexdigest()[:8], 16) % 1000 / 1000
    return lo <= h < hi


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(D._http.headers)
    return s


class Submitter:
    def __init__(self, arms: list[tuple[str, str]]):
        """arms: [(model_version, policy name)]; requests are split into equal fixed hash ranges."""
        self.S = Store.build("live", cold_start=True)
        make = {"v21": lambda: Ranker.load(self.S, head=OnlineHead.load(V2)),
                "blend": lambda: Blend.load(self.S, head=OnlineHead.load(V2)),
                "viewed": lambda: ViewedFirst(Blend.load(self.S, head=OnlineHead.load(V2)))}
        k = len(arms)
        self.arms = [(v, make[p](), n / k, (n + 1) / k) for n, (v, p) in enumerate(arms)]
        self.version = "+".join(v for v, _ in arms)
        self.pid = self.S.items.product_id.to_numpy()
        self.inactive = set(np.flatnonzero(~self.S.items.is_active.to_numpy().astype(bool)))
        self.unavailable = set(self.inactive)
        self.q: queue.Queue = queue.Queue()
        self.log: list[dict] = []
        self.lock = threading.Lock()
        self.alive = True
        self.offset = pd.Timedelta(0)            # server clock - local clock

    # ---------------------------------------------------------------- threads
    def stock_loop(self):
        http = session()
        while self.alive:
            t = time.time()
            try:
                r = http.post(f"{D.API}/v1/query", json={"sql": OUT_OF_STOCK}, timeout=5)
                r.raise_for_status()
                oos = {self.S.pid2i[x["product_id"]] for x in r.json()["data"] if x["product_id"] in self.S.pid2i}
                self.unavailable = oos | self.inactive
            except Exception as e:
                print("stock check failed:", str(e)[:120], flush=True)
            time.sleep(max(0.0, 3.0 - (time.time() - t)))   # stock changes every few minutes

    def push_loop(self):
        http = session()
        while self.alive or not self.q.empty():
            try:
                batch = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            while True:                          # merge everything waiting into one insert
                try:
                    batch = batch + self.q.get_nowait()
                except queue.Empty:
                    break
            now = pd.Timestamp.utcnow().tz_localize(None) + self.offset
            fresh = [a for a in batch if (now - a["_ts"]).total_seconds() < DEADLINE_S]
            status = "dropped_late" if not fresh else "ok"
            if fresh:
                body = [{k: a[k] for k in ("request_id", "items", "model_version")} for a in fresh]
                try:
                    r = http.post(f"{D.API}/v1/tables/submissions", params={"database": D.TEAM}, json=body,
                                  timeout=8)
                    r.raise_for_status()
                except requests.exceptions.ReadTimeout:
                    status = "timeout_unknown"   # the insert may still land: check team feedback
                except Exception as e:
                    status = "push_failed"
                    print("push failed:", str(e)[:120], flush=True)
            done = pd.Timestamp.utcnow().tz_localize(None) + self.offset
            sent = {a["request_id"] for a in fresh}
            with self.lock:
                for a in batch:
                    self.log.append(dict(request_id=a["request_id"], ts=a["_ts"], items=a["items"],
                                         version=a["model_version"],
                                         latency_ms=(done - a["_ts"]).total_seconds() * 1000,
                                         status=status if a["request_id"] in sent else "dropped_late"))

    # ---------------------------------------------------------------- main loop
    def run(self, minutes: float):
        threads = [threading.Thread(target=self.stock_loop, daemon=True)] + \
                  [threading.Thread(target=self.push_loop, daemon=True) for _ in range(WORKERS)]
        for t in threads:
            t.start()
        http = session()
        seen: set[str] = set()
        first = True
        t_end, last_report = time.time() + 60 * minutes, time.time()
        for v, pol, lo, hi in self.arms:
            print(f"SUBMITTING as {v} ({pol.name}) on hash range [{lo:.3f}, {hi:.3f})", flush=True)
        while time.time() < t_end and not STOP.exists():
            t0 = time.time()
            try:
                r = http.post(f"{D.API}/v1/query", json={"sql": NEW_REQUESTS}, timeout=3)
                r.raise_for_status()
                df = pd.DataFrame(r.json()["data"])
                if len(df):
                    self.offset = pd.Timestamp(df.srv_now.iloc[0]) - pd.Timestamp.utcnow().tz_localize(None)
                    df = df[~df.request_id.isin(seen)].reset_index(drop=True)
                    seen.update(df.request_id)
                    if first:                       # skip whatever was already there at start
                        first, df = False, df.iloc[0:0]
                batch = []
                for v, pol, lo, hi in self.arms if len(df) else []:
                    sub = df[[mine(x, lo, hi) for x in df.request_id]].reset_index(drop=True)
                    if not len(sub):
                        continue
                    ts = pd.to_datetime(sub.ts)
                    unav = self.unavailable
                    lists = pol.recommend(self.S, self.S.requests(sub), [unav] * len(sub))
                    for k in range(len(sub)):
                        items = [str(x) for x in self.pid[lists[k]]]
                        if len(set(items)) == 10 and not (set(lists[k]) & unav):
                            batch.append(dict(request_id=sub.request_id[k], items=items, model_version=v, _ts=ts[k]))
                if batch:
                    self.q.put(batch)
            except Exception as e:
                print("poll error:", str(e)[:120], flush=True)
            if time.time() - last_report > 60:
                last_report = time.time()
                self.report()
            time.sleep(max(0.0, 0.25 - (time.time() - t0)))
        self.alive = False
        for t in threads[1:]:
            t.join(timeout=5)
        self.report()
        print("stopped", "(STOP_SUBMIT file)" if STOP.exists() else "(time limit)", flush=True)

    def report(self):
        with self.lock:
            out = pd.DataFrame(self.log)
        if not len(out):
            print("no answers yet", flush=True)
            return
        out.to_pickle(D.DATA / "submit_live.pkl")
        last = out[out.ts > out.ts.max() - pd.Timedelta(minutes=1)]
        st = last.status.value_counts(normalize=True).mul(100).round(1).to_dict()
        per = last.version.value_counts().to_dict()
        print(f"{pd.Timestamp.now():%H:%M:%S} {len(out)} total | last min {len(last)} {per}: {st} | latency p50 "
              f"{last.latency_ms.median():.0f} p95 {last.latency_ms.quantile(.95):.0f} ms | queue {self.q.qsize()}",
              flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", default="t37-m1:v21,t37-m2:blend,t37-m3:viewed",
                    help="comma-separated model_version:policy; equal fixed hash ranges, 100%% coverage")
    ap.add_argument("--minutes", type=float, default=180)
    a = ap.parse_args()
    Submitter([tuple(x.split(":")) for x in a.arms.split(",")]).run(a.minutes)
