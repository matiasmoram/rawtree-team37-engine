"""Derived snapshot tables that policies rely on, computed once per snapshot object."""
from __future__ import annotations

from ..features import attach_sub_price
from ..snapshot import Snapshot
from .evidence import attach_sub_quality


def prepare_snapshot(snap: Snapshot) -> None:
    if getattr(snap, "_prepared_id", None) == id(snap.stats):
        return
    attach_sub_quality(snap)
    attach_sub_price(snap)
    snap._prepared_id = id(snap.stats)


class Prepared:
    """Wrap a policy so the snapshot's derived tables exist before it is called (evaluators)."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.name = inner.name

    def recommend(self, req, snap):
        prepare_snapshot(snap)
        return self.inner.recommend(req, snap)
