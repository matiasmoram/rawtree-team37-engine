"""Isolated context/trend challenger. The nocovis winner is unchanged."""
from __future__ import annotations

import threading

from ..content import known_at
from ..contextual import ContextIndex
from .evidence import EvidencePolicy


class ContextualPolicy(EvidencePolicy):
    def __init__(self, name="ev-context", index=None, context_gain=.35, trend_gain=.25, **kwargs):
        params = {"bought_factor": .02, "covis_gain": 0., "rel": {"user_viewed": 1.5}}
        params.update(kwargs)
        super().__init__(name, **params)
        if not 0 <= context_gain <= 1 or not 0 <= trend_gain <= 1:
            raise ValueError("context and trend gains must be bounded")
        self.index = index if index is not None else ContextIndex.load()
        self.context_gain = context_gain
        self.trend_gain = trend_gain
        self._tls = threading.local()

    def refresh_context(self):
        """Call outside request handling when the background artifact is refreshed."""
        self.index = ContextIndex.load()

    def _context_signals(self, req, snap):
        if req.viewed and not req.is_new_user:
            return {}
        key = (req.request_id, req.ts, req.device, req.region, id(self.index), id(snap.products))
        if getattr(self._tls, "key", None) != key:
            rows, _ = self.index.context(req)
            top = rows[0][1] if rows else 1.
            bought = set(snap.user_buy.get(req.user_id, {})) | set(
                getattr(snap, "recent_user_buys", {}).get(req.user_id, set()))
            self._tls.signals = {pid: min(1., value / top) for pid, value in rows[:60]
                                 if known_at(pid, snap, req) and pid not in bought}
            self._tls.key = key
        return self._tls.signals

    def extra_candidates(self, req, snap):
        return self._context_signals(req, snap)

    def scored_candidates(self, req, snap):
        return [(score, pid) for score, pid in super().scored_candidates(req, snap)
                if known_at(pid, snap, req)]

    def item_multiplier(self, req, snap, pid):
        # Context/popularity cannot cancel either known preference or repurchase penalties.
        if (pid in req.viewed or pid in snap.user_view.get(req.user_id, {})
                or pid in snap.user_buy.get(req.user_id, {})
                or pid in getattr(snap, "recent_user_buys", {}).get(req.user_id, set())):
            return 1.
        p = snap.products[pid]
        context = 1. + self.context_gain * self._context_signals(req, snap).get(pid, 0.)
        trend = self.index.trend(p.sub, p.brand, req.ts) ** self.trend_gain
        return min(2., max(.5, context * trend))
