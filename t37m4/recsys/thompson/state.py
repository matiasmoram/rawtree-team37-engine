"""Live state for the Thompson learner: catalogue, stock, bought sets, user/item stats, co-views.

Everything is refreshed by deltas (watermarks on ts), so new products, price changes, stock changes and
purchases (organic or through any shown list) reach serving within ~20-60 s. Readers never lock: mutating
methods build new objects and swap references.
"""
from __future__ import annotations

import threading
import time

import numpy as np
import pandas as pd

UPDATES_SQL = """
SELECT toString(ts) ts_s, change::String change, product_id::String product_id, category::String category,
       subcategory::String subcategory, brand::String brand, price_eur::Float64 price
FROM shop.catalog_updates {where} ORDER BY ts"""

PURCHASES_SQL = """
SELECT user_id::String user_id, product_id::String product_id, toString(ts) ts_s
FROM shop.events WHERE event_type = 'purchase' AND {where} ORDER BY ts"""

TSF = "%Y-%m-%d %H:%M:%S.%f"

CATALOG_SQL = """
SELECT product_id::String product_id, category::String category, subcategory::String subcategory,
       brand::String brand, price_eur::Float64 price, is_active::Bool is_active FROM shop.catalog"""


def q(sql: str, **kw) -> pd.DataFrame:
    """Run a delta query; selects alias the timestamp as ts_s (so WHERE sees the raw column) -> ts."""
    from .. import data as D
    return D.sql(sql, **kw).rename(columns={"ts_s": "ts"})


def _after(mark: str) -> str:
    """Rows strictly after a toString(ts) watermark (string compare keeps full precision; the
    DateTime bound lets RawTree prune)."""
    return f"ts >= toDateTime('{mark[:19]}') AND toString(ts) > '{mark}'"


def purchases_where(mark: str, overlap_s: int = 60) -> str:
    """Purchases after the watermark minus an overlap, so rows inserted late with an older ts are not skipped
    (apply_purchases is idempotent)."""
    back = (pd.Timestamp(mark) - pd.Timedelta(seconds=overlap_s)).strftime("%Y-%m-%d %H:%M:%S.%f")
    return _after(back)


