"""Live system: poll shop.requests, rank, push batches to team_NN.submissions, keep knowledge fresh.

Threads:
  poller     reads new requests (ts watermark) and ranks them immediately
  pusher     inserts answers in batches every PUSH_EVERY seconds, retries until the deadline
  stock      applies new catalogue updates (stock-outs, prices, new products) every STOCK_EVERY seconds
  refresher  refreshes item counters and recent user purchases every FAST_EVERY seconds
  rebuilder  rebuilds the full snapshot (co-visitation, user profiles incl. live events) every FULL_EVERY seconds
Traffic is split between policies ("arms") by a stable hash of request_id, so arms can be compared on feedback.
"""
from __future__ import annotations

import hashlib
import os
import signal
import logging
import queue
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from .config import LOGS
from .policies.base import K, fill
from .policies.evidence import attach_sub_quality
from .rt import RawTree
from .snapshot import Snapshot, build_snapshot, load_products, load_stats, _rank_lists
from .types import Request, parse_ts, sql_ts

log = logging.getLogger("live")

POLL_SLEEP = 0.2
N_POLLERS = 2
PUSH_EVERY = 0.1
PUSH_WORKERS = 4
STOCK_EVERY = 0.5
UPDATE_OVERLAP = timedelta(seconds=30)
FAST_EVERY = 60.0
BUYS_EVERY = 20.0
FULL_EVERY = 60 * 60.0
DEADLINE = 3.0

POLL_SQL = """
SELECT request_id::String AS request_id, ts::DateTime64(3) AS ts, user_id::String AS user_id,
       is_new_user::Bool AS is_new_user, context.page::String AS page, context.device::String AS device,
       context.region::String AS region, recent_views
FROM shop.requests WHERE ts::DateTime64(3) > '{since}' ORDER BY ts"""

RECENT_BUYS_SQL = """
SELECT u, groupUniqArray(p) AS ps FROM (
  SELECT user_id::String AS u, product_id::String AS p FROM shop.events
  WHERE event_type::String = 'purchase' AND ts::DateTime64(3) > now() - INTERVAL 6 HOUR
  UNION ALL
  SELECT r.user_id::String AS u, f.purchased::String AS p
  FROM {team}.feedback AS f INNER JOIN shop.requests AS r ON r.request_id::String = f.request_id::String
  WHERE f.purchased::String != '' AND f.ts::DateTime64(3) > now() - INTERVAL 6 HOUR AND r.ts::DateTime64(3) > now() - INTERVAL 7 HOUR
) GROUP BY u"""


def arm_bucket(request_id: str) -> int:
    return int(hashlib.md5(request_id.encode()).hexdigest()[:8], 16) % 100


