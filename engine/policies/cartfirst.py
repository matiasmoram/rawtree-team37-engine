"""M1 - cart-first policy: carts, then session views, then quality-ranked fill. Bought items are never shown.

Sources, each with a relative weight (a tier), multiplied by item quality (shrunk conversion, bounded):
    cart     the user's carted-not-bought items          live ~5.9 permille vs 0.7 for ordinary items (REVIEW Q18)
    session  items in the request's recent_views         ~10x ordinary items in history (REVIEW Q13)
    sub      popular items of the session's subcategories
    affinity popular items of the user's top subcategories
    context  trending / global popular items (new users, home page)
Carts are capped (`cart_cap`) because lists with many cart items were never tested live (REVIEW risk table).
Hard exclusion: every item the user ever bought (history + live) and items bought during the event.
No exploration: `explore_slots` stays 0 unless an experiment arm sets it.
"""
from __future__ import annotations

import math
from datetime import timedelta

from ..snapshot import Snapshot
from ..types import Request
from .base import K, fill
from .evidence import EvidencePolicy

TIERS = {"cart": 1.2, "session": 1.0, "sub": 0.30, "affinity": 0.20, "context": 0.10}


class CartFirstPolicy:
    def __init__(self, name: str = "cf-v1", cart_cap: int = 6, tiers: dict[str, float] | None = None,
                 cart_half_life_days: float = 14.0, new_item_boost: float = 1.0, session_cap: int = 4) -> None:
        self.name = name
        self.cart_cap = cart_cap
        self.session_cap = session_cap
        self.tiers = {**TIERS, **(tiers or {})}
        self.cart_half_life_days = cart_half_life_days
        self.new_item_boost = new_item_boost
        self._q = EvidencePolicy(name + "-q")  # reuse the bounded smoothed quality estimate

    # ------------------------------------------------------------------------------------------
    def recommend(self, req: Request, snap: Snapshot) -> list[str]:
        products = snap.products
        user = req.user_id
        excluded = set(snap.user_buy.get(user, {})) | set(getattr(snap, "recent_user_buys", {}).get(user, ()))
        sub_quality = getattr(snap, "sub_quality", {})

        def q(pid: str) -> float:
            return self._q.quality(pid, snap, sub_quality)

        def ok(pid: str) -> bool:
            p = products.get(pid)
            return p is not None and p.active and pid not in excluded

        viewed = [p for p in req.viewed if ok(p)]
        sess_subs = [products[p].sub for p in req.viewed if p in products]
        sub_weight: dict[str, float] = {}
        for k, s in enumerate(sess_subs):
            sub_weight[s] = sub_weight.get(s, 0.0) + 0.7 ** k

        scores: dict[str, tuple[float, str]] = {}

        def offer(pid: str, tier: str, extra: float = 1.0) -> None:
            if not ok(pid):
                return
            p = products[pid]
            s = self.tiers[tier] * q(pid) * extra
            if p.is_new:
                s *= self.new_item_boost
            if pid not in scores or s > scores[pid][0]:
                scores[pid] = (s, tier)

        # 1. carts, newest first, mild recency decay, session-subcategory match
        carts = getattr(snap, "user_cart", {}).get(user, {})
        ranked_carts = []
        for pid, ts in carts.items():
            if not ok(pid):
                continue
            age_days = max(0.0, (req.ts - ts).total_seconds() / 86400.0)
            decay = 0.5 ** (age_days / self.cart_half_life_days)
            match = 1.5 if products[pid].sub in sub_weight else 1.0
            ranked_carts.append((self.tiers["cart"] * q(pid) * (0.5 + 0.5 * decay) * match, pid))
        ranked_carts.sort(reverse=True)
        for s, pid in ranked_carts[: self.cart_cap]:
            scores[pid] = (s, "cart")

        # 2. session views not bought, most recent first
        for k, pid in enumerate(viewed[: self.session_cap]):
            offer(pid, "session", 0.85 ** k)

        # 3. fill: same subcategory, user's top subcategories, context
        for sub in sorted(sub_weight, key=sub_weight.get, reverse=True)[:3]:
            for pid in snap.pop_by_sub.get(sub, [])[:20]:
                offer(pid, "sub", sub_weight[sub])
        usub = snap.user_sub.get(user, {})
        total = sum(usub.values()) or 1.0
        for sub in sorted(usub, key=usub.get, reverse=True)[:3]:
            for pid in snap.pop_by_sub.get(sub, [])[:10]:
                offer(pid, "affinity", 0.5 + usub[sub] / total)
        for pid in snap.trending[:15]:
            offer(pid, "context", min(2.0, max(0.7, snap.trend_lift(pid))) ** 0.5)
        for pid in snap.pop_global[:40]:
            offer(pid, "context")

        ordered = [pid for pid, _ in sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))]
        out = self._finalize(ordered, snap, excluded)
        return out

    @staticmethod
    def _finalize(ordered: list[str], snap: Snapshot, excluded: set[str]) -> list[str]:
        """Take K items; top up only from the global list *without* excluded items, then validate."""
        items = list(ordered)
        if len(items) < K:
            items += [p for p in snap.pop_global if p not in excluded]
        out = [p for p in fill(items, snap, K) if p not in excluded]
        if len(out) < K:  # fill() may have re-added an excluded id from its own fallback: refill without them
            pool = [p for p in snap.pop_global if p not in excluded and p not in out and snap.is_valid(p)]
            out += pool[: K - len(out)]
        return out[:K]
