"""Revenue-aware cart-first policy ("money"): rank by expected revenue, not purchase probability alone.

The leaderboard tie-break is revenue per request, and the top practice team ranks by P(buy) x price.
Score = cart-first score x (price / median price) ** alpha, with the price factor bounded so a single
expensive item cannot outrank a much more likely one. Bought items stay hard-excluded (CartFirstPolicy).
"""
from __future__ import annotations

import statistics

from ..snapshot import Snapshot
from ..types import Request
from .base import K, fill
from .cartfirst import CartFirstPolicy


class MoneyPolicy(CartFirstPolicy):
    def __init__(self, name: str = "money-v1", alpha: float = 0.5, lo: float = 0.5, hi: float = 2.5, **kw) -> None:
        super().__init__(name, **kw)
        self.alpha, self.lo, self.hi = alpha, lo, hi
        self._ref: tuple[int, float] | None = None

    def _median_price(self, snap: Snapshot) -> float:
        key = id(snap)
        if self._ref is None or self._ref[0] != key:
            prices = [p.price for p in snap.products.values() if p.active and p.price > 0]
            self._ref = (key, statistics.median(prices) if prices else 1.0)
        return self._ref[1]

    def recommend(self, req: Request, snap: Snapshot) -> list[str]:
        base = super().recommend(req, snap)  # 10 valid, bought items excluded, cart/session first
        # Re-rank a wider pool by expected revenue; keep the cart-first order as the probability proxy.
        pool = base + [p for p in snap.pop_global[:30] if p not in base]
        excluded = set(snap.user_buy.get(req.user_id, {})) | set(getattr(snap, "recent_user_buys", {}).get(req.user_id, ()))
        ref = self._median_price(snap)
        scored = []
        for rank, pid in enumerate(pool):
            p = snap.products.get(pid)
            if p is None or not p.active or pid in excluded:
                continue
            prob = 1.0 / (1.0 + rank) ** 0.6  # decreasing probability proxy from the cart-first ordering
            mult = min(self.hi, max(self.lo, (p.price / ref) if p.price > 0 else 1.0)) ** self.alpha
            scored.append((prob * mult, pid))
        scored.sort(reverse=True)
        out = [pid for _, pid in scored[:K]]
        return fill(out, snap) if len(out) < K else out
