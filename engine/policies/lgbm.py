"""LightGBM policy trained on our live feedback (engine/learn, docs/live_ranker.md).

recommend(): build_context -> generate_candidates -> featurize at slot 0 -> one vectorised predict -> top-10 via fill.
Items the user bought before (snapshot history or purchases during the event) are kept out of the list unless the
model clearly prefers them: their score is divided by ``bought_penalty``, so a bought item only enters the top 10
if it scores at least ``bought_penalty`` times the non-bought item it would displace (``inf`` = always exclude).
"""
from __future__ import annotations

import numpy as np
import hashlib
import json

from ..features import FIDX, build_context, featurize, generate_candidates
from ..calibration import OnlineCalibration, group_multipliers
from ..config import CACHE
from ..learn.scoring import ServingModel
from ..snapshot import Snapshot
from ..types import Request
from .base import K, fill
from .prepare import prepare_snapshot

_BOUGHT_N = FIDX["user_bought_n"]
_BOUGHT_EVENT = FIDX["bought_in_event"]


class LgbmPolicy:
    def __init__(self, name: str, model_path: str, bought_penalty: float = 3.0, pool: int = 3 * K,
                 num_threads: int = 4, use_content: bool = False) -> None:
        """``model_path``: LightGBM text model (relative paths resolve against the project root); its JSON sidecar
        (same stem) selects the serving score (click, purchase or factored click * P(purchase | click)).
        ``num_threads``: LightGBM threads per predict (see ServingModel)."""
        self.name = name
        self.model = ServingModel(model_path, num_threads=num_threads)
        self.bought_penalty = float(bought_penalty)
        self.pool = pool
        self.use_content = use_content
        if self.use_content:
            from ..content import ContentIndex
            self.content_index = ContentIndex.load()
        self.model_id = hashlib.sha256(self.model.path.read_bytes() +
                                      json.dumps(self.model.meta, sort_keys=True).encode()).hexdigest()[:20]
        self.online_calibration = OnlineCalibration()
        self.refresh_feedback()

    def refresh_feedback(self):
        self.online_calibration = OnlineCalibration.load(CACHE / "online_calibration.json", self.model_id)

    def _probabilities(self, req, snap, items, X, slots, online=True):
        p = self.model.score(X)
        subs = [snap.products[pid].sub for pid in items]
        p = np.clip(p * group_multipliers(self.model.meta.get("calibration", {}).get("groups", {}), subs, slots),
                    1e-8, 1 - 1e-8)
        if online:
            p = self.online_calibration.apply(p, subs, slots, req.ts.timestamp())
        return p

    def exposure_metadata(self, req, snap, items):
        ctx = build_context(req, snap)
        slots = list(range(len(items)))
        X = featurize(ctx, snap, items, slots=slots)
        return {"model_id": self.model_id,
                "online_calibration_built_at": self.online_calibration.payload.get("built_at"),
                "base_probabilities": self._probabilities(req, snap, items, X, slots, online=False).tolist(),
                "subcategories": [snap.products[p].sub for p in items]}

    @staticmethod
    def _ensure_ready(snap: Snapshot) -> None:
        """Derived tables the features need. Computed here only when missing: the live runner keeps them fresh
        (refresher: sub_quality every minute; rebuilder: prepare_snapshot), so no request pays for a recompute
        each time the item counters are swapped. Snapshots pickled by an older Snapshot class lack
        ``recent_user_buys`` until the live refresher first sets it; build_context reads it unguarded."""
        if getattr(snap, "sub_price", None) is None or not getattr(snap, "sub_quality", None):
            prepare_snapshot(snap)
        if not hasattr(snap, "recent_user_buys"):
            snap.recent_user_buys = {}

    def score_candidates(self, req: Request, snap: Snapshot) -> tuple[list[str], np.ndarray, np.ndarray]:
        """Candidates, their feature rows (slot 0) and final scores (bought penalty applied)."""
        self._ensure_ready(snap)
        ctx = build_context(req, snap)
        cands = generate_candidates(ctx, snap)
        if self.use_content:
            from ..content import content_candidates, known_at
            index = self.content_index
            cands = list(dict.fromkeys(cands + list(content_candidates(req, snap, index))))
            cands = [p for p in cands if known_at(p, snap, req)]
        if not cands:
            return [], np.zeros((0, 0), dtype=np.float32), np.zeros(0)
        X = featurize(ctx, snap, cands)  # slots=None -> slot feature 0 for every candidate
        s = self._probabilities(req, snap, cands, X, [0] * len(cands))
        if self.bought_penalty > 1.0:
            bought = (X[:, _BOUGHT_N] > 0) | (X[:, _BOUGHT_EVENT] > 0)
            s = np.where(bought, s / self.bought_penalty, s)
        return cands, X, s

    def recommend(self, req: Request, snap: Snapshot) -> list[str]:
        cands, _, s = self.score_candidates(req, snap)
        if not cands:
            return fill([], snap)
        order = np.argsort(-s, kind="stable")[: self.pool]
        return fill([cands[i] for i in order], snap)
