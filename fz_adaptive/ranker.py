"""Ranker: live store state + trained model + online corrections -> 10 product ids for one request.

Three layers, slowest to fastest:
  1. GBDT model  P(click) x P(buy | click)   - retrained every few minutes by learn.py on history + live feedback
  2. live features                            - prices, stock, new products (1.5 s), trends from shop.events (60 s)
  3. online correction (bandit)               - for every product and subcategory we track, with exponential forgetting,
     how many clicks/purchases the model EXPECTED from our own impressions vs. how many HAPPENED; the ratio rescales
     the score, so a product that suddenly sells better/worse than predicted moves within minutes.
One slot of some lists is used for exploration so the system keeps learning about products it would not show.
"""
from __future__ import annotations
import json, pickle, threading, time, os, zlib
from pathlib import Path
import numpy as np, pandas as pd, lightgbm as lgb
from features import Store, FEATS, FI, D

MODEL = D / "model.pkl"
POS = np.array([1, .59, .40, .355, .28, .22, .214, .19, .165, .153])  # examination by slot (click share in the logged data)
CAP = 12000
STREAM_START = 1794646800000  # Sat 10:00 CET: live events start here
DEFAULT = dict(bought_factor=0.05, half_life_min=90, k_item=6.0, k_sub=25.0, a_item=1.0, a_sub=1.0, explore=0.3, same_cat_only=True, buy_w=2.0, xcat_factor=1.0, max_per_sub=0, max_per_cat=0, ignore_rv=False)


