"""LIVE serving for t37-m4: poll -> Thompson-ranked lists -> push, with the learner, state refresh and guards
running on their own threads.

    python -m recsys.thompson.serve --dry-run --minutes 2     # no inserts
    python -m recsys.thompson.serve --minutes 900             # live (refuses while STOP_SUBMIT exists)

Stop: Ctrl-C or create STOP_SUBMIT in the repo root.
"""
from __future__ import annotations

import argparse
import queue
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .. import data as D
from .features import Req
from .guards import (COLLISION_SQL, PerfGuard, collision_rate, foreign_on_our_shard, leaderboard_window, owns)
from .learner import MODELS, Learner
from .model import Posterior
from .ranker import banned, fill, rank

ROOT = Path(__file__).resolve().parents[2]
STOP = ROOT / "STOP_SUBMIT"
DEADLINE_S = 2.8
WORKERS = 4
POLLERS = 2          # staggered parallel polls: one slow RawTree query no longer blocks the next poll
NEW_REQUESTS = """
SELECT request_id::String request_id, toString(ts) ts, user_id::String user_id, is_new_user::Bool is_new_user,
       context, recent_views, toString(now64(3)) srv_now
FROM shop.requests WHERE ts::DateTime64(3) > now64(3) - INTERVAL 6 SECOND"""
OUT_OF_STOCK = """
SELECT product_id::String AS product_id FROM shop.catalog_updates
WHERE change::String IN ('out_of_stock', 'back_in_stock')
GROUP BY product_id HAVING argMax(change::String, ts::DateTime64(3)) = 'out_of_stock'"""


def session():
    import requests
    s = requests.Session()
    s.headers.update(D._http.headers)
    return s


