"""One-idea variants of the cart-first policy for the experiment shard (owned by session datathon-d1).

Each arm changes exactly one thing against the `cf-v1` control, so a difference in the per-model
leaderboard can be attributed to that idea.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from ..types import Request
from .cartfirst import CartFirstPolicy


class RotateLastView:
    """Show earlier session views before the last one (live: earlier view at slot 1 converted 2.08% vs 0.66%).

    Implemented by moving the most recent view to the oldest position before calling the inner policy.
    """

    def __init__(self, inner, name: str) -> None:
        self.inner = inner
        self.name = name
        self.use_content = getattr(inner, "use_content", False)

    def __getattr__(self, attr):  # content_index / refresh_content are forwarded to the inner policy
        return getattr(self.inner, attr)

    def recommend(self, req: Request, snap):
        if len(req.recent_views) >= 2:
            views = sorted(req.recent_views, key=lambda v: v[1])
            last_pid, last_ts = views[-1]
            oldest = views[0][1] - timedelta(seconds=1)
            rotated = [(last_pid, oldest)] + [v for v in views[:-1] if v[0] != last_pid]
            req = replace(req, recent_views=rotated)
        return self.inner.recommend(req, snap)


VARIANTS = {
    "cf-rot": lambda: RotateLastView(CartFirstPolicy("cf-rot-inner"), "cf-rot"),
    "cf-sess": lambda: CartFirstPolicy("cf-sess", tiers={"session": 1.5}),
    "cf-aff4": lambda: CartFirstPolicy("cf-aff4", tiers={"affinity": 0.4}),
    "cf-nocontent": lambda: CartFirstPolicy("cf-nocontent", content_gain=0.0),
}