class LiveState:
    def __init__(self):
        self.lock = threading.Lock()
        self.upd_mark = "1970-01-01 00:00:00"
        self.buy_mark = "2026-11-14 00:00:00"

    # ------------------------------------------------------------------ build
    @classmethod
    def from_frames(cls, catalog, updates, purchases, user_cat, item_stats, coview) -> "LiveState":
        st = cls()
        items = catalog[["product_id", "category", "subcategory", "price"]].copy().reset_index(drop=True)
        items["price"] = items.price.astype(float)
        items["new"] = False
        st.cats = sorted(items.category.unique())
        st.subs = sorted(items.subcategory.unique())
        items["cat"] = items.category.map({c: i for i, c in enumerate(st.cats)}).astype(int)
        items["sub"] = items.subcategory.map({s: i for i, s in enumerate(st.subs)}).astype(int)
        pop = item_stats.groupby("product_id").p.sum()
        items["logp"] = np.log1p(pop.reindex(items.product_id).fillna(0).to_numpy().astype(float))
        st.items = items
        st.pid2i = {p: i for i, p in enumerate(items.product_id)}
        active = catalog.is_active.astype(bool).to_numpy() if "is_active" in catalog else np.ones(len(items), bool)
        st.oos = set(np.flatnonzero(~active).tolist())
        st._rebuild_best()

        st.bought, st.bought_sub, st.bought_at = {}, {}, {}
        st.apply_purchases(purchases)

        uc = user_cat.copy()
        uc["w"] = uc.v.astype(float) + 3 * uc.c.astype(float) + 10 * uc.p.astype(float)
        uc = uc[uc.category.isin(st.cats)]
        g = uc.groupby(["user_id", "category"]).w.sum().reset_index()
        g["ci"] = g.category.map({c: i for i, c in enumerate(st.cats)})
        st.ucat = {}
        for u, d in g.groupby("user_id"):
            a = np.zeros(len(st.cats))
            a[d.ci.to_numpy()] = d.w.to_numpy()
            if a.sum() > 0:
                st.ucat[u] = a / a.sum()

        cov = coview[coview.p.isin(st.pid2i) & coview.q.isin(st.pid2i)].sort_values(["p", "n"], ascending=[True, False])
        st.cov = {st.pid2i[p]: [st.pid2i[q] for q in d.q] for p, d in cov.groupby("p")}

        if len(updates):
            st.apply_updates(updates)
        return st

    @classmethod
    def load(cls) -> "LiveState":
        """Fresh catalogue + all updates + live purchases from RawTree; history from data/ caches."""
        from .. import data as D
        t = time.time()
        catalog = D.sql(CATALOG_SQL)
        updates = q(UPDATES_SQL.format(where=""), timeout=300)
        purchases = pd.concat([pd.read_pickle(D.DATA / "purchases.pkl"),
                               q(PURCHASES_SQL.format(where="ts >= '2026-11-14 00:00:00'"), timeout=300)],
                              ignore_index=True)
        st = cls.from_frames(catalog, updates, purchases, pd.read_pickle(D.DATA / "user_cat.pkl"),
                             pd.read_pickle(D.DATA / "item_stats.pkl"), pd.read_pickle(D.DATA / "coview.pkl"))
        print(f"LiveState: {len(st.items)} items ({int(st.items.new.sum())} new), {len(st.oos)} oos, "
              f"{len(st.bought)} buyers, {len(st.ucat)} users with history, {time.time() - t:.1f}s", flush=True)
        return st

    def _rebuild_best(self):
        it = self.items
        order = np.lexsort((-it.new.to_numpy().astype(int), -it.logp.to_numpy()))  # by logp desc, new first on ties
        cat, sub = it.cat.to_numpy()[order], it["sub"].to_numpy()[order]
        self.cat_best = {c: order[cat == c].tolist() for c in range(len(self.cats))}
        self.sub_best = {s: order[sub == s].tolist() for s in range(len(self.subs))}

    # ------------------------------------------------------------------ deltas
    def apply_updates(self, rows: pd.DataFrame) -> int:
        if not len(rows):
            return 0
        rows = rows.sort_values("ts")
        new = rows[(rows.change == "new_product") & ~rows.product_id.isin(self.pid2i)].drop_duplicates("product_id")
        with self.lock:
            if len(new):
                it = self.items
                for c in new.category.unique():
                    if c not in self.cats:
                        self.cats = self.cats + [c]
                for s in new.subcategory.unique():
                    if s not in self.subs:
                        self.subs = self.subs + [s]
                sub_lp = it.groupby("sub").logp.mean()
                add = pd.DataFrame(dict(product_id=new.product_id.to_numpy(), category=new.category.to_numpy(),
                                        subcategory=new.subcategory.to_numpy(), price=new.price.astype(float).to_numpy(),
                                        new=True))
                add["cat"] = add.category.map({c: i for i, c in enumerate(self.cats)}).astype(int)
                add["sub"] = add.subcategory.map({s: i for i, s in enumerate(self.subs)}).astype(int)
                add["logp"] = add["sub"].map(sub_lp).fillna(float(it.logp.mean())).astype(float)
                items = pd.concat([it, add], ignore_index=True)
                pid2i = dict(self.pid2i)
                for k, p in enumerate(add.product_id, start=len(it)):
                    pid2i[p] = k
                self.items = items
                self.pid2i = pid2i
                self._rebuild_best()
            price = rows[rows.change == "price_change"]
            if len(price):
                items = self.items.copy()
                for p, v in zip(price.product_id, price.price):
                    if p in self.pid2i and pd.notna(v):
                        items.at[self.pid2i[p], "price"] = float(v)
                self.items = items
            oos = set(self.oos)
            for ch, p in zip(rows.change, rows.product_id):
                i = self.pid2i.get(p)
                if i is None:
                    continue
                if ch == "out_of_stock":
                    oos.add(i)
                elif ch in ("back_in_stock", "new_product"):
                    oos.discard(i)
            self.oos = oos
            self.upd_mark = max(self.upd_mark, str(rows.ts.iloc[-1]))
        return len(rows)

    def apply_purchases(self, rows: pd.DataFrame) -> int:
        n = 0
        subs = self.items["sub"].to_numpy()
        tss = (pd.to_datetime(rows.ts).dt.strftime(TSF) if "ts" in rows and len(rows) else [""] * len(rows))
        for u, p, t in zip(rows.user_id, rows.product_id, tss):
            i = self.pid2i.get(p)
            if i is None:
                continue
            self.bought.setdefault(u, set()).add(i)
            at = self.bought_at.setdefault(u, {})
            if i not in at or t < at[i]:
                at[i] = t
            self.bought_sub.setdefault(u, set()).add(int(subs[i]))
            n += 1
        if len(rows) and "ts" in rows:
            self.buy_mark = max(self.buy_mark, str(rows.ts.max()))
        return n

    def bought_before(self, user: str, ts) -> set[int]:
        """Items the user had bought strictly before ts (for training rows: a purchase made through the
        shown list itself must not ban its own positive label)."""
        t = pd.Timestamp(ts).strftime(TSF)
        return {i for i, b in dict(self.bought_at.get(user, {})).items() if b < t}

    def refresh_loop(self, stop: threading.Event, buys_every: float = 3, upd_every: float = 20):
        from .. import data as D
        last_upd = 0.0
        while not stop.is_set():
            try:
                rows = q(PURCHASES_SQL.format(where=purchases_where(self.buy_mark)), timeout=10)
                self.apply_purchases(rows)
            except Exception as e:
                print("state: purchases refresh failed:", str(e)[:120], flush=True)
            if time.time() - last_upd > upd_every:
                try:
                    self.apply_updates(q(UPDATES_SQL.format(where="WHERE " + _after(self.upd_mark)), timeout=30))
                    last_upd = time.time()
                except Exception as e:
                    print("state: catalogue refresh failed:", str(e)[:120], flush=True)
            stop.wait(buys_every)
