"""LightGBM policy trained on our live feedback (engine/learn, docs/live_ranker.md).

recommend(): build_context -> generate_candidates -> featurize at slot 0 -> one vectorised predict -> top-10 via fill.
Items the user bought before (snapshot history or purchases during the event) are kept out of the list unless the
model clearly prefers them: their score is divided by ``bought_penalty``, so a bought item only enters the top 10
if it scores at least ``bought_penalty`` times the non-bought item it would displace (``inf`` = always exclude).
"""
from __future__ import annotations

import numpy as np

from ..features import FIDX, build_context, featurize, generate_candidates
from ..learn.scoring import ServingModel
from ..snapshot import Snapshot
from ..types import Request
from .base import K, fill
from .prepare import prepare_snapshot

_BOUGHT_N = FIDX["user_bought_n"]
_BOUGHT_EVENT = FIDX["bought_in_event"]


class LgbmPolicy:
    def __init__(self, name: str, model_path: str, bought_penalty: float = 3.0, pool: int = 3 * K) -> None:
        """``model_path``: LightGBM text model (relative paths resolve against the project root); its JSON sidecar
        (same stem) selects the serving score (click, purchase or factored click * P(purchase | click))."""
        self.name = name
        self.model = ServingModel(model_path)
        self.bought_penalty = float(bought_penalty)
        self.pool = pool

    def score_candidates(self, req: Request, snap: Snapshot) -> tuple[list[str], np.ndarray, np.ndarray]:
        """Candidates, their feature rows (slot 0) and final scores (bought penalty applied)."""
        prepare_snapshot(snap)
        ctx = build_context(req, snap)
        cands = generate_candidates(ctx, snap)
        if not cands:
            return [], np.zeros((0, 0), dtype=np.float32), np.zeros(0)
        X = featurize(ctx, snap, cands)  # slots=None -> slot feature 0 for every candidate
        s = self.model.score(X)
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
