"""Evidence policy (v1): candidate generation from several sources + an interpretable score.

The score approximates "probability of a purchase if shown in a top slot" and is anchored on rates
measured in the logged carousel impressions (per shown item):
    item is the last viewed product            2.35 %
    item viewed earlier in the session         1.78 %
    user bought the item before (organic)      1.66 %
    user viewed the item before (not bought)   0.12 %
    same subcategory as the session            0.20 %
    same category as the session               0.135 %
    nothing in common                          0.058 %
Those relation rates are multiplied by item quality (smoothed conversion), co-visitation strength,
user affinity, trend and price fit. Every multiplier is bounded so no single signal dominates.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ..snapshot import Snapshot
from ..types import Request
from .base import K, fill

EVENT_START = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)

REL_LAST_VIEW = 2.35
REL_EARLIER_VIEW = 1.78
REL_BOUGHT = 1.66
REL_USER_VIEWED = 0.12
REL_SAME_SUB = 0.20
REL_SAME_CAT = 0.135
REL_NONE = 0.058

CAROUSEL_MEAN = 28053 / 20_000_000      # purchases per shown item in the logged carousel
ORGANIC_MEAN = 548160 / 10354047        # organic purchases per view


class EvidencePolicy:
    def __init__(self, name: str = "ev-v1", recent_buy_factor: float = 0.25, covis_gain: float = 3.0,
                 affinity_gain: float = 1.5, max_views_used: int = 6, rel: dict[str, float] | None = None,
                 bought_factor: float | None = None) -> None:
        """`rel` overrides relation rates; `bought_factor` (if set) multiplies any item the user bought before,
        instead of treating "bought before" as a positive relation (live feedback: bought items lose appeal)."""
        self.name = name
        self.rel = {"last_view": REL_LAST_VIEW, "earlier_view": REL_EARLIER_VIEW, "bought": REL_BOUGHT,
                    "user_viewed": REL_USER_VIEWED, "same_sub": REL_SAME_SUB, "same_cat": REL_SAME_CAT, "none": REL_NONE}
        self.rel.update(rel or {})
        self.bought_factor = bought_factor
        self.recent_buy_factor = recent_buy_factor
        self.covis_gain = covis_gain
        self.affinity_gain = affinity_gain
        self.max_views_used = max_views_used

    # ---- item quality ---------------------------------------------------------------
    def quality(self, pid: str, snap: Snapshot, sub_quality: dict[str, float]) -> float:
        """Smoothed conversion relative to the average item, bounded to [0.4, 3]."""
        shown, _, buys = snap.carousel.get(pid, (0, 0, 0))
        s = snap.stats.get(pid)
        q_car = (buys + 500 * CAROUSEL_MEAN) / (shown + 500) / CAROUSEL_MEAN
        if s and s["view_all"] > 0:
            q_org = (s["buy_all"] + 50 * ORGANIC_MEAN) / (s["view_all"] + 50) / ORGANIC_MEAN
        else:
            p = snap.products.get(pid)
            q_org = sub_quality.get(p.sub, 1.0) if p else 1.0
        q = math.sqrt(q_car * q_org) if shown > 0 else q_org
        return min(3.0, max(0.4, q))

    # ---- main entry -----------------------------------------------------------------
    def recommend(self, req: Request, snap: Snapshot) -> list[str]:
        products = snap.products
        viewed = [p for p in req.viewed if p in products][: self.max_views_used]
        user = req.user_id
        ubuy = snap.user_buy.get(user, {})
        uview = snap.user_view.get(user, {})
        usub = snap.user_sub.get(user, {})
        recent_buys = getattr(snap, "recent_user_buys", {}).get(user, set())

        sess_subs: dict[str, float] = defaultdict(float)
        sess_cats: dict[str, float] = defaultdict(float)
        for k, pid in enumerate(viewed):
            p = products[pid]
            sess_subs[p.sub] += 0.7 ** k
            sess_cats[p.cat] += 0.7 ** k

        # ---- candidates ----
        cand: set[str] = set(viewed)
        covis: dict[str, float] = defaultdict(float)
        for k, pid in enumerate(viewed[:4]):
            decay = 0.7 ** k
            for table, weight in ((snap.covis_vb, 1.0), (snap.covis_vv, 0.5)):
                neigh = table.get(pid, [])[:25]
                if not neigh:
                    continue
                top = neigh[0][1] or 1.0
                for q, w in neigh:
                    covis[q] += decay * weight * w / top
                    cand.add(q)
        if ubuy:
            cand.update(sorted(ubuy, key=lambda p: ubuy[p][1], reverse=True)[:20])
        if uview:
            cand.update(sorted(uview, key=lambda p: uview[p][0], reverse=True)[:10])
        for sub in sorted(sess_subs, key=sess_subs.get, reverse=True)[:3]:
            cand.update(snap.pop_by_sub.get(sub, [])[:20])
        if viewed:
            cand.update(snap.pop_by_cat.get(products[viewed[0]].cat, [])[:15])
        top_user_subs = sorted(usub, key=usub.get, reverse=True)[:3]
        for sub in top_user_subs:
            cand.update(snap.pop_by_sub.get(sub, [])[:10])
        cand.update(snap.trending[:20])
        cand.update(snap.pop_global[:20])
        for pid, p in products.items():
            if p.is_new and p.active and p.sub in sess_subs:
                cand.add(pid)

        usub_total = sum(usub.values()) or 1.0
        user_price = snap.user_price.get(user)
        sub_quality = getattr(snap, "sub_quality", {})
        view_rank = {pid: k for k, pid in enumerate(viewed)}

        scored: list[tuple[float, str]] = []
        for pid in cand:
            p = products.get(pid)
            if p is None or not p.active:
                continue
            # relation to this session / user
            R = self.rel
            bought = pid in ubuy
            if pid in view_rank:
                k = view_rank[pid]
                rel = R["last_view"] if k == 0 else R["earlier_view"] * 0.85 ** (k - 1)
            elif bought and self.bought_factor is None:
                rel = R["bought"]
            elif pid in uview:
                rel = R["user_viewed"] * (1 + 0.2 * math.log1p(uview[pid][0]))
            elif p.sub in sess_subs:
                rel = R["same_sub"]
            elif p.cat in sess_cats:
                rel = R["same_cat"]
            else:
                rel = R["none"]
            if bought and self.bought_factor is not None:
                rel *= self.bought_factor
            score = rel * self.quality(pid, snap, sub_quality)
            if pid not in view_rank and (pid not in uview or self.bought_factor is None):
                # co-visitation is a discovery signal: v2 policies do not let it lift items the user already knows
                score *= 1 + self.covis_gain * min(covis.get(pid, 0.0), 1.5)
            if usub:
                score *= 1 + self.affinity_gain * usub.get(p.sub, 0.0) / usub_total
            score *= min(2.0, max(0.7, snap.trend_lift(pid))) ** 0.5
            if user_price and p.price > 0:
                score *= math.exp(-0.25 * abs(math.log(p.price / user_price)))
            if pid in recent_buys:
                score *= self.recent_buy_factor
            scored.append((score, pid))

        scored.sort(reverse=True)
        return fill([pid for _, pid in scored[: K * 3]], snap)


def attach_sub_quality(snap: Snapshot) -> None:
    """Average organic conversion per subcategory, used as the prior for products without history."""
    agg: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for pid, s in snap.stats.items():
        p = snap.products.get(pid)
        if p:
            agg[p.sub][0] += s["buy_all"]
            agg[p.sub][1] += s["view_all"]
    snap.sub_quality = {sub: min(3.0, max(0.4, (b + 50 * ORGANIC_MEAN) / (v + 50) / ORGANIC_MEAN)) for sub, (b, v) in agg.items()}