class Server:
    def __init__(self, version: str = "t37-m4", shard: int = 1, count: int = 2, guard: bool = True,
                 dry_run: bool = False, st=None, learner: Learner | None = None, log_path: Path | None = None,
                 redraw_s: float = 5.0, control: str | None = None):
        from .state import LiveState
        self.version, self.shard, self.count, self.guard, self.dry_run = version, shard, count, guard, dry_run
        self.control = control
        self.st = st if st is not None else LiveState.load()
        if learner is None:
            post = Posterior.load(MODELS / "posterior_latest.pkl")
            learner = Learner(self.st, post)
        self.learner = learner
        self.rng = np.random.default_rng()
        self.draw = self.learner.current().draw(self.rng)
        self.draw_version = self.learner.current().version
        self.redraw_s = redraw_s
        self.log_path = log_path or (D.DATA / "thompson_serve.pkl")
        self.q: queue.Queue = queue.Queue()
        self.log: list[dict] = []
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.offset = pd.Timedelta(0)
        self.seen: set[str] = set()
        self.seen_lock = threading.Lock()
        self.first = True
        self.perf = PerfGuard()

    # ------------------------------------------------------------------ ranking
    def _one(self, row: dict) -> dict:
        st = self.st
        req = Req.from_row(row, st)
        level, items = 0, None
        post = self.learner.current()
        for lvl, d in ((0, self.draw), (1, post.mean_draw()), (2, post.anchor_draw())):
            try:
                items = rank(st, req, d)
                level = lvl
                break
            except Exception as e:
                if lvl == 0:
                    print("rank failed, falling back:", str(e)[:120], flush=True)
        if items is None:
            level = 3
            try:
                ban = banned(st, req)
            except Exception:
                ban = set(st.oos)
            items = fill(st, [], ban)
        pid = st.items.product_id.to_numpy()
        return dict(request_id=row["request_id"], items=[str(x) for x in pid[items]], model_version=self.version,
                    _ts=pd.Timestamp(row["ts"]), user_id=row.get("user_id"), fallback=level, draw=self.draw.id,
                    pv=post.version)

    def answer(self, df: pd.DataFrame) -> list[dict]:
        out = []
        for row in df.to_dict("records"):
            if not owns(row["request_id"], self.shard, self.count):
                continue
            try:
                a = self._one(row)
            except Exception as e:
                print("answer failed:", str(e)[:120], flush=True)
                continue
            if len(set(a["items"])) == 10:
                out.append(a)
        return out

    def _claim(self, ids: list[str]) -> list[str]:
        """Mark ids as seen; return the ones nobody claimed before."""
        with self.seen_lock:
            new = [r for r in ids if r not in self.seen]
            self.seen.update(new)
        return new

    def poll_once(self, http) -> list[dict]:
        try:
            r = http.post(f"{D.API}/v1/query", json={"sql": NEW_REQUESTS}, timeout=3)
            r.raise_for_status()
            df = pd.DataFrame(r.json()["data"])
        except Exception as e:
            print("poll error:", str(e)[:120], flush=True)
            return []
        if not len(df):
            return []
        self.offset = pd.Timestamp(df.srv_now.iloc[0]) - pd.Timestamp.utcnow().tz_localize(None)
        new = set(self._claim(df.request_id.tolist()))
        df = df[df.request_id.isin(new)].reset_index(drop=True)
        with self.seen_lock:
            skip, self.first = self.first, False
        if skip:                               # skip whatever was already there at start
            return []
        return self.answer(df)

    # ------------------------------------------------------------------ threads
    def poll_loop(self, delay: float = 0.0):
        http = session()
        time.sleep(delay)
        while not self.stop.is_set():
            t0 = time.time()
            batch = self.poll_once(http)
            if batch:
                self.q.put(batch)
            time.sleep(max(0.0, 0.25 - (time.time() - t0)))

    def stock_loop(self):
        http = session()
        while not self.stop.is_set():
            try:
                r = http.post(f"{D.API}/v1/query", json={"sql": OUT_OF_STOCK}, timeout=5)
                r.raise_for_status()
                self.st.oos = {self.st.pid2i[x["product_id"]] for x in r.json()["data"] if x["product_id"] in self.st.pid2i}
            except Exception as e:
                print("stock check failed:", str(e)[:120], flush=True)
            self.stop.wait(3.0)

    def draw_loop(self):
        while not self.stop.wait(self.redraw_s):
            try:
                post = self.learner.current()
                self.draw = post.draw(self.rng)
                self.draw_version = post.version
            except Exception as e:
                print("draw failed:", str(e)[:120], flush=True)

    def push_loop(self):
        import requests
        http = session()
        while not self.stop.is_set() or not self.q.empty():
            try:
                batch = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            while True:
                try:
                    batch = batch + self.q.get_nowait()
                except queue.Empty:
                    break
            now = pd.Timestamp.utcnow().tz_localize(None) + self.offset
            fresh = [a for a in batch if (now - a["_ts"]).total_seconds() < DEADLINE_S]
            status = "dropped_late" if not fresh else ("dry_run" if self.dry_run else "ok")
            if fresh and not self.dry_run:
                body = [{k: a[k] for k in ("request_id", "items", "model_version")} for a in fresh]
                try:
                    r = http.post(f"{D.API}/v1/tables/submissions", params={"database": D.TEAM}, json=body, timeout=8)
                    r.raise_for_status()
                except requests.exceptions.ReadTimeout:
                    status = "timeout_unknown"
                except Exception as e:
                    status = "push_failed"
                    print("push failed:", str(e)[:120], flush=True)
            done = pd.Timestamp.utcnow().tz_localize(None) + self.offset
            sent = {a["request_id"] for a in fresh}
            with self.lock:
                for a in batch:
                    self.log.append(dict(request_id=a["request_id"], ts=a["_ts"], items=a["items"],
                                         version=a["model_version"], fallback=a["fallback"], draw=a["draw"],
                                         pv=a["pv"], latency_ms=(done - a["_ts"]).total_seconds() * 1000,
                                         status=status if a["request_id"] in sent else "dropped_late"))

    def guard_loop(self):
        last_perf = time.time()
        while not self.stop.wait(300):
            try:
                rate = collision_rate(D.sql(COLLISION_SQL.format(team=D.TEAM), timeout=30), self.version)
                if rate > 0.05 and not self.dry_run:
                    print(f"GUARD: {rate:.0%} of our requests also answered by another version -> stopping", flush=True)
                    self.stop.set()
                    return
            except Exception as e:
                print("guard: collision check failed:", str(e)[:120], flush=True)
            if self.guard and time.time() - last_perf >= 1800:
                last_perf = time.time()
                w = leaderboard_window(self.version, D.TEAM, 30, control=self.control)
                if w is None:
                    continue
                verdict = self.perf.observe(w.ours, w.ctrl, w.n_ours)
                print(f"guard: 30-min window ours {w.ours:.3f} vs {w.ctrl_version} {w.ctrl:.3f} (n={w.n_ours}) -> "
                      f"{verdict}", flush=True)
                if verdict == "reset":
                    self.learner.reset_to_anchor()
                elif verdict == "stop":
                    print("GUARD: frozen start also lost two windows -> STOP_SUBMIT", flush=True)
                    STOP.write_text(f"written by thompson guard at {pd.Timestamp.now()}\n")
                    self.stop.set()
                    return

    # ------------------------------------------------------------------ main
    def preflight(self) -> bool:
        if self.dry_run:
            return True
        if STOP.exists():
            print("refusing to start: STOP_SUBMIT exists (delete it to go live)", flush=True)
            return False
        try:
            share = foreign_on_our_shard(D.sql(COLLISION_SQL.format(team=D.TEAM), timeout=30), self.version,
                                         self.shard, self.count)
        except Exception as e:
            print("refusing to start: collision check failed:", str(e)[:120], flush=True)
            return False
        if share > 0.05:
            print(f"refusing to start: {share:.0%} of shard-{self.shard} requests are already answered by another "
                  f"version (teammate must run --shard-index 0 --shard-count 2)", flush=True)
            return False
        return True

    def run(self, minutes: float):
        if not self.preflight():
            return
        threads = [threading.Thread(target=f, daemon=True) for f in
                   (self.stock_loop, self.draw_loop, self.guard_loop,
                    lambda: self.st.refresh_loop(self.stop), lambda: self.learner.loop(self.stop))]
        pushers = [threading.Thread(target=self.push_loop, daemon=True) for _ in range(WORKERS)]
        for t in threads + pushers:
            t.start()
        mode = "DRY RUN (no inserts)" if self.dry_run else "SUBMITTING"
        print(f"{mode} as {self.version} on shard {self.shard}/{self.count}, posterior v{self.learner.current().version}",
              flush=True)
        pollers = [threading.Thread(target=self.poll_loop, args=(k * 0.25 / POLLERS,), daemon=True)
                   for k in range(POLLERS)]
        for t in pollers:
            t.start()
        t_end, last_report = time.time() + 60 * minutes, time.time()
        try:
            while time.time() < t_end and not self.stop.is_set() and not (STOP.exists() and not self.dry_run):
                if time.time() - last_report > 60:
                    last_report = time.time()
                    self.report()
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        self.stop.set()
        for t in pushers:
            t.join(timeout=5)
        self.report()
        print("stopped", flush=True)

    def report(self):
        with self.lock:
            out = pd.DataFrame(self.log)
        if not len(out):
            print("no answers yet", flush=True)
            return
        out.to_pickle(self.log_path)
        last = out[out.ts > out.ts.max() - pd.Timedelta(seconds=60)]
        st = last.status.value_counts(normalize=True).mul(100).round(1).to_dict()
        fb = last.fallback.value_counts().to_dict()
        h = self.learner.history[-1] if self.learner.history else {}
        print(f"{pd.Timestamp.now():%H:%M:%S} {len(out)} total | last min {len(last)}: {st} | fallback {fb} | "
              f"latency p50 {last.latency_ms.median():.0f} p95 {last.latency_ms.quantile(.95):.0f} ms | "
              f"posterior v{self.learner.current().version} (last step rows {h.get('rows', 0)}, ok {h.get('ok')}) | "
              f"queue {self.q.qsize()}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="t37-m4")
    ap.add_argument("--minutes", type=float, default=900)
    ap.add_argument("--shard", type=int, default=1)
    ap.add_argument("--count", type=int, default=2)
    ap.add_argument("--no-guard", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--control", help="engine arm the performance guard compares against (e.g. t37-cf-v1)")
    a = ap.parse_args()
    Server(a.version, a.shard, a.count, guard=not a.no_guard, dry_run=a.dry_run, control=a.control).run(a.minutes)


if __name__ == "__main__":
    main()
