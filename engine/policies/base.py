"""Policy interface and reference policies used as sanity anchors by the evaluators."""
from __future__ import annotations

from typing import Protocol

from ..snapshot import Snapshot
from ..types import Request

K = 10


class Policy(Protocol):
    name: str

    def recommend(self, req: Request, snap: Snapshot) -> list[str]:
        """Return exactly K distinct product ids that are active in snap."""
        ...


def fill(items: list[str], snap: Snapshot, k: int = K) -> list[str]:
    """Deduplicate, drop inactive ids, and top up with global best sellers so the answer is always valid."""
    out: list[str] = []
    seen: set[str] = set()
    for pid in list(items) + snap.pop_global:
        if pid not in seen and snap.is_valid(pid):
            seen.add(pid)
            out.append(pid)
            if len(out) == k:
                break
    return out


class GlobalBestSellers:
    """The official baseline: all-time best sellers that are in stock, same list for everybody."""

    name = "ref-global-bestsellers"

    def recommend(self, req: Request, snap: Snapshot) -> list[str]:
        ranked = sorted(snap.stats, key=lambda p: (snap.stats[p]["buy_all"], p), reverse=True)
        return fill(ranked[:50], snap)


class LastViewCategoryBestSellers:
    """Imitates the old logged policy (without its randomness): best sellers of the last viewed product's category."""

    name = "ref-lastview-category"

    def recommend(self, req: Request, snap: Snapshot) -> list[str]:
        viewed = req.viewed
        if viewed and viewed[0] in snap.products:
            return fill(snap.pop_by_cat.get(snap.products[viewed[0]].cat, []), snap)
        return fill(snap.pop_global, snap)
