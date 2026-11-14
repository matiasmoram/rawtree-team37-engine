"""Candidate generation and feature extraction shared by training and serving.

Single source of truth: the learned rankers are trained on exactly the features they see live.
Features are generic (relations, ranks, rates, ratios); no product or user ids, so the model can
generalise to new products, new users and shifted trends.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from .snapshot import Snapshot
from .types import Request

CAROUSEL_MEAN = 28053 / 20_000_000
ORGANIC_MEAN = 548160 / 10354047
NONE_DAYS = 365.0

FEATURES = [
    "is_last_view", "view_rank", "n_item_views", "mins_since_item_view",
    "sess_sub_share", "sess_cat_share", "same_sub_last", "same_cat_last",
    "covis_vb", "covis_vv", "covis_vb_rank",
    "user_bought_n", "user_days_since_buy", "user_viewed_n", "user_days_since_view",
    "user_sub_share", "user_cat_share", "user_known", "bought_in_event",
    "log_price", "log_price_vs_user", "log_price_vs_sub", "log_price_change",
    "q_carousel", "log_carousel_shown", "q_organic",
    "log_buy_7d", "log_buy_all", "log_buy_1d", "log_trend", "log_view_3h",
    "is_new_item", "item_age_hours_if_new",
    "page_home", "page_product", "page_category", "dev_ios", "dev_android",
    "n_session_views", "is_new_user",
    "slot",
]
FIDX = {name: i for i, name in enumerate(FEATURES)}


@dataclass
class Context:
    """Per-request quantities reused for every candidate."""
    req: Request
    viewed: list[str]
    view_rank: dict[str, int]
    view_count: dict[str, int]
    view_last_ts: dict[str, datetime]
    sess_sub: dict[str, float]
    sess_cat: dict[str, float]
    last_sub: str | None
    last_cat: str | None
    covis_vb: dict[str, float]
    covis_vv: dict[str, float]
    covis_vb_rank: dict[str, int]
    ubuy: dict
    uview: dict
    usub: dict[str, float]
    ucat: dict[str, float]
    usub_total: float
    ucat_total: float
    uprice: float | None
    recent_buys: set[str]
    candidates: list[str] = field(default_factory=list)


def build_context(req: Request, snap: Snapshot, max_views: int = 6, covis_views: int = 4, covis_top: int = 25) -> Context:
    products = snap.products
    viewed = [p for p in req.viewed if p in products][:max_views]
    view_count: dict[str, int] = defaultdict(int)
    view_last: dict[str, datetime] = {}
    for pid, ts in req.recent_views:
        view_count[pid] += 1
        if pid not in view_last or ts > view_last[pid]:
            view_last[pid] = ts
    sess_sub: dict[str, float] = defaultdict(float)
    sess_cat: dict[str, float] = defaultdict(float)
    for k, pid in enumerate(viewed):
        p = products[pid]
        sess_sub[p.sub] += 0.7 ** k
        sess_cat[p.cat] += 0.7 ** k
    tot = sum(sess_sub.values()) or 1.0
    sess_sub = {k: v / tot for k, v in sess_sub.items()}
    sess_cat = {k: v / tot for k, v in sess_cat.items()}

    covis_vb: dict[str, float] = defaultdict(float)
    covis_vv: dict[str, float] = defaultdict(float)
    for k, pid in enumerate(viewed[:covis_views]):
        decay = 0.7 ** k
        for table, acc in ((snap.covis_vb, covis_vb), (snap.covis_vv, covis_vv)):
            neigh = table.get(pid, [])[:covis_top]
            if neigh:
                top = neigh[0][1] or 1.0
                for q, w in neigh:
                    acc[q] += decay * w / top
    vb_rank = {q: r for r, (q, _) in enumerate(sorted(covis_vb.items(), key=lambda x: -x[1]))}

    user = req.user_id
    usub = snap.user_sub.get(user, {})
    ucat = snap.user_cat.get(user, {})
    last = products[viewed[0]] if viewed else None
    return Context(
        req=req, viewed=viewed, view_rank={p: k for k, p in enumerate(viewed)}, view_count=dict(view_count),
        view_last_ts=view_last, sess_sub=sess_sub, sess_cat=sess_cat,
        last_sub=last.sub if last else None, last_cat=last.cat if last else None,
        covis_vb=dict(covis_vb), covis_vv=dict(covis_vv), covis_vb_rank=vb_rank,
        ubuy=snap.user_buy.get(user, {}), uview=snap.user_view.get(user, {}),
        usub=usub, ucat=ucat, usub_total=sum(usub.values()) or 1.0, ucat_total=sum(ucat.values()) or 1.0,
        uprice=snap.user_price.get(user), recent_buys=snap.recent_user_buys.get(user, set()),
    )


def generate_candidates(ctx: Context, snap: Snapshot, n_covis: int = 40) -> list[str]:
    """Union of candidate sources; order does not matter (the ranker sorts)."""
    products = snap.products
    cand: dict[str, None] = dict.fromkeys(ctx.viewed)
    for q, _ in sorted(ctx.covis_vb.items(), key=lambda x: -x[1])[:n_covis]:
        cand[q] = None
    for q, _ in sorted(ctx.covis_vv.items(), key=lambda x: -x[1])[:n_covis]:
        cand[q] = None
    if ctx.ubuy:
        for q in sorted(ctx.ubuy, key=lambda p: ctx.ubuy[p][1], reverse=True)[:20]:
            cand[q] = None
    if ctx.uview:
        for q in sorted(ctx.uview, key=lambda p: ctx.uview[p][0], reverse=True)[:10]:
            cand[q] = None
    for sub in sorted(ctx.sess_sub, key=ctx.sess_sub.get, reverse=True)[:3]:
        for q in snap.pop_by_sub.get(sub, [])[:20]:
            cand[q] = None
    if ctx.last_cat:
        for q in snap.pop_by_cat.get(ctx.last_cat, [])[:15]:
            cand[q] = None
    for sub in sorted(ctx.usub, key=ctx.usub.get, reverse=True)[:3]:
        for q in snap.pop_by_sub.get(sub, [])[:10]:
            cand[q] = None
    for q in snap.trending[:20]:
        cand[q] = None
    for q in snap.pop_global[:20]:
        cand[q] = None
    new_by_sub = getattr(snap, "new_by_sub", None)
    if new_by_sub is None:
        new_by_sub = defaultdict(list)
        for pid, p in products.items():
            if p.is_new:
                new_by_sub[p.sub].append(pid)
    for sub in ctx.sess_sub:
        for q in new_by_sub.get(sub, []):
            cand[q] = None
    return [q for q in cand if q in products and products[q].active]


def _l(x: float) -> float:
    return math.log1p(max(x, 0.0))


def featurize(ctx: Context, snap: Snapshot, items: list[str], slots: list[int] | None = None,
              sub_price: dict[str, float] | None = None) -> np.ndarray:
    """Feature matrix (len(items) x len(FEATURES)). `slots` is only given for logged training rows."""
    req = ctx.req
    T = req.ts
    X = np.zeros((len(items), len(FEATURES)), dtype=np.float32)
    sub_quality = snap.sub_quality
    sub_price = sub_price or getattr(snap, "sub_price", {}) or {}
    page = req.page
    for i, pid in enumerate(items):
        p = snap.products.get(pid)
        if p is None:
            continue
        row = X[i]
        k = ctx.view_rank.get(pid)
        row[0] = 1.0 if k == 0 else 0.0
        row[1] = k if k is not None else 9.0
        row[2] = ctx.view_count.get(pid, 0)
        lt = ctx.view_last_ts.get(pid)
        row[3] = min((T - lt).total_seconds() / 60.0, 999.0) if lt else 999.0
        row[4] = ctx.sess_sub.get(p.sub, 0.0)
        row[5] = ctx.sess_cat.get(p.cat, 0.0)
        row[6] = 1.0 if ctx.last_sub == p.sub else 0.0
        row[7] = 1.0 if ctx.last_cat == p.cat else 0.0
        row[8] = ctx.covis_vb.get(pid, 0.0)
        row[9] = ctx.covis_vv.get(pid, 0.0)
        row[10] = ctx.covis_vb_rank.get(pid, 99)
        b = ctx.ubuy.get(pid)
        row[11] = b[0] if b else 0.0
        row[12] = min((T - b[1]).total_seconds() / 86400.0, NONE_DAYS) if b else NONE_DAYS
        v = ctx.uview.get(pid)
        row[13] = v[0] if v else 0.0
        row[14] = min((T - v[1]).total_seconds() / 86400.0, NONE_DAYS) if v else NONE_DAYS
        row[15] = ctx.usub.get(p.sub, 0.0) / ctx.usub_total
        row[16] = ctx.ucat.get(p.cat, 0.0) / ctx.ucat_total
        row[17] = 1.0 if (ctx.usub or ctx.ubuy) else 0.0
        row[18] = 1.0 if pid in ctx.recent_buys else 0.0
        row[19] = math.log(max(p.price, 0.5))
        row[20] = math.log(p.price / ctx.uprice) if ctx.uprice and p.price > 0 else 0.0
        sp = sub_price.get(p.sub)
        row[21] = math.log(p.price / sp) if sp and p.price > 0 else 0.0
        row[22] = math.log(p.price / p.base_price) if p.base_price > 0 and p.price > 0 else 0.0
        shown, _, buys = snap.carousel.get(pid, (0, 0, 0))
        row[23] = (buys + 500 * CAROUSEL_MEAN) / (shown + 500) / CAROUSEL_MEAN
        row[24] = _l(shown)
        s = snap.stats.get(pid)
        if s:
            row[25] = (s["buy_all"] + 50 * ORGANIC_MEAN) / (s["view_all"] + 50) / ORGANIC_MEAN
            row[26] = _l(s["buy_7d"])
            row[27] = _l(s["buy_all"])
            row[28] = _l(s["buy_1d"])
            row[29] = math.log(snap.trend_lift(pid))
            row[30] = _l(s["view_3h"])
        else:
            row[25] = sub_quality.get(p.sub, 1.0)
        row[31] = 1.0 if p.is_new else 0.0
        row[32] = min((T - p.added_ts).total_seconds() / 3600.0, 999.0) if (p.is_new and p.added_ts) else 999.0
        row[33] = 1.0 if page == "home" else 0.0
        row[34] = 1.0 if page == "product" else 0.0
        row[35] = 1.0 if page == "category" else 0.0
        row[36] = 1.0 if req.device == "ios" else 0.0
        row[37] = 1.0 if req.device == "android" else 0.0
        row[38] = len(ctx.viewed)
        row[39] = 1.0 if req.is_new_user else 0.0
        row[40] = slots[i] if slots is not None else 0.0
    return X


def attach_sub_price(snap: Snapshot) -> None:
    """Median price per subcategory (for relative price features)."""
    by_sub: dict[str, list[float]] = defaultdict(list)
    for p in snap.products.values():
        by_sub[p.sub].append(p.price)
    snap.sub_price = {k: float(np.median(v)) for k, v in by_sub.items()}
