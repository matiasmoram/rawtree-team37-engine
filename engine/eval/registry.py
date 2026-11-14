"""Policy registry for the evaluators: name -> zero-argument factory returning a fresh policy.

To evaluate a new policy, import it here and add one line to ``POLICIES`` (see the marked section below).
A policy is any object with a ``name`` attribute and ``recommend(req, snap) -> list[str]`` (10 active product ids).
"""
from __future__ import annotations

from typing import Callable

from ..policies.base import GlobalBestSellers, LastViewCategoryBestSellers, Policy
from ..policies.prepare import Prepared
from ..policies.evidence import EvidencePolicy
from ..snapshot import Snapshot
from ..types import Request
from .stats import BASELINE


class SnapshotConstant:
    """Speed wrapper for a policy whose answer depends only on the snapshot, never on the request.

    ``GlobalBestSellers`` re-sorts every product on each call (~7 ms); the evaluators call it tens of thousands of
    times with the same snapshot. The wrapped answer is identical, it is just computed once per snapshot object.
    Only wrap policies that ignore ``req`` entirely, otherwise results would be wrong.
    """

    def __init__(self, inner: Policy) -> None:
        self.inner = inner
        self.name = inner.name
        self._key: tuple | None = None
        self._items: list[str] = []

    def recommend(self, req: Request, snap: Snapshot) -> list[str]:
        key = (id(snap), snap.T)
        if key != self._key:
            self._items = list(self.inner.recommend(req, snap))
            self._key = key
        return list(self._items)


POLICIES: dict[str, Callable[[], Policy]] = {
    # Reference anchors (do not remove: the baseline is used for every lift).
    "ref-global-bestsellers": lambda: SnapshotConstant(GlobalBestSellers()),
    "ref-lastview-category": LastViewCategoryBestSellers,
    # ---- register new policies below ------------------------------------------------------------------------
    "ev-v1": lambda: Prepared(EvidencePolicy("ev-v1")),
    # "my-policy": MyPolicy,                      # from ..policies.my_module import MyPolicy
    # "my-policy-tuned": lambda: MyPolicy(alpha=0.3),
}


def make_policies(names: list[str]) -> list[Policy]:
    """Instantiate policies by registry name; the baseline is always included (first) so lifts can be computed."""
    unknown = [n for n in names if n not in POLICIES]
    if unknown:
        raise KeyError(f"unknown policies {unknown}; registered: {sorted(POLICIES)}")
    ordered = [BASELINE] + [n for n in names if n != BASELINE]
    return [POLICIES[n]() for n in ordered]
