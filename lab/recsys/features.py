"""Feature store: everything known *before* a cutoff, in fast in-memory arrays.

Two modes, so no evaluation ever sees the future:
  * "offline": history before CUT (2026-11-07). Used to train policies and score the last-7-days test.
  * "live":    all history + live shop.events before the live test window. Used on live requests.

`pair_features(reqs, req_idx, item_idx, slot)` builds one feature row per (request, item, slot).
The simulator and the learned policy both use it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import scipy.sparse as sp

from . import data as D

PAGES = {"home": 0, "product": 1, "category": 2}
DEVICES = {"web": 0, "ios": 1, "android": 2}


def _field(x, key, default=None):
    if isinstance(x, dict):
        return x.get(key, default)
    return default


@dataclass
class Requests:
    """A batch of requests in array form (one row per request)."""
    df: pd.DataFrame
    user: np.ndarray            # user index or -1
    page: np.ndarray
    device: np.ndarray
    region: np.ndarray
    views: list[list[int]]      # item indices of recent views, oldest -> newest
    last_item: np.ndarray       # -1 if no views
    sess_cat: np.ndarray        # N x n_cat decayed counts of recent views per category
    sess_sub: np.ndarray        # N x n_sub
    RV: sp.csr_matrix           # N x n_items decayed recent views
    is_new: np.ndarray
    RVCV: sp.csr_matrix = None  # N x n_items co-view score of each item with the session's views


@dataclass
class Store:
    mode: str
    items: pd.DataFrame                     # index = item idx; product_id, category, subcategory, price, active, cat, sub, new
    pid2i: dict[str, int]
    cats: list[str]
    subs: list[str]
    regions: dict[str, int]
    u2i: dict[str, int]
    U_v: np.ndarray                          # users x cats
    U_c: np.ndarray
    U_p: np.ndarray
    U_sub: sp.csr_matrix                     # users x subs (views + 3*actions)
    U_logprice: np.ndarray                   # median log price of user purchases (nan if none)
    bought: dict[int, set[int]]
    I_v: np.ndarray                          # items
    I_c: np.ndarray
    I_p: np.ndarray
    I_trend: np.ndarray                      # live: recent purchases share vs history (1 in offline)
    CV: sp.csr_matrix                        # item x item co-view (row-normalised)
    ctx_cat: dict[tuple[int, int], np.ndarray]
    cat_pop: np.ndarray                      # cats: global purchase share
    extra: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ build
    @classmethod
    def build(cls, mode: str = "offline", cold_start: bool = False) -> "Store":
        assert mode in ("offline", "live")
        live = mode == "live"
        cat = D.pull("catalog")
        upd = D.pull("catalog_updates")
        upd["ts"] = pd.to_datetime(upd.ts)
        cut_ts = pd.Timestamp(D.live_cut()) if live else pd.Timestamp(D.CUT)

        items = cat[["product_id", "category", "subcategory", "price", "is_active"]].copy()
        items["new"] = False
        if live:  # products added during the event, and the latest price / stock before the cut
            u = upd[upd.ts < cut_ts]
            newp = u[u.change == "new_product"].drop_duplicates("product_id", keep="last")
            newp = newp[["product_id", "category", "subcategory", "price", "is_active"]].assign(new=True)
            items = pd.concat([items, newp[~newp.product_id.isin(items.product_id)]], ignore_index=True)
            last = u.sort_values("ts").drop_duplicates("product_id", keep="last").set_index("product_id")
            idx = items.product_id.isin(last.index)
            items.loc[idx, "price"] = last.loc[items.loc[idx, "product_id"], "price"].to_numpy()
        items = items.reset_index(drop=True)
        cats = sorted(items.category.unique())
        subs = sorted(items.subcategory.unique())
        items["cat"] = items.category.map({c: i for i, c in enumerate(cats)})
        items["sub"] = items.subcategory.map({s: i for i, s in enumerate(subs)})
        pid2i = {p: i for i, p in enumerate(items.product_id)}
        nI, nC, nS = len(items), len(cats), len(subs)

        # ---- users x category
        uc = D.pull("user_cat")
        uc = uc[uc.pre.astype(bool)] if not live else uc
        if live:
            luc = D.pull("live_user_cat", live_cut=str(cut_ts))
            uc = pd.concat([uc, luc[["user_id", "category", "v", "c", "p"]]], ignore_index=True)
        users = sorted(uc.user_id.unique())
        u2i = {u: i for i, u in enumerate(users)}
        ui = uc.user_id.map(u2i).to_numpy()
        ci = uc.category.map({c: i for i, c in enumerate(cats)}).to_numpy()
        mats = []
        for col in ("v", "c", "p"):
            m = np.zeros((len(users), nC), np.float32)
            np.add.at(m, (ui, ci), uc[col].astype(float).to_numpy())
            mats.append(m)
        U_v, U_c, U_p = mats

        us = D.pull("user_sub")
        us = us[us.pre.astype(bool)] if not live else us
        us = us[us.user_id.isin(u2i)]
        U_sub = sp.csr_matrix(((us.v.astype(float) + 3 * us.cp.astype(float)).to_numpy(),
                               (us.user_id.map(u2i).to_numpy(), us.subcategory.map({s: i for i, s in enumerate(subs)}).to_numpy())),
                              shape=(len(users), nS))

        # ---- purchases: bought sets and price level
        pur = D.pull("purchases")
        pur["ts"] = pd.to_datetime(pur.ts)
        pur = pur[pur.ts < (cut_ts if not live else pd.Timestamp.max)]
        if live:
            lp = D.pull("live_purchases", live_cut=str(cut_ts))
            pur = pd.concat([pur, lp.assign(ts=pd.to_datetime(lp.ts))], ignore_index=True)
        pur = pur[pur.user_id.isin(u2i) & pur.product_id.isin(pid2i)]
        pu, pi = pur.user_id.map(u2i).to_numpy(), pur.product_id.map(pid2i).to_numpy()
        bought: dict[int, set[int]] = {}
        for a, b in zip(pu, pi):
            bought.setdefault(int(a), set()).add(int(b))
        lp_ = np.log(items.price.to_numpy()[pi])
        U_logprice = np.full(len(users), np.nan, np.float32)
        s = pd.Series(lp_).groupby(pu).median()
        U_logprice[s.index.to_numpy()] = s.to_numpy()

        # ---- item stats
        ist = D.pull("item_stats")
        ist = ist[ist.pre.astype(bool)] if not live else ist
        ist = ist.groupby("product_id")[["v", "c", "p"]].sum()
        I_v, I_c, I_p = (np.zeros(nI, np.float32) for _ in range(3))
        hit = ist.index.isin(pid2i)
        ii = ist.index[hit].map(pid2i).to_numpy()
        I_v[ii], I_c[ii], I_p[ii] = (ist.loc[hit, k].to_numpy(float) for k in ("v", "c", "p"))
        I_trend = np.ones(nI, np.float32)
        if live:  # live purchases per item vs the 60-day average rate, smoothed
            lis = D.pull("live_item_stats", live_cut=str(cut_ts)).set_index("product_id")
            hours_live = max((cut_ts - pd.Timestamp("2026-11-14 09:00")).total_seconds() / 3600, 0.5)
            lv = np.zeros(nI, np.float32)
            h2 = lis.index.isin(pid2i)
            lv[lis.index[h2].map(pid2i).to_numpy()] = lis.loc[h2, "v"].to_numpy(float) + 3 * lis.loc[h2, "p"].to_numpy(float)
            base = (I_v + 3 * I_p) / (60 * 24)
            I_trend = ((lv / hours_live) + 1.0) / (base + 1.0)

        # ---- co-views (built before CUT in both modes)
        cv = D.pull("coview")
        cv = cv[cv.p.isin(pid2i) & cv.q.isin(pid2i)]
        r, c = cv.p.map(pid2i).to_numpy(), cv.q.map(pid2i).to_numpy()
        n = cv.n.astype(float).to_numpy()
        CV = sp.csr_matrix((n, (r, c)), shape=(nI, nI))
        rs = np.asarray(CV.sum(1)).ravel()
        CV = sp.diags(1 / np.maximum(rs, 1)) @ CV

        # ---- context prior P(category | device, region) from purchases
        cc = D.pull("ctx_cat")
        cc = cc[cc.pre.astype(bool)] if not live else cc
        regions = {r: i for i, r in enumerate(sorted(cc.region.unique()))}
        ctx_cat = {}
        for (dv, rg), g in cc.groupby(["device", "region"]):
            v = np.zeros(nC)
            np.add.at(v, g.category.map({c: i for i, c in enumerate(cats)}).to_numpy(), g.p.astype(float).to_numpy())
            ctx_cat[(DEVICES.get(dv, 0), regions[rg])] = (v + 1) / (v.sum() + nC)
        cp = np.zeros(nC)
        np.add.at(cp, items.cat.to_numpy(), I_p)
        cat_pop = (cp + 1) / (cp.sum() + nC)

        store = cls(mode, items, pid2i, cats, subs, regions, u2i, U_v, U_c, U_p, U_sub, U_logprice, bought,
                    I_v, I_c, I_p, I_trend, CV, ctx_cat, cat_pop)
        if cold_start:
            store.impute_new_items()
        return store

    def impute_new_items(self, k: int = 10, shrink: float = 0.7) -> None:
        """P3 cold start: new products have only a description. Borrow (shrunk) activity stats from the k most
        similar established products in the same subcategory/category by TF-IDF of description + brand."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        cat = D.pull("catalog").set_index("product_id")
        upd = D.pull("catalog_updates").drop_duplicates("product_id", keep="last").set_index("product_id")
        desc = pd.concat([cat.description, upd.description[~upd.index.isin(cat.index)]])
        brand = pd.concat([cat.brand, upd.brand[~upd.index.isin(cat.index)]])
        txt = (desc.reindex(self.items.product_id).fillna("") + " " + brand.reindex(self.items.product_id).fillna("")).to_numpy()
        T = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True).fit_transform(txt)
        new = np.flatnonzero(self.items.new.to_numpy())
        old = np.flatnonzero(~self.items.new.to_numpy())
        sub, catv = self.items["sub"].to_numpy(), self.items.cat.to_numpy()
        sim = (T[new] @ T[old].T).toarray()
        sim += 1.0 * (sub[new][:, None] == sub[old][None, :]) + 0.3 * (catv[new][:, None] == catv[old][None, :])
        nb = old[np.argsort(-sim, axis=1)[:, :k]]
        for name in ("I_v", "I_c", "I_p"):
            arr = getattr(self, name)
            arr[new] = shrink * arr[nb].mean(1)
        self.extra["new_neighbours"] = dict(zip(new, nb))

    # ------------------------------------------------------------------ requests
    def requests(self, df: pd.DataFrame) -> Requests:
        N, nI, nC, nS = len(df), len(self.items), len(self.cats), len(self.subs)
        user = df.user_id.map(self.u2i).fillna(-1).astype(int).to_numpy()
        ctx = df.context.tolist()
        page = np.array([PAGES.get(_field(c, "page"), 0) for c in ctx])
        device = np.array([DEVICES.get(_field(c, "device"), 0) for c in ctx])
        region = np.array([self.regions.get(_field(c, "region"), 0) for c in ctx])
        views, rows, cols, vals = [], [], [], []
        for n, rv in enumerate(df.recent_views.tolist()):
            vv = [self.pid2i[v["product_id"]] for v in (rv or []) if v.get("product_id") in self.pid2i]
            views.append(vv)
            for k, it in enumerate(reversed(vv)):      # newest first, decayed
                rows.append(n); cols.append(it); vals.append(0.6 ** k)
        RV = sp.csr_matrix((vals, (rows, cols)), shape=(N, nI))
        RV.sum_duplicates()
        cat_of, sub_of = self.items.cat.to_numpy(), self.items["sub"].to_numpy()
        sess_cat = (RV @ sp.csr_matrix((np.ones(nI), (np.arange(nI), cat_of)), shape=(nI, nC))).toarray()
        sess_sub = (RV @ sp.csr_matrix((np.ones(nI), (np.arange(nI), sub_of)), shape=(nI, nS))).toarray()
        last_item = np.array([v[-1] if v else -1 for v in views])
        is_new = df.is_new_user.astype(bool).to_numpy() if "is_new_user" in df else (user < 0)
        RVCV = (RV @ self.CV).tocsr()
        return Requests(df, user, page, device, region, views, last_item, sess_cat, sess_sub, RV, is_new, RVCV)

    # ------------------------------------------------------------------ pair features
    FEATURES = ["slot", "page", "device", "known_user", "n_views",
                "u_cat_v", "u_cat_c", "u_cat_p", "u_cat_share", "u_sub",
                "s_cat", "s_cat_share", "s_sub", "last_cat", "last_sub", "is_last", "in_views",
                "coview", "i_logp", "i_conv", "i_cart", "logprice", "price_vs_user", "price_vs_last",
                "bought", "ctx_cat", "cat_pop", "cat", "new_item", "trend"]

    # Features the models must not learn from. "bought": history shows heavy re-buying (62% of carousel
    # purchases), but live the hidden model makes bought items lose appeal (0 of 82 live purchases were
    # re-buys). We drop it from the models and handle it explicitly (ban in policies, penalty in simulator).
    MASKED = ("bought",)

    def model_X(self, X: np.ndarray) -> np.ndarray:
        X = X.copy()
        for f in self.MASKED:
            X[:, self.FEATURES.index(f)] = 0
        return X

    def pair_features(self, R: Requests, ri: np.ndarray, ii: np.ndarray, slot: np.ndarray | int) -> np.ndarray:
        it = self.items
        cat = it.cat.to_numpy()[ii]
        sub = it["sub"].to_numpy()[ii]
        logprice = np.log(it.price.to_numpy()[ii].astype(float))
        u = R.user[ri]
        known = u >= 0
        uu = np.where(known, u, 0)
        ucv = np.where(known, self.U_v[uu, cat], 0)
        ucc = np.where(known, self.U_c[uu, cat], 0)
        ucp = np.where(known, self.U_p[uu, cat], 0)
        tot = np.where(known, self.U_v[uu].sum(1) + 3 * self.U_c[uu].sum(1) + 5 * self.U_p[uu].sum(1), 0)
        ushare = (ucv + 3 * ucc + 5 * ucp + 0.1) / (tot + 1.0)
        usub = np.where(known, np.asarray(self.U_sub[uu, sub]).ravel(), 0)
        n_views = np.array([len(R.views[r]) for r in ri])
        s_cat = R.sess_cat[ri, cat]
        s_tot = R.sess_cat[ri].sum(1)
        s_sub = R.sess_sub[ri, sub]
        last = R.last_item[ri]
        has_last = last >= 0
        lastc = np.where(has_last, it.cat.to_numpy()[np.maximum(last, 0)], -1)
        lasts = np.where(has_last, it["sub"].to_numpy()[np.maximum(last, 0)], -1)
        lastp = np.where(has_last, np.log(it.price.to_numpy()[np.maximum(last, 0)].astype(float)), np.nan)
        in_views = np.asarray(R.RV[ri, ii]).ravel()
        # co-view score: sum over recent views v (decayed) of CV[v, item]
        cvs = np.asarray(R.RVCV[ri, ii]).ravel()
        ulp = np.where(known, self.U_logprice[uu], np.nan)
        bought = np.array([int(i) in self.bought.get(int(x), ()) for x, i in zip(u, ii)], dtype=float)
        ctxc = np.array([self.ctx_cat.get((d, r), self.cat_pop)[c] for d, r, c in
                         zip(R.device[ri], R.region[ri], cat)])
        Ip, Iv, Ic = self.I_p[ii], self.I_v[ii], self.I_c[ii]
        X = np.column_stack([
            np.broadcast_to(slot, ri.shape), R.page[ri], R.device[ri], known, n_views,
            ucv, ucc, ucp, ushare, usub,
            s_cat, s_cat / np.maximum(s_tot, 1e-9), s_sub, lastc == cat, lasts == sub, last == ii, in_views,
            cvs, np.log1p(Ip), (Ip + 1) / (Iv + 50), (Ic + 1) / (Iv + 50), logprice, logprice - ulp, logprice - lastp,
            bought, ctxc, self.cat_pop[cat], cat, it.new.to_numpy()[ii], self.I_trend[ii],
        ]).astype(np.float32)
        return X

    # ------------------------------------------------------------------ stock
    def stock_timeline(self) -> pd.DataFrame:
        upd = D.pull("catalog_updates")
        upd = upd[upd.change.isin(["out_of_stock", "back_in_stock", "new_product"])].copy()
        upd["ts"] = pd.to_datetime(upd.ts)
        return upd.sort_values("ts")[["ts", "product_id", "change"]]

    def unavailable_at(self, ts: pd.Timestamp, _cache={}) -> set[int]:
        """Item indices that are out of stock (or not yet launched) at time ts. Offline: inactive items."""
        if self.mode == "offline":
            return set(np.flatnonzero(~self.items.is_active.to_numpy().astype(bool)))
        key = (id(self), ts.floor("10s"))
        if key not in _cache:
            tl = self.extra.setdefault("tl", self.stock_timeline())
            t = tl[tl.ts <= ts].drop_duplicates("product_id", keep="last")
            out = set(t.product_id[t.change == "out_of_stock"])
            out |= set(self.items.product_id[~self.items.is_active.astype(bool)])
            _cache[key] = {self.pid2i[p] for p in out if p in self.pid2i}
        return _cache[key]
