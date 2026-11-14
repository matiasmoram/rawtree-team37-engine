"""Live serving loop: poll shop.requests -> rank -> insert into team_NN.submissions.

Design (the network round-trip is the scarce resource, so everything is concurrent):
  * N poll threads, staggered, each with its own HTTP connection, read the last few seconds of requests
  * each new request is ranked immediately (numpy, ~1 ms) and queued
  * M push threads drain the queue and insert batches
  * background threads keep the store state fresh: catalogue changes, live purchases, live trends, own feedback
Everything it sees (requests, feedback) is also appended to data/live_*.jsonl so we can retrain on it.

    python serve.py
"""
from __future__ import annotations
import json, os, queue, sys, threading, time, traceback
from pathlib import Path
import requests
from ranker import Ranker

ROOT = Path(__file__).parent
for line in (ROOT / ".env").read_text().splitlines():
    k, _, v = line.partition("="); os.environ.setdefault(k.strip(), v.strip())
API = "https://api.rawtree.com"; TEAM = os.environ["TEAM_ID"]
HDR = {"Authorization": f"Bearer {os.environ['RAWTREE_API_KEY']}"}
N_POLL, N_PUSH, POLL_GAP = 4, 6, 0.15
tl = threading.local()


def http() -> requests.Session:
    if not hasattr(tl, "s"):
        tl.s = requests.Session(); tl.s.headers.update(HDR)
    return tl.s


def q(sql: str, timeout: float = 8) -> list[dict]:
    try:
        r = http().post(f"{API}/v1/query", json={"sql": sql}, timeout=timeout)
    except Exception:
        del tl.s  # drop a stuck connection
        raise
    if r.status_code != 200:
        raise RuntimeError(r.text[:300])
    return r.json()["data"]


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


REQ_SQL = """SELECT request_id::String rid, toUnixTimestamp64Milli(ts::DateTime64(3)) t, user_id::String u,
 is_new_user::Bool nu, context.device::String d, context.page::String pg, context.region::String r,
 arrayMap(x->x.product_id::String, recent_views::Array(Dynamic)) rv,
 toUnixTimestamp64Milli(now64(3)) now
FROM shop.requests WHERE ts::DateTime64(3) > now64(3) - INTERVAL 4 SECOND"""