class Ranker:
    EV_PAGE = 50000
    ARR = ["Csv", "Csb", "Cbv", "Cbb", "Cav", "Cab", "un", "ub", "slp", "slp2", "slpb"]

    def __init__(self):
        self.st = Store()
        self.cat_ts = 0
        # live cursor starts "now"; the backlog since the stream opened is back-filled slowly in the background
        # (carts & purchases first, then views) so it never competes with answering requests for bandwidth
        now = int(time.time() * 1000) - 5000
        self.ev_ts = now; self.ev_seen: set = set(); self.ev_lag = 0.0
        self.bf = {"phase": 0, "ts": STREAM_START, "end": now}
        self.bought: dict[str, set] = {}
        f = D / "user_bought.parquet"
        if f.exists():
            for u, lst in pd.read_parquet(f).itertuples(index=False): self.bought[u] = set(lst)
        self.lock = threading.Lock(); self.rng = np.random.default_rng()
        self.pending: dict[str, tuple] = {}
        # online correction state: expected vs observed (clicks + buy_w * purchases), per product and per subcategory
        self.E = np.zeros(CAP); self.O = np.zeros(CAP); self.Es = np.zeros(200); self.Os = np.zeros(200); self.decayed = time.time()
        self.fX = open(D / f"live_X{len(FEATS)}.f32", "ab"); self.fY = open(D / f"live_Y{len(FEATS)}.jsonl", "a")
        self.mtime = 0; self.version = "none"; self.load(); self.load_state()

    # ---- model ----------------------------------------------------------------------------------
    def load(self):
        m = pickle.load(open(MODEL, "rb"))
        self.models = {k: lgb.Booster(model_str=s) for k, s in m["models"].items()}
        self.cols = [FI[f] for f in m["feats"]]
        self.cfg = {**DEFAULT, **m.get("cfg", {})}; self.version = m["version"]
        self.mtime = os.path.getmtime(MODEL)

    def maybe_reload(self):
        if os.path.getmtime(MODEL) != self.mtime:
            self.load(); print(time.strftime("%H:%M:%S"), "reloaded model", self.version, self.cfg, flush=True)

    def predict(self, F: np.ndarray):
        X = F[:, self.cols]
        pc = self.models["click"].predict(X, num_threads=2)
        pb = pc * self.models["buy_given_click"].predict(X, num_threads=2)
        return pc, pb

    # ---- state ----------------------------------------------------------------------------------
    def apply_updates(self, rows: list[dict]):
        with self.lock:
            for r in rows:
                ch = r.pop("change"); t = r.pop("t")
                if ch == "new_product": self.st.new_products.add(r["product_id"])
                self.st.add_item(r)
                self.cat_ts = max(self.cat_ts, t)
            self.st.build()

    def add_events(self, rows: list[dict]):
        """Live organic events: update shopper profiles, carts and purchases (deduplicated; small overlap on the cursor)."""
        new = [r for r in rows if (r["u"], r["p"], r["e"], r["t"]) not in self.ev_seen]
        for k in range(0, len(new), 2000):
            with self.lock:
                for r in new[k:k + 2000]:
                    self.st.add_event(r["u"], r["p"], r["e"], r["t"] / 1000)
                    if r["e"] == "purchase": self.bought.setdefault(r["u"], set()).add(r["p"])
        if rows:
            tmax = rows[-1]["t"]; caught_up = len(rows) < self.EV_PAGE
            self.ev_seen = {k for k in self.ev_seen if k[3] > tmax - 6000} | {(r["u"], r["p"], r["e"], r["t"]) for r in rows if r["t"] > tmax - 6000}
            self.ev_ts = tmax - 3000 if caught_up else tmax
            self.ev_lag = time.time() - tmax / 1000
        return len(new)

    def add_backfill(self, rows: list[dict], page: int):
        for k in range(0, len(rows), 2000):
            with self.lock:
                for r in rows[k:k + 2000]:
                    self.st.add_event(r["u"], r["p"], r["e"], r["t"] / 1000)
                    if r["e"] == "purchase": self.bought.setdefault(r["u"], set()).add(r["p"])
        if len(rows) < page: self.bf["phase"] += 1; self.bf["ts"] = STREAM_START
        else: self.bf["ts"] = rows[-1]["t"]

    def save_state(self):
        """Persist everything learned from the stream so a restart resumes where it left off."""
        with self.lock:
            st = self.st; n = len(st.uidx)
            state = dict(ev_ts=self.ev_ts, bf=dict(self.bf), uidx=dict(st.uidx), ucart={u: dict(d) for u, d in st.ucart.items()}, bought={u: set(x) for u, x in self.bought.items()},
                         arrays={k: getattr(st, k)[:n].copy() for k in self.ARR}, E=self.E.copy(), O=self.O.copy(), Es=self.Es.copy(), Os=self.Os.copy())
        with open(D / "state.tmp", "wb") as fh:
            pickle.dump(state, fh, protocol=5); fh.flush(); os.fsync(fh.fileno())
        (D / "state.tmp").replace(D / "state.pkl")

    def load_state(self):
        f = D / "state.pkl"
        if not f.exists(): return
        try: s = pickle.load(open(f, "rb"))
        except Exception as e:   # a crash mid-write must never stop the server: start clean, the backfill rebuilds profiles
            print("state file unreadable, starting clean:", repr(e)[:100], flush=True); return
        st = self.st; n = len(s["uidx"])
        st.uidx = s["uidx"]; st.ucart = s["ucart"]; self.bought = s["bought"]; self.ev_ts = s["ev_ts"]; self.bf = s["bf"]
        for k, a in s["arrays"].items(): getattr(st, k)[:n] = a
        self.E, self.O, self.Es, self.Os = s["E"], s["O"], s["Es"], s["Os"]
        print("state restored: users", n, "event cursor", time.strftime("%H:%M:%S", time.localtime(self.ev_ts / 1000)), flush=True)

    def set_trends(self, rows: list[dict]):
        live = {r["p"]: (int(r["v"]), int(r["c"]), int(r["b"]), int(r["v30"]), int(r["b30"])) for r in rows}
        with self.lock: self.st.set_live(live)

    def add_feedback(self, rows: list[dict]):
        """Learn from our own impressions: update bought sets, the online correction, and the live training log."""
        now = time.time(); h = self.cfg["half_life_min"] * 60
        g = 0.5 ** ((now - self.decayed) / h); self.decayed = now
        self.E *= g; self.O *= g; self.Es *= g; self.Os *= g
        st = self.st; bw = self.cfg["buy_w"]
        for r in rows:
            pend = self.pending.pop(r["rid"], None)
            if pend is None: continue
            u, items, F, pc, pb, explored, mv = pend
            if r["purchased"]: self.bought.setdefault(u, set()).add(r["purchased"])
            if r["served_by"] != "team" or list(r["shown"]) != items: continue   # another answer was shown: not our impression
            ii = np.array([st.idx[p] for p in items])
            e = (pc + bw * pb) * POS
            self.E[ii] += e; np.add.at(self.Es, st.sub[ii], e)
            for p, w in ((r["clicked"], 1.0), (r["purchased"], bw)):
                if p in st.idx: self.O[st.idx[p]] += w; self.Os[st.sub[st.idx[p]]] += w
            self.fX.write(F.astype(np.float32).tobytes())
            self.fY.write(json.dumps({"rid": r["rid"], "t": r["t"], "u": u, "items": items, "c": items.index(r["clicked"]) if r["clicked"] in items else -1,
                                      "b": items.index(r["purchased"]) if r["purchased"] in items else -1, "x": explored, "mv": mv}) + "\n")
        self.fX.flush(); self.fY.flush()
        if len(self.pending) > 5000:
            for k in list(self.pending)[:2500]: del self.pending[k]

    def correction(self, c: np.ndarray) -> np.ndarray:
        cfg = self.cfg; g = (self.O.sum() + 50) / (self.E.sum() + 50)   # global calibration, so factors are relative
        fi = (self.O[c] + cfg["k_item"] * g) / (self.E[c] + cfg["k_item"]) / g
        s = self.st.sub[c]
        fs = (self.Os[s] + cfg["k_sub"] * g) / (self.Es[s] + cfg["k_sub"]) / g
        return fi ** cfg["a_item"] * fs ** cfg["a_sub"]

    def fallback(self) -> list[str]:
        st = self.st; order = np.argsort(-(st.pop_lb + 100 * st.active))[:10]
        return [st.ids[i] for i in order]

    # ---- ranking --------------------------------------------------------------------------------
    def recommend(self, req: dict) -> list[str]:
        cfg = self.cfg; req["mv"] = self.version
        if cfg.get("variants"):   # concurrent A/B test: requests are split by a hash of the request id
            name, over = cfg["variants"][zlib.crc32(req["rid"].encode()) % len(cfg["variants"])]
            cfg = {**cfg, **over}; req["mv"] = name
        # exploration mode for this request: 0 none, 1 = last slot sampled from ranks 11-40, 2 = last slot is the best
        # product OUTSIDE the browsed category (the logged data never shows those, so only live feedback can price them)
        mode = 0
        if self.rng.random() < cfg["explore"]: mode = 1 if self.rng.random() < 0.5 else 2
        with self.lock:
            st = self.st
            rv = [st.idx[p] for p in req["rv"] if p in st.idx]
            c = np.flatnonzero(st.active)
            restrict = bool(rv) and cfg["same_cat_only"]
            incat = (st.cat[c] == st.cat[rv[-1]]) if restrict else np.ones(len(c), bool)
            if incat.sum() < 30: incat[:] = True; restrict = False
            if restrict and mode != 2: c = c[incat]; incat = np.ones(len(c), bool)
            F = st.feats({**req, "rv": []} if cfg["ignore_rv"] else req, c, slot=0)
            ids = st.ids; corr = self.correction(c)
        pc, pb = self.predict(F)
        s = pb * corr
        if rv and cfg["xcat_factor"] != 1.0 and not cfg["ignore_rv"]:   # browsing one category: products from other categories are discounted
            s = np.where(F[:, FI["same_cat_last"]] == 0, s * cfg["xcat_factor"], s)
        for p in self.bought.get(req["u"], ()):   # already bought -> very unlikely to buy again
            i = st.idx.get(p)
            if i is not None:
                j = np.searchsorted(c, i)
                if j < len(c) and c[j] == i: s[j] *= cfg["bought_factor"]
        s_in = np.where(incat, s, -1.0)
        k = min(120, int(incat.sum()) - 1)
        top = np.argpartition(-s_in, k)[:k]; top = top[np.argsort(-s_in[top])]
        pick = list(top[:10]); explored = 0
        if cfg["max_per_sub"] or cfg["max_per_cat"]:
            # diversity: greedy pick with a cap per subcategory / category (similar products compete with each other)
            ms, mc = cfg["max_per_sub"] or 99, cfg["max_per_cat"] or 99
            ns: dict = {}; ncat: dict = {}; pick = []
            for i in top:
                a, b = int(st.sub[c[i]]), int(st.cat[c[i]])
                if ns.get(a, 0) >= ms or ncat.get(b, 0) >= mc: continue
                ns[a] = ns.get(a, 0) + 1; ncat[b] = ncat.get(b, 0) + 1; pick.append(int(i))
                if len(pick) == 10: break
            pick += [int(i) for i in top if int(i) not in pick][:10 - len(pick)]
        if mode == 1 and len(top) > 12:
            pool = np.array([i for i in top[:40] if i not in pick]); w = s[pool]; pick[9] = int(self.rng.choice(pool, p=w / w.sum())); explored = 1
        elif mode == 2 and restrict and (~incat).any():
            pick[9] = int(np.argmax(np.where(incat, -1.0, s))); explored = 2
        pick = np.array(pick)
        Fp = F[pick].copy(); Fp[:, FI["slot"]] = np.arange(10)
        items = [ids[c[i]] for i in pick]
        self.pending[req["rid"]] = (req["u"], items, Fp, pc[pick], pb[pick], explored, req["mv"])
        return items