class LiveRunner:
    def __init__(self, arms: list[tuple[object, int]], team: str, dry_run: bool = False) -> None:
        assert sum(share for _, share in arms) == 100, "arm shares must add up to 100"
        self.arms = arms
        self.team = team
        self.dry_run = dry_run
        self.snap: Snapshot | None = None
        self.outbox: queue.Queue = queue.Queue()
        self.seen: dict[str, float] = {}
        self.watermark = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.last_update_ts: datetime | None = None
        self.stop = threading.Event()
        self.stats = {"answered": 0, "pushed": 0, "push_fail": 0, "late": 0, "errors": 0}
        self.latencies: deque = deque(maxlen=3000)
        self.lock = threading.Lock()
        self.clock_offset = 0.0  # server clock minus local clock, seconds (deadlines use the server clock)
        self.seen_lock = threading.Lock()

    def measure_offset(self, rt: RawTree) -> None:
        samples = []
        for _ in range(5):
            t0 = time.time()
            row = rt.query("SELECT toString(now64(3)) AS n", timeout=5, retries=0)[0]
            t1 = time.time()
            samples.append((t1 - t0, parse_ts(row["n"]).timestamp() - (t0 + t1) / 2))
        samples.sort()
        self.clock_offset = sorted(off for _, off in samples[:3])[1]  # median of the 3 fastest round trips
        log.info("clock offset server-local = %+.3fs", self.clock_offset)

    # ---- arms -----------------------------------------------------------------------
    def pick(self, request_id: str):
        b = arm_bucket(request_id)
        acc = 0
        for policy, share in self.arms:
            acc += share
            if b < acc:
                return policy
        return self.arms[-1][0]

    # ---- knowledge ------------------------------------------------------------------
    def build(self) -> None:
        rt = RawTree(timeout=300)
        snap = build_snapshot(rt)
        attach_sub_quality(snap)
        if self.snap is not None:
            snap.recent_user_buys = self.snap.recent_user_buys
        # The snapshot holds the catalogue as of snap.T; replay updates since then before publishing it.
        with self.lock:
            self.last_update_ts = snap.T - timedelta(minutes=5)
        self.apply_updates(rt, snap)
        self.snap = snap
        log.info("snapshot ready: %s users=%d products=%d", snap.build_secs, len(snap.user_buy), len(snap.products))

    def apply_updates(self, rt: RawTree, snap: Snapshot | None = None) -> None:
        snap = snap or self.snap
        with self.lock:
            since = sql_ts(self.last_update_ts - UPDATE_OVERLAP)
        rows = rt.query(
            "SELECT product_id::String AS pid, change::String AS change, ts::DateTime64(3) AS ts, category::String AS cat, "
            "subcategory::String AS sub, brand::String AS brand, price_eur::Float64 AS price, description::String AS descr, "
            f"is_active::Bool AS active FROM shop.catalog_updates WHERE ts::DateTime64(3) >= '{since}' ORDER BY ts", timeout=10)
        if not rows:
            return
        from .snapshot import Product
        products = snap.products
        if any(r["pid"] not in products for r in rows):
            products = dict(products)  # copy-on-add: policies may be iterating the old dict
        for r in rows:
            ts = parse_ts(r["ts"])
            p = products.get(r["pid"])
            if p is None:
                p = Product(r["pid"], r["cat"], r["sub"], r["brand"], float(r["price"]), float(r["price"]), r["descr"], bool(r["active"]))
                products[r["pid"]] = p
            if r["change"] == "new_product":
                p.is_new, p.added_ts = True, ts
            if r["change"] == "price_change" and abs(float(r["price"]) - p.price) > 1e-9:
                p.price_changed_ts = ts
            p.price, p.active = float(r["price"]), bool(r["active"])
            p.cat, p.sub, p.brand, p.descr = r["cat"], r["sub"], r["brand"], r["descr"]
            with self.lock:
                self.last_update_ts = max(self.last_update_ts, ts)
        snap.products = products

    # ---- threads ----------------------------------------------------------------------
    def poller(self, offset: float = 0.0) -> None:
        rt = RawTree(timeout=2.5)
        self.stop.wait(offset)
        while not self.stop.is_set():
            try:
                since = sql_ts(self.watermark - timedelta(seconds=8))
                rows = rt.query(POLL_SQL.format(since=since), timeout=2.5, retries=0)
                now = time.time()
                for row in rows:
                    rid = str(row.get("request_id"))
                    with self.seen_lock:
                        if rid in self.seen:
                            continue
                        self.seen[rid] = now  # claim it: answer() cannot raise (valid_items is total)
                    try:
                        req = Request.from_row(row)
                    except Exception as e:
                        self.stats["errors"] += 1
                        log.warning("unparseable request %s: %s", rid, str(e)[:200])
                        continue
                    self.answer(req)
                    if req.ts > self.watermark:
                        self.watermark = req.ts
                if len(self.seen) > 20000:
                    with self.seen_lock:
                        cutoff = now - 600
                        self.seen = {k: v for k, v in self.seen.items() if v > cutoff}
            except Exception as e:
                self.stats["errors"] += 1
                log.warning("poll error: %s", str(e)[:200])
                time.sleep(0.5)
            time.sleep(POLL_SLEEP)

    def answer(self, req: Request) -> None:
        snap = self.snap
        policy = self.pick(req.request_id)
        try:
            items = policy.recommend(req, snap)
            version = f"t37-{policy.name}"
        except Exception as e:
            log.exception("policy %s failed on %s: %s", policy.name, req.request_id, e)
            items, version = [], "t37-safety"
        items = self.valid_items(items, snap)
        self.outbox.put((req, {"request_id": req.request_id, "items": items, "model_version": version}))
        self.stats["answered"] += 1

    @staticmethod
    def valid_items(items: list[str], snap: Snapshot) -> list[str]:
        """Guarantee K distinct active ids using the current catalogue; never raises."""
        try:
            if len(items) == K and len(set(items)) == K and all(snap.is_valid(p) for p in items):
                return items
            out = fill(items, snap)
            if len(out) == K:
                return out
        except Exception:
            pass
        out = []
        for pid, p in list(snap.products.items()):
            if p.active and pid not in out:
                out.append(pid)
                if len(out) == K:
                    break
        return out

    def _send(self, batch: list) -> None:
        rt = getattr(self._tls, "rt", None)
        if rt is None:
            rt = self._tls.rt = RawTree(timeout=2.0)
        try:
            if not self.dry_run:
                rt.insert("submissions", [rec for _, rec in batch], database=self.team, timeout=2.0)
            done = time.time() + self.clock_offset
            for req, _ in batch:
                self.latencies.append(done - req.ts.timestamp())
            self.stats["pushed"] += len(batch)
        except Exception as e:
            self.stats["push_fail"] += 1
            msg = str(e)
            log.warning("push failed (%d rows): %s", len(batch), msg[:160])
            if "insert HTTP 4" in msg:
                for req, rec in batch:  # a bad row: send rows one by one once, drop the ones that still fail
                    try:
                        rt.insert("submissions", [rec], database=self.team, timeout=2.0)
                        self.stats["pushed"] += 1
                    except Exception as e2:
                        log.warning("dropping %s: %s", rec["request_id"], str(e2)[:160])
            else:
                for item in batch:  # transport error: back to the outbox, the collector drops it once too late
                    self.outbox.put(item)

    def pusher(self) -> None:
        self._tls = threading.local()
        pool = ThreadPoolExecutor(max_workers=PUSH_WORKERS, thread_name_prefix="push")
        while not self.stop.is_set():
            pending = []
            while True:
                try:
                    pending.append(self.outbox.get_nowait())
                except queue.Empty:
                    break
            if pending:
                now = time.time() + self.clock_offset
                batch = [(req, rec) for req, rec in pending if now - req.ts.timestamp() < DEADLINE + 1]
                self.stats["late"] += len(pending) - len(batch)
                if batch:
                    snap = self.snap
                    for _, rec in batch:
                        rec["items"] = self.valid_items(rec["items"], snap)
                    pool.submit(self._send, batch)
            time.sleep(PUSH_EVERY)

    def stock(self) -> None:
        rt = RawTree(timeout=10)
        while not self.stop.is_set():
            try:
                self.apply_updates(rt)
            except Exception as e:
                log.warning("stock refresh failed: %s", str(e)[:200])
            self.stop.wait(STOCK_EVERY)

    def refresher(self) -> None:
        rt = RawTree(timeout=60)
        last_fast = time.time()
        while not self.stop.is_set():
            try:
                rows = rt.query(RECENT_BUYS_SQL.format(team=self.team), timeout=30)
                self.snap.recent_user_buys = {r["u"]: set(r["ps"]) for r in rows}
            except Exception as e:
                log.warning("recent buys refresh failed: %s", str(e)[:200])
            if time.time() - last_fast >= FAST_EVERY:
                try:
                    snap = self.snap
                    snap.stats = load_stats(rt, datetime.now(timezone.utc))
                    _rank_lists(snap)
                    attach_sub_quality(snap)
                    last_fast = time.time()
                except Exception as e:
                    log.warning("fast refresh failed: %s", str(e)[:200])
            self.stop.wait(BUYS_EVERY)

    def rebuilder(self) -> None:
        while not self.stop.wait(FULL_EVERY):
            try:
                self.build()
            except Exception as e:
                log.warning("full rebuild failed, keeping old snapshot: %s", str(e)[:200])

    def reporter(self) -> None:
        rt = RawTree(timeout=10)
        n = 0
        while not self.stop.wait(60):
            n += 1
            if n % 10 == 0:
                try:
                    self.measure_offset(rt)
                except Exception as e:
                    log.warning("offset refresh failed: %s", str(e)[:200])
            lat = sorted(self.latencies)
            p50 = lat[len(lat) // 2] if lat else 0
            p95 = lat[int(len(lat) * 0.95)] if lat else 0
            log.info("answered=%(answered)d pushed=%(pushed)d push_fail=%(push_fail)d dropped_late=%(late)d errors=%(errors)d" % self.stats
                     + f" latency p50={p50:.2f}s p95={p95:.2f}s watermark={self.watermark:%H:%M:%S}")

    def preload_seen(self, rt: RawTree) -> None:
        rows = rt.query(f"SELECT request_id::String AS rid FROM {self.team}.submissions "
                        "WHERE request_id::String IN (SELECT request_id::String FROM shop.requests "
                        "WHERE ts::DateTime64(3) > now() - INTERVAL 3 MINUTE)", timeout=20)
        now = time.time()
        for r in rows:
            self.seen[r["rid"]] = now
        log.info("preloaded %d already-answered request ids", len(rows))

    def takeover(self) -> None:
        """Stop the previous live process (if any) only now that this one is ready: no gap, minimal overlap."""
        pid_file = LOGS / "live.pid"
        if pid_file.exists() and not self.dry_run:
            try:
                old = int(pid_file.read_text().strip())
                if old != os.getpid():
                    os.kill(old, signal.SIGTERM)
                    log.info("took over from previous live process %d", old)
            except (ValueError, OSError) as e:
                log.info("no previous live process to stop (%s)", e)
        if not self.dry_run:
            pid_file.write_text(str(os.getpid()))

    def run(self) -> None:
        self.measure_offset(RawTree(timeout=10))
        self.build()
        self.takeover()
        threads = [threading.Thread(target=t, name=t.__name__, daemon=True)
                   for t in (self.pusher, self.stock, self.refresher, self.rebuilder, self.reporter)]
        threads += [threading.Thread(target=self.poller, args=(i * POLL_SLEEP / N_POLLERS,), name=f"poller{i}", daemon=True)
                    for i in range(N_POLLERS)]
        self.watermark = datetime.now(timezone.utc) - timedelta(seconds=3)
        try:
            self.preload_seen(RawTree(timeout=20))
        except Exception as e:
            log.warning("could not preload answered ids: %s", str(e)[:200])
        for t in threads:
            t.start()
        log.info("live runner started (dry_run=%s) arms=%s", self.dry_run, [(p.name, s) for p, s in self.arms])
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop.set()