class Server:
    def __init__(self):
        self.ranker = Ranker()
        self.seen: dict[str, float] = {}
        self.probe_s = {"other_host": requests.Session(), "api_noop": requests.Session()}
        self.inflight: dict[str, list] = {}
        self.done: dict[str, float] = {}   # request -> time its answer was accepted
        self.users: dict[str, str] = {}  # request -> user, to learn who bought what from our feedback
        self.lock = threading.Lock()
        self.out: queue.Queue = queue.Queue()
        self.skew = 0.0  # server clock - local clock, seconds
        self.stats = {"polled": 0, "pushed": 0, "late": 0, "err": 0, "lat": []}
        self.req_log = open(ROOT / "data" / "live_requests.jsonl", "a")
        self.fb_log = open(ROOT / "data" / "live_feedback.jsonl", "a")

    # ---- request path -------------------------------------------------------------------------
    def poll_loop(self, k: int):
        time.sleep(k * 0.25)
        while True:
            try:
                t0 = time.time()
                rows = q(REQ_SQL, timeout=(2.0, 3.5))
                t1 = time.time()
                if rows:
                    self.skew = 0.9 * self.skew + 0.1 * (rows[0]["now"] / 1000 - (t0 + t1) / 2) if self.skew else rows[0]["now"] / 1000 - (t0 + t1) / 2
                fresh = []
                with self.lock:
                    for r in rows:
                        if r["rid"] not in self.seen:
                            self.seen[r["rid"]] = t1; fresh.append(r)
                self.stats.setdefault("poll_rt", []).append(t1 - t0)
                for r in fresh:
                    r["age_seen"] = t1 + self.skew - r["t"] / 1000
                    try:
                        tr = time.time(); items = self.ranker.recommend(r); self.stats.setdefault("rank", []).append(time.time() - tr)
                        self.stats.setdefault("age", []).append(r["age_seen"])
                    except Exception:
                        log("rank error", traceback.format_exc()[-400:]); items = self.ranker.fallback()
                    r["items"] = items; r.setdefault("mv", self.ranker.version)
                    self.out.put((r, items))
                if fresh:
                    self.stats["polled"] += len(fresh)
                    self.req_log.write("".join(json.dumps(r) + "\n" for r in fresh)); self.req_log.flush()
            except Exception as e:
                self.stats["err"] += 1
            time.sleep(POLL_GAP)

    def push_loop(self):
        """Hedged pushes: short timeouts, and a failed batch goes straight back on the queue so another thread
        (another connection) retries it while there is still time. A duplicate insert is harmless: one answer counts."""
        while True:
            batch = [self.out.get()]
            while not self.out.empty() and len(batch) < 200:
                batch.append(self.out.get_nowait())
            now = time.time() + self.skew
            batch = [x for x in batch if now - x[0]["t"] / 1000 < 3.0] or batch[:0]
            if not batch: continue
            batch = [x for x in batch if x[0]["rid"] not in self.done]
            if not batch: continue
            body = [{"request_id": r["rid"], "items": items, "model_version": r["mv"]} for r, items in batch]
            t_send = time.time()
            for x in batch: self.inflight.setdefault(x[0]["rid"], [x, t_send, 0])
            try:
                resp = http().post(f"{API}/v1/tables/submissions", params={"database": TEAM}, json=body, timeout=(2.0, 3.0))
                resp.raise_for_status()
                done = time.time() + self.skew
                with self.lock:
                    fresh = [(r, i) for r, i in batch if r["rid"] not in self.done]
                    for r, _ in fresh: self.done[r["rid"]] = done
                for r, _ in batch: self.inflight.pop(r["rid"], None)
                self.stats.setdefault("push_rt", []).append(time.time() - t_send)
                lats = [done - r["t"] / 1000 for r, _ in fresh]
                self.stats["pushed"] += len(fresh); self.stats["late"] += sum(l > 3 for l in lats); self.stats["lat"] += lats
            except Exception as e:
                self.stats["err"] += 1
                if hasattr(tl, "s"): del tl.s
                for x in batch:
                    if x[0]["rid"] not in self.done: self.out.put(x)

    def hedge_loop(self):
        """If an insert has been in flight for more than 0.7 s, send the same answer again on another connection
        (at most twice). Slow or stalled connections are the main cause of late answers on this network."""
        while True:
            time.sleep(0.15)
            now = time.time()
            for rid, v in list(self.inflight.items()):
                x, t_send, n = v
                if rid in self.done or now + self.skew - x[0]["t"] / 1000 > 3.0: self.inflight.pop(rid, None); continue
                if now - t_send > 0.7 and n < 2:
                    v[1] = now; v[2] = n + 1; self.out.put(x); self.stats["hedged"] = self.stats.get("hedged", 0) + 1

    def probe(self):
        """Diagnosis only: time one request to a different host and one no-op to the API. If both slow down together
        the local network is the cause; if only the API slows down, it is the API (or our own load on it)."""
        for name, url in (("other_host", "https://datathon.rawtree.dev/favicon.svg"), ("api_noop", f"{API}/")):
            t = time.time()
            try: self.probe_s[name].get(url, timeout=6)
            except Exception: pass
            self.stats.setdefault("probe_" + name, []).append(time.time() - t)

    # ---- state refreshers ---------------------------------------------------------------------
    def every(self, seconds: float, fn, name: str):
        def loop():
            while True:
                try: fn()
                except Exception as e: log(name, "error", type(e).__name__, str(e)[:160])
                time.sleep(seconds)
        threading.Thread(target=loop, daemon=True, name=name).start()

    def refresh_catalog(self):
        rows = q(f"""SELECT product_id::String product_id, category::String category, subcategory::String subcategory, brand::String brand,
            price_eur::Float64 price_eur, description::String description, is_active::Bool is_active, change::String change,
            toUnixTimestamp64Milli(ts::DateTime64(3)) t
            FROM shop.catalog_updates WHERE ts::DateTime64(3) > fromUnixTimestamp64Milli({self.ranker.cat_ts}) ORDER BY t""", timeout=20)
        if rows:
            self.ranker.apply_updates(rows); log("catalog updates", len(rows))

    def refresh_events(self):
        """Stream shop.events (views, carts, purchases) into the per-shopper profiles; pages through the backlog on start."""
        r = self.ranker
        rows = q(f"""SELECT user_id::String u, product_id::String p, event_type::String e, toUnixTimestamp64Milli(ts::DateTime64(3)) t
            FROM shop.events WHERE ts::DateTime64(3) > fromUnixTimestamp64Milli({r.ev_ts}) ORDER BY t LIMIT {r.EV_PAGE}""", timeout=60)
        if rows:
            n = r.add_events(rows); self.stats["events"] = self.stats.get("events", 0) + n

    def refresh_backfill(self):
        """Slowly replay the events from before this process started (small pages: bandwidth belongs to the request path)."""
        r = self.ranker; bf = r.bf
        if bf["phase"] > 1 or self.stats["err"] > 0 or self.stats["late"] > 0: return   # yield bandwidth when the network struggles
        page = 15000 if bf["phase"] == 0 else 3000
        cond = "event_type != 'view'" if bf["phase"] == 0 else "event_type = 'view'"
        rows = q(f"""SELECT user_id::String u, product_id::String p, event_type::String e, toUnixTimestamp64Milli(ts::DateTime64(3)) t
            FROM shop.events WHERE {cond} AND ts::DateTime64(3) > fromUnixTimestamp64Milli({bf['ts']}) AND ts::DateTime64(3) <= fromUnixTimestamp64Milli({bf['end']})
            ORDER BY t LIMIT {page}""", timeout=60)
        r.add_backfill(rows, page); self.stats["backfill"] = self.stats.get("backfill", 0) + len(rows)

    def refresh_trends(self):
        rows = q("""SELECT product_id::String p, countIf(event_type='view') v, countIf(event_type='add_to_cart') c, countIf(event_type='purchase') b,
            countIf(event_type='view' AND ts::DateTime64(3) > now64(3) - INTERVAL 30 MINUTE) v30,
            countIf(event_type='purchase' AND ts::DateTime64(3) > now64(3) - INTERVAL 30 MINUTE) b30
            FROM shop.events WHERE ts::DateTime64(3) > now64(3) - INTERVAL 3 HOUR GROUP BY p""", timeout=30)
        if rows: self.ranker.set_trends(rows)

    def refresh_feedback(self):
        rows = q(f"""SELECT request_id::String rid, toUnixTimestamp64Milli(ts::DateTime64(3)) t, shown, served_by::String served_by,
            fallback_reason::String fr, latency_ms::Float64 lat, clicked::String clicked, purchased::String purchased, revenue_eur::Float64 rev
            FROM {TEAM}.feedback WHERE request_id != '__init__' AND ts::DateTime64(3) > fromUnixTimestamp64Milli({self.fb_ts}) ORDER BY t LIMIT 20000""", timeout=30)
        if not rows: return
        self.fb_ts = rows[-1]["t"]
        self.fb_log.write("".join(json.dumps(r) + "\n" for r in rows)); self.fb_log.flush()
        self.ranker.add_feedback(rows)
        n = len(rows); team = [r for r in rows if r["served_by"] == "team"]
        reasons = {}
        for r in rows:
            if r["served_by"] != "team": reasons[r["fr"]] = reasons.get(r["fr"], 0) + 1
        self.fb_hist = (self.fb_hist + [(r["served_by"] == "team", r["clicked"] != "", r["purchased"] != "") for r in rows])[-6000:]
        h = self.fb_hist; ht = [x for x in h if x[0]] or [(1, 0, 0)]
        log(f"feedback +{n} served={len(team)/n:.0%} {reasons} | last {len(h)}: served={len(ht)/len(h):.1%} "
            f"ctr={sum(x[1] for x in ht)/len(ht):.2%} conv={sum(x[2] for x in ht)/len(ht):.2%}")

    def report(self):
        s = self.stats; lat = sorted(s["lat"]) or [0]
        log(f"polled={s['polled']} pushed={s['pushed']} late={s['late']} err={s['err']} "
            f"latency p50={lat[len(lat)//2]:.2f}s p95={lat[int(len(lat)*.95)]:.2f}s max={lat[-1]:.2f}s | events +{s.get('events', 0)} lag={self.ranker.ev_lag:.0f}s backfill +{s.get('backfill', 0)} phase={self.ranker.bf['phase']} users={len(self.ranker.st.uidx)}")
        med = lambda k: (sorted(s.get(k) or [0])[len(s.get(k) or [0]) // 2])
        log(f"   breakdown: poll round-trip p50={med('poll_rt'):.2f}s polls={len(s.get('poll_rt', []))} | request age when first seen p50={med('age'):.2f}s | push round-trip p50={med('push_rt'):.2f}s hedged={s.get('hedged', 0)} | probe other-host p50={med('probe_other_host'):.2f}s api-noop p50={med('probe_api_noop'):.2f}s | rank p50={med('rank')*1000:.0f}ms max={max(s.get('rank') or [0])*1000:.0f}ms")
        self.stats = {"polled": 0, "pushed": 0, "late": 0, "err": 0, "lat": []}
        now = time.time()
        with self.lock:
            for k in [k for k, v in self.seen.items() if now - v > 60]: del self.seen[k]
            for k in [k for k, v in self.done.items() if now - v > 60]: del self.done[k]
            if len(self.users) > 20000:
                for k in list(self.users)[:10000]: del self.users[k]

    def run(self):
        self.fb_ts = int((time.time() - 20) * 1000); self.fb_hist = []
        self.refresh_catalog()
        for name, fn in [("trends", self.refresh_trends)]:
            try: fn()
            except Exception as e: log("initial", name, "failed", str(e)[:200])
        self.every(1.5, self.refresh_catalog, "catalog")
        self.every(1.0, self.refresh_events, "events")
        self.every(5, self.refresh_backfill, "backfill")
        self.every(60, self.ranker.save_state, "save")
        self.every(60, self.refresh_trends, "trends")
        self.every(10, self.refresh_feedback, "feedback")
        self.every(30, self.report, "report")
        self.every(3, self.probe, "probe")
        self.every(20, self.ranker.maybe_reload, "reload")
        for k in range(N_PUSH): threading.Thread(target=self.push_loop, daemon=True).start()
        threading.Thread(target=self.hedge_loop, daemon=True).start()
        for k in range(N_POLL): threading.Thread(target=self.poll_loop, args=(k,), daemon=True).start()
        log("serving as", self.ranker.version)
        while True: time.sleep(3600)


if __name__ == "__main__":
    Server().run()
