"""Click / buy feature rows for (request, item, slot). Names are fixed: weight trajectories are logged by name."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

CLICK_FEATURES = (["bias"] + [f"slot_{k}" for k in range(1, 11)] +
                  ["earlier_viewed", "last_viewed", "earlier_viewed_top3", "last_viewed_top3", "sess_cat_share",
                   "same_last_sub", "hist_cat_share", "bought_same_sub", "logp_in_sess_cat", "logp_out_sess_cat",
                   "log_price", "log_price_ratio", "log_price_ratio_sq", "new_item", "cold", "page_home",
                   "page_category", "nviews_0", "nviews_1_3", "served_by_fallback"])
BUY_FEATURES = ["bias", "log_price", "cold", "page_home", "viewed"]
_C = {n: k for k, n in enumerate(CLICK_FEATURES)}


def _get(x, key, default=None):
    return x.get(key, default) if isinstance(x, dict) else default


@dataclass
class Req:
    request_id: str
    ts: pd.Timestamp
    user_id: str
    is_new_user: bool
    page: str
    views: list = field(default_factory=list)   # item idx, oldest -> newest, only views before ts
    cold: bool = False
    served_by_fallback: bool = False

    @classmethod
    def from_row(cls, row: dict, st, served_by_fallback: bool = False) -> "Req":
        ts = pd.Timestamp(row["ts"])
        views = []
        for v in row.get("recent_views") or []:
            p = _get(v, "product_id")
            vt = _get(v, "ts")
            if p in st.pid2i and (vt is None or pd.Timestamp(vt) < ts):
                views.append(st.pid2i[p])
        new = st.items.new.to_numpy()
        is_new_user = bool(row.get("is_new_user"))
        cold = is_new_user or any(bool(new[i]) for i in views)
        return cls(str(row["request_id"]), ts, str(row.get("user_id")), is_new_user,
                   _get(row.get("context"), "page", "home") or "home", views, cold, served_by_fallback)


def click_matrix(st, req: Req, items: np.ndarray, slots: np.ndarray) -> np.ndarray:
    """slots are 1-based (1..10)."""
    items = np.asarray(items, dtype=int)
    slots = np.asarray(slots, dtype=int)
    it = st.items
    cat = it.cat.to_numpy()[items]
    sub = it["sub"].to_numpy()[items]
    price = it.price.to_numpy().astype(float)
    logp = it.logp.to_numpy()[items]
    X = np.zeros((len(items), len(CLICK_FEATURES)))
    X[:, _C["bias"]] = 1
    X[np.arange(len(items)), _C["slot_1"] + np.clip(slots, 1, 10) - 1] = 1
    views = req.views
    last = views[-1] if views else -1
    earlier = set(views[:-1]) - {last}
    is_last = items == last
    is_earlier = np.array([i in earlier for i in items], dtype=bool)
    top3 = slots <= 3
    X[:, _C["last_viewed"]] = is_last
    X[:, _C["earlier_viewed"]] = is_earlier
    X[:, _C["last_viewed_top3"]] = is_last & top3
    X[:, _C["earlier_viewed_top3"]] = is_earlier & top3
    if views:
        vc = it.cat.to_numpy()[views]
        share = np.bincount(vc, minlength=len(st.cats)) / len(views)
        sc = share[cat] if share.shape[0] > cat.max(initial=0) else np.zeros(len(items))
        X[:, _C["sess_cat_share"]] = sc
        X[:, _C["same_last_sub"]] = sub == it["sub"].to_numpy()[last]
        in_sess = sc > 0
        ratio = np.log(np.maximum(price[items], .01) / max(price[last], .01))
        X[:, _C["log_price_ratio"]] = ratio
        X[:, _C["log_price_ratio_sq"]] = ratio ** 2
    else:
        in_sess = np.zeros(len(items), bool)
    X[:, _C["logp_in_sess_cat"]] = np.where(in_sess, logp, 0)
    X[:, _C["logp_out_sess_cat"]] = np.where(in_sess, 0, logp)
    u = st.ucat.get(req.user_id)
    if u is not None:
        X[:, _C["hist_cat_share"]] = np.where(cat < len(u), u[np.minimum(cat, len(u) - 1)], 0)
    bs = st.bought_sub.get(req.user_id, ())
    if bs:
        X[:, _C["bought_same_sub"]] = np.isin(sub, list(bs))
    X[:, _C["log_price"]] = np.log(np.maximum(price[items], .01))
    X[:, _C["new_item"]] = it.new.to_numpy()[items].astype(float)
    X[:, _C["cold"]] = float(req.cold)
    X[:, _C["page_home"]] = float(req.page == "home")
    X[:, _C["page_category"]] = float(req.page == "category")
    X[:, _C["nviews_0"]] = float(len(views) == 0)
    X[:, _C["nviews_1_3"]] = float(1 <= len(views) <= 3)
    X[:, _C["served_by_fallback"]] = float(req.served_by_fallback)
    return X


def buy_matrix(st, req: Req, items: np.ndarray) -> np.ndarray:
    items = np.asarray(items, dtype=int)
    price = st.items.price.to_numpy().astype(float)[items]
    X = np.zeros((len(items), len(BUY_FEATURES)))
    X[:, 0] = 1
    X[:, 1] = np.log(np.maximum(price, .01))
    X[:, 2] = float(req.cold)
    X[:, 3] = float(req.page == "home")
    X[:, 4] = np.isin(items, req.views)
    return X
