"""Shared feature code: the SAME function builds features offline (training on the history / live feedback)
and online (ranking the catalogue for one request), so there is no train/serve skew.

A request is (user, device, region, page, recent_views). For a set of candidate products we build one row each:
  item      : price, popularity (organic purchases per view), discount vs. starting price, is-new
  session   : relation to the recently viewed products (same product / subcategory / brand / category / attributes / price)
  user      : long-term taste from 60 days of organic events (share of views & purchases in the item's subcategory,
              category, brand, attributes; price level)
  context   : page, device, and how well the item's subcategory converts for this device x region
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd

D = Path(__file__).parent / "data"
ATTRS = ["a sporty style", "a family-size format", "a luxury feel", "organic ingredients", "a minimalist design", "built for professionals",
         "wireless connectivity", "bold colours", "designed for kids", "premium materials", "smart app control", "whisper-quiet operation",
         "a vintage look", "made from recycled materials", "great value for money", "a travel-ready build", "extra durability",
         "a waterproof shell", "a handmade finish", "lightweight"]
PAGES = {"home": 0, "category": 1, "product": 2}; DEVS = {"web": 0, "ios": 1, "android": 2}
FEATS = ["lprice", "lprice_rel_sub", "pop_conv", "pop_lv", "pop_lb", "pop_cart", "pop_lb_rel_sub", "ldisc", "is_new",
         "n_rv", "in_rv_w", "is_last", "same_sub_last", "same_brand_last", "same_cat_last", "frac_sub_rv", "frac_brand_rv", "frac_cat_rv",
         "attr_last", "attr_rv", "dprice_last", "dprice_rv",
         "has_user", "u_sub_v", "u_sub_b", "u_cat_v", "u_cat_b", "u_brand_v", "u_brand_b", "u_attr_v", "u_attr_b",
         "u_ln", "u_lb", "dprice_u", "zprice_u", "dprice_ub", "page", "device", "ctx_lift", "slot",
         # live market signals (0 in the historical log, filled from shop.events while serving)
         "tr_item", "tr_sub", "live_conv_d", "u_cart", "u_cart_age"]
FI = {f: i for i, f in enumerate(FEATS)}
PAD = 8  # spare columns for subcategories / brands that appear during the event


class Store:
    def __init__(self):
        cat = pd.read_parquet(D / "catalog.parquet")
        self.SUBS = sorted(cat.subcategory.unique()); self.CATS = sorted(cat.category.unique()); self.BRANDS = sorted(cat.brand.unique())
        self.si = {s: i for i, s in enumerate(self.SUBS)}; self.ci = {s: i for i, s in enumerate(self.CATS)}; self.bi = {s: i for i, s in enumerate(self.BRANDS)}
        self.ids: list[str] = []; self.idx: dict[str, int] = {}; self.rows: list[dict] = []
        self.base_price: dict[str, float] = {}; self.new_products: set[str] = set()
        for r in cat.to_dict("records"):
            self.add_item(r); self.base_price[r["product_id"]] = float(r["price_eur"])
        ps = pd.read_parquet(D / "prod_stats.parquet")
        self.hist = {p: (v, c, b) for p, v, c, b in zip(ps.p, ps.v, ps.c, ps.b)}
        self.live: dict[str, tuple] = {}   # product -> (views 3h, carts 3h, purchases 3h, views 30m, purchases 30m)
        self._users(); self._ctx()
        self.build()

    # ---- catalogue ------------------------------------------------------------------------------
    def add_item(self, r: dict):
        p = r["product_id"]
        if p in self.idx: self.rows[self.idx[p]].update(r)
        else:
            self.idx[p] = len(self.ids); self.ids.append(p); self.rows.append(dict(r))

    def _code(self, table: dict, key: str, cap: int) -> int:
        if key not in table and len(table) < cap: table[key] = len(table)
        return table.get(key, cap - 1)

    def build(self):
        rows = self.rows; n = self.n = len(rows)
        S, C, B = len(self.SUBS) + PAD, len(self.CATS) + PAD, len(self.BRANDS) + PAD
        self.sub = np.array([self._code(self.si, r["subcategory"], S) for r in rows]); self.cat = np.array([self._code(self.ci, r["category"], C) for r in rows])
        self.brand = np.array([self._code(self.bi, r["brand"], B) for r in rows])
        self.sub2cat = np.zeros(S, dtype=int); self.sub2cat[self.sub] = self.cat
        self.price = np.array([float(r["price_eur"]) for r in rows]); self.lprice = np.log(self.price).astype(np.float32)
        self.active = np.array([bool(r["is_active"]) for r in rows])
        self.A = np.array([[a in r["description"] for a in ATTRS] for r in rows], dtype=np.float32)
        self.is_new = np.array([p in self.new_products for p in self.ids], dtype=np.float32)
        base = np.array([self.base_price.get(p, np.nan) for p in self.ids]); self.ldisc = np.round(np.nan_to_num(np.log(self.price / base)), 4).astype(np.float32)  # log(current price / starting price)
        sub_mean = np.bincount(self.sub, self.lprice, S) / np.maximum(np.bincount(self.sub, minlength=S), 1)
        self.lprice_rel = (self.lprice - sub_mean[self.sub]).astype(np.float32)
        self.build_pop()

    def build_pop(self):
        """Long-run popularity from 60 days of organic events (products never seen get their subcategory's average),
        plus live trend features from the last 3 h / 30 min of shop.events."""
        n = self.n; v = np.full(n, np.nan); c = np.zeros(n); b = np.zeros(n); new_live = {}
        hist_v = sum(h[0] for h in self.hist.values()); live_v = sum(l[0] for p, l in self.live.items() if p in self.hist)
        self.live_scale = hist_v / live_v if live_v > 1000 else 0.0
        for p, i in self.idx.items():
            h = self.hist.get(p)
            if h is not None: v[i], c[i], b[i] = h
            elif p in self.live and self.live_scale > 0:
                # product added during the event: no history, so its popularity comes from the live window,
                # scaled to history-equivalent volume and shrunk towards its subcategory (filled in below) while data is thin
                l = self.live[p]; new_live[i] = (l[0] * self.live_scale, l[1] * self.live_scale, l[2] * self.live_scale, l[0])
        S = len(self.SUBS) + PAD
        known = ~np.isnan(v); cnt = np.maximum(np.bincount(self.sub[known], minlength=S), 1)
        for arr in (v, c, b):
            m = np.bincount(self.sub[known], arr[known], S) / cnt
            arr[~known] = m[self.sub[~known]]
        for i, (lv, lc, lb, raw) in new_live.items():
            w = raw / (raw + 50.0)   # trust the live estimate once the product has ~50+ live views
            v[i] = w * lv + (1 - w) * v[i]; c[i] = w * lc + (1 - w) * c[i]; b[i] = w * lb + (1 - w) * b[i]
        self.pop_conv = np.log((b + 1) / (v + 20)).astype(np.float32); self.pop_lv = np.log1p(v).astype(np.float32)
        self.pop_lb = np.log1p(b).astype(np.float32); self.pop_cart = np.log((c + 1) / (v + 20)).astype(np.float32)
        sm = np.bincount(self.sub, self.pop_lb, S) / np.maximum(np.bincount(self.sub, minlength=S), 1)
        self.pop_lb_rel = (self.pop_lb - sm[self.sub]).astype(np.float32)
        self.tr_item = np.zeros(n, dtype=np.float32); self.tr_sub = np.zeros(n, dtype=np.float32); self.live_conv_d = np.zeros(n, dtype=np.float32)
        if self.live:
            v3 = np.zeros(n); b3 = np.zeros(n); v30 = np.zeros(n)
            for p, l in self.live.items():
                i = self.idx.get(p)
                if i is not None: v3[i], b3[i], v30[i] = l[0], l[2], l[3]
            share = v / v.sum()                                   # long-run share of views
            exp30 = share * v30.sum()                             # views expected in 30 min if nothing changed
            self.tr_item = np.log((v30 + 5) / (exp30 + 5)).astype(np.float32)          # >0: product is trending up
            s30 = np.bincount(self.sub, v30, S); e30 = np.bincount(self.sub, exp30, S)
            self.tr_sub = np.log((s30 + 20) / (e30 + 20))[self.sub].astype(np.float32)  # >0: subcategory is trending up
            rate = (b + 1) / (v + 20)
            self.live_conv_d = (np.log((b3 + 20 * rate) / (v3 + 20)) - np.log(rate)).astype(np.float32)  # live vs long-run conversion

    def set_live(self, live: dict):
        self.live = live
        self.build_pop()

    # ---- users (updatable: counts from 60 days of history + every live event) ---------------------
    def _users(self):
        st = pd.read_parquet(D / "user_stats.parquet")
        self.uidx = {u: i for i, u in enumerate(st.u)}; U0 = len(st); U = self.ucap = U0 + 150000
        S, B, K = len(self.SUBS) + PAD, len(self.BRANDS) + PAD, len(ATTRS)
        z = lambda k: np.zeros((U, k), np.float32)
        self.Csv, self.Csb, self.Cbv, self.Cbb, self.Cav, self.Cab = z(S), z(S), z(B), z(B), z(K), z(K)
        self.un = np.zeros(U, np.float32); self.ub = np.zeros(U, np.float32)           # events, purchases
        self.slp = np.zeros(U, np.float32); self.slp2 = np.zeros(U, np.float32); self.slpb = np.zeros(U, np.float32)
        n = st.n.values.astype(np.float32); nb = st.b.values.astype(np.float32); lp = st.lp.values; sp = st.sp.fillna(0.9).values
        self.un[:U0] = n; self.ub[:U0] = nb; self.slp[:U0] = lp * n; self.slp2[:U0] = (sp ** 2 + lp ** 2) * n; self.slpb[:U0] = np.nan_to_num(st.lpb.values) * nb
        us = pd.read_parquet(D / "user_sub.parquet"); ui = us.u.map(self.uidx).values; sj = us["sub"].map(self.si).values
        self.Csv[ui, sj] = us.v.values; self.Csb[ui, sj] = us.b.values
        fs = sorted(D.glob("user_brand_*.parquet"))
        ub = pd.concat([pd.read_parquet(f) for f in fs]); ui = ub.u.map(self.uidx).values; bj = ub.br.map(self.bi).values
        self.Cbv[ui, bj] = ub.v.values; self.Cbb[ui, bj] = ub.b.values
        ua = pd.read_parquet(D / "user_attr.parquet"); ui = ua.u.map(self.uidx).values
        self.Cav[ui] = ua[[f"v{i}" for i in range(K)]].values; self.Cab[ui] = ua[[f"b{i}" for i in range(K)]].values
        # population priors: a shopper with few events is shrunk towards the average shopper
        nrm = lambda x: (x / x.sum()).astype(np.float32)
        self.g = dict(sv=nrm(self.Csv[:U0].sum(0) + 1), sb=nrm(self.Csb[:U0].sum(0) + 1), bv=nrm(self.Cbv[:U0].sum(0) + 1), bb=nrm(self.Cbb[:U0].sum(0) + 1),
                      av=nrm(self.Cav[:U0].sum(0) + 1), ab=nrm(self.Cab[:U0].sum(0) + 1))
        self.g_lp = float(self.slp[:U0].sum() / n.sum()); self.g_lp2 = float(self.slp2[:U0].sum() / n.sum()); self.g_lpb = float(self.slpb[:U0].sum() / nb.sum())
        # products each shopper added to cart: user -> {product: first cart time (s)}
        self.ucart: dict[str, dict[str, float]] = {}
        for f in sorted(D.glob("user_cart_*.parquet")):
            d = pd.read_parquet(f)
            for u, p, tc in zip(d.u, d.p, d.tc): self.ucart.setdefault(u, {})[p] = float(tc)

    def add_event(self, u: str, p: str, e: str, t: float):
        """One live organic event (view / add_to_cart / purchase) updates the shopper's profile immediately."""
        i = self.idx.get(p)
        if i is None: return
        k = self.uidx.get(u)
        if k is None:
            if len(self.uidx) >= self.ucap: return
            k = self.uidx[u] = len(self.uidx)
        lp = self.lprice[i]
        self.un[k] += 1; self.slp[k] += lp; self.slp2[k] += lp * lp
        if e == "view":
            self.Csv[k, self.sub[i]] += 1; self.Cbv[k, self.brand[i]] += 1; self.Cav[k] += self.A[i]
        elif e == "purchase":
            self.ub[k] += 1; self.slpb[k] += lp
            self.Csb[k, self.sub[i]] += 1; self.Cbb[k, self.brand[i]] += 1; self.Cab[k] += self.A[i]
        elif e == "add_to_cart":
            d = self.ucart.setdefault(u, {}); d[p] = min(t, d.get(p, t))

    def _ctx(self):
        """Purchases per view for device x region x subcategory, relative to the subcategory average (log lift)."""
        cs = pd.read_parquet(D / "ctx_stats.parquet")
        tot = cs.groupby("sub")[["v", "b"]].sum()
        rate = np.log((cs.b + 5 * (tot.b / tot.v).reindex(cs["sub"]).values) / (cs.v + 5)) - np.log((tot.b / tot.v).reindex(cs["sub"]).values)
        self.ctx = {(d, r, self.si[s]): x for d, r, s, x in zip(cs.d, cs.r, cs["sub"], rate)}

    # ---- features ---------------------------------------------------------------------------------
    def feats(self, req: dict, c: np.ndarray, slot=0, use_user: bool = True) -> np.ndarray:
        """Feature matrix [len(c), len(FEATS)] for candidate item indices c."""
        F = np.full((len(c), len(FEATS)), np.nan, dtype=np.float32)
        sub, cat, brand, lp = self.sub[c], self.cat[c], self.brand[c], self.lprice[c]
        F[:, 0] = lp; F[:, 1] = self.lprice_rel[c]; F[:, 2] = self.pop_conv[c]; F[:, 3] = self.pop_lv[c]; F[:, 4] = self.pop_lb[c]
        F[:, 5] = self.pop_cart[c]; F[:, 6] = self.pop_lb_rel[c]; F[:, 7] = self.ldisc[c]; F[:, 8] = self.is_new[c]
        rv = [self.idx[p] for p in req["rv"] if p in self.idx]
        F[:, 9] = len(rv)
        if rv:
            rva = np.array(rv); last = rv[-1]
            w = np.zeros(self.n, dtype=np.float32)
            for k, i in enumerate(reversed(rv)): w[i] += 0.8 ** k
            F[:, 10] = w[c]; F[:, 11] = c == last
            F[:, 12] = sub == self.sub[last]; F[:, 13] = brand == self.brand[last]; F[:, 14] = cat == self.cat[last]
            m = len(rv)
            F[:, 15] = np.bincount(self.sub[rva], minlength=len(self.SUBS) + PAD)[sub] / m
            F[:, 16] = np.bincount(self.brand[rva], minlength=len(self.BRANDS) + PAD)[brand] / m
            F[:, 17] = np.bincount(self.cat[rva], minlength=len(self.CATS) + PAD)[cat] / m
            A = self.A[c]
            F[:, 18] = A @ self.A[last]; F[:, 19] = A @ self.A[rva].mean(0)
            F[:, 20] = lp - self.lprice[last]; F[:, 21] = lp - self.lprice[rva].mean()
        else:
            F[:, 10:20] = 0
        u = self.uidx.get(req["u"]) if use_user else None
        F[:, 22] = u is not None
        if u is not None:
            g = self.g; MV, MB, MP = 20.0, 5.0, 10.0   # prior strength (pseudo-events)
            sv, sb = self.Csv[u], self.Csb[u]; nv, nb = sv.sum(), sb.sum()
            F[:, 23] = (sv[sub] + MV * g["sv"][sub]) / (nv + MV); F[:, 24] = (sb[sub] + MB * g["sb"][sub]) / (nb + MB)
            nc = len(self.CATS) + PAD
            cv = np.bincount(self.sub2cat, sv + MV * g["sv"], nc) / (nv + MV); cb = np.bincount(self.sub2cat, sb + MB * g["sb"], nc) / (nb + MB)
            F[:, 25] = cv[cat]; F[:, 26] = cb[cat]
            F[:, 27] = (self.Cbv[u, brand] + MV * g["bv"][brand]) / (nv + MV); F[:, 28] = (self.Cbb[u, brand] + MB * g["bb"][brand]) / (nb + MB)
            av = (self.Cav[u] + 2 * MV * g["av"]) / (self.Cav[u].sum() + 2 * MV); ab = (self.Cab[u] + 2 * MB * g["ab"]) / (self.Cab[u].sum() + 2 * MB)
            A = self.A[c]; F[:, 29] = A @ av; F[:, 30] = A @ ab
            n, b = self.un[u], self.ub[u]
            F[:, 31] = np.log1p(n); F[:, 32] = np.log1p(b)
            ulp = (self.slp[u] + MP * self.g_lp) / (n + MP); ulp2 = (self.slp2[u] + MP * self.g_lp2) / (n + MP)
            usp = max(float(np.sqrt(max(ulp2 - ulp * ulp, 0.0))), 0.3); ulpb = (self.slpb[u] + MB * self.g_lpb) / (b + MB)
            F[:, 33] = lp - ulp; F[:, 34] = (lp - ulp) / usp; F[:, 35] = lp - ulpb
        F[:, 36] = PAGES.get(req["pg"], 0); F[:, 37] = DEVS.get(req["d"], 0)
        d, r = req["d"], req["r"]
        F[:, 38] = [self.ctx.get((d, r, s), 0.0) for s in sub] if len(c) <= 64 else self._ctx_vec(d, r)[sub]
        F[:, 39] = slot
        F[:, 40] = self.tr_item[c]; F[:, 41] = self.tr_sub[c]; F[:, 42] = self.live_conv_d[c]
        # products this shopper put in the cart before this request (strongest single signal in the history)
        F[:, 43] = 0; F[:, 44] = 0
        cart = self.ucart.get(req["u"]) if use_user else None
        if cart:
            t = req["t"] / 1000
            pos = {int(x): j for j, x in enumerate(c)} if len(c) <= 64 else None
            for p, tc in cart.items():
                i = self.idx.get(p)
                if i is None or tc >= t: continue
                if pos is not None: j = pos.get(i, -1)
                else:
                    j = int(np.searchsorted(c, i)); j = j if j < len(c) and c[j] == i else -1
                if j >= 0: F[j, 43] = 1; F[j, 44] = np.log1p((t - tc) / 3600)
        return F

    def _ctx_vec(self, d, r):
        key = (d, r)
        if not hasattr(self, "_ctxc"): self._ctxc = {}
        if key not in self._ctxc:
            self._ctxc[key] = np.array([self.ctx.get((d, r, s), 0.0) for s in range(len(self.SUBS) + PAD)], dtype=np.float32)
        return self._ctxc[key]
