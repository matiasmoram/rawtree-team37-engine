"""Separate content and recent-co-vis candidates; existing winners are unchanged."""
from __future__ import annotations

import threading

from ..content import ContentIndex, borrowed_quality, content_candidates, known_at
from ..recent_covis import RecentCovisIndex
from .evidence import EvidencePolicy


def winner_params(overrides):
    params = {"bought_factor": 0.02, "covis_gain": 0.0,
              "rel": {"user_viewed": 2.5, "same_cat": 0.25, "same_sub": 0.25}}
    params.update(overrides)
    return params


class ContentPolicy(EvidencePolicy):
    def __init__(self, name="ev-content", index: ContentIndex | None = None,
                 content_gain: float = 0.35, prior_strength: float = 30.0, **kwargs):
        super().__init__(name, **winner_params(kwargs))
        if not 0 <= content_gain <= 1 or not 0 <= prior_strength <= 100:
            raise ValueError("content influence must be bounded")
        self.index = index if index is not None else ContentIndex.load()
        self.content_gain = content_gain
        self.prior_strength = prior_strength
        self._tls = threading.local()

    def _signals(self, req, snap):
        # One cache per poller thread; candidate/score hooks share one calculation.
        key = (req.request_id, req.ts, tuple(req.viewed[:4]), id(snap), id(snap.products),
               id(snap.covis_vv), id(snap.covis_vb), id(self.index))
        if getattr(self._tls, "key", None) != key:
            self._tls.signals = content_candidates(req, snap, self.index)
            self._tls.key = key
        return self._tls.signals

    def extra_candidates(self, req, snap):
        return self._signals(req, snap)

    def scored_candidates(self, req, snap):
        return [(score, pid) for score, pid in super().scored_candidates(req, snap)
                if known_at(pid, snap, req)]

    def item_multiplier(self, req, snap, pid):
        # Similarity must never cancel the bought-item penalty or boost known views.
        if (pid in req.viewed or pid in snap.user_buy.get(req.user_id, {})
                or pid in getattr(snap, "recent_user_buys", {}).get(req.user_id, set())):
            return 1.0
        return 1.0 + self.content_gain * self._signals(req, snap).get(pid, 0.0)

    def quality(self, pid, snap, sub_quality):
        base = lambda q: EvidencePolicy.quality(self, q, snap, sub_quality)
        return borrowed_quality(pid, snap, self.index, base, self.prior_strength)


class RecentCovisPolicy(EvidencePolicy):
    def __init__(self, name="ev-recent-covis", index: RecentCovisIndex | None = None,
                 recent_gain: float = 0.35, **kwargs):
        super().__init__(name, **winner_params(kwargs))
        if not 0 <= recent_gain <= 1:
            raise ValueError("recent co-vis influence must be bounded")
        self.index = index if index is not None else RecentCovisIndex.load()
        self.recent_gain = recent_gain
        self._tls = threading.local()

    def _signals(self, req, snap):
        key = (req.request_id, req.ts, tuple(req.viewed[:4]), id(snap), id(snap.products), id(self.index))
        if getattr(self._tls, "key", None) != key:
            self._tls.signals = {q: value for q, value in self.index.candidates(req.viewed, req.ts).items()
                                 if known_at(q, snap, req)}
            self._tls.key = key
        return self._tls.signals

    def extra_candidates(self, req, snap):
        return self._signals(req, snap)

    def scored_candidates(self, req, snap):
        return [(score, pid) for score, pid in super().scored_candidates(req, snap)
                if known_at(pid, snap, req)]

    def item_multiplier(self, req, snap, pid):
        if (pid in req.viewed or pid in snap.user_buy.get(req.user_id, {})
                or pid in getattr(snap, "recent_user_buys", {}).get(req.user_id, set())):
            return 1.0
        return 1.0 + self.recent_gain * self._signals(req, snap).get(pid, 0.0)
