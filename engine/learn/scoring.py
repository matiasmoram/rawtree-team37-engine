"""Scoring shared by the training report and the serving policy (no training dependencies).

A saved model is a LightGBM text file plus an optional JSON sidecar with the same stem (``<stem>.json``) that
says how to turn the booster output into the serving score:

- ``kind = "click"``: score = P(click | x, slot=0)
- ``kind = "purchase"``: score = P(purchase | x, slot=0)
- ``kind = "factored"``: score = P(click | x, slot=0) * P(purchase | click, x), the second factor given by ``pc``:
  ``{"kind": "rate", "p": r}`` (constant) or ``{"kind": "logreg", "mu", "sd", "w", "b", "clip"}`` (z-scored,
  clipped features, logistic link).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import lightgbm as lgb
import numpy as np

from ..config import ROOT
from ..features import FEATURES


def pc_predict(pc: dict | None, X: np.ndarray) -> np.ndarray:
    """P(purchase | click, x) from the exported second-stage model."""
    if not pc:
        return np.ones(len(X))
    if pc["kind"] == "rate":
        return np.full(len(X), float(pc["p"]))
    if pc["kind"] == "logreg":
        mu, sd, w = (np.asarray(pc[k], dtype=np.float64) for k in ("mu", "sd", "w"))
        z = np.clip((X.astype(np.float64) - mu) / sd, -pc["clip"], pc["clip"])
        return 1.0 / (1.0 + np.exp(-(z @ w + float(pc["b"]))))
    raise ValueError(f"unknown pc model kind {pc['kind']}")


def resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


class ServingModel:
    """Booster + sidecar, loaded once. ``score`` is thread-safe and expects rows in ``FEATURES`` order."""

    def __init__(self, model_path: str | Path, num_threads: int = 4) -> None:
        """``num_threads``: OpenMP threads per predict. Single-threaded LightGBM costs ~50 us per row with ~500
        trees (6-7 ms for 120 candidates); 4 threads bring it to ~2 ms. Calls are serialised by a lock."""
        self.num_threads = num_threads
        self.path = resolve(model_path)
        self.booster = lgb.Booster(model_file=str(self.path))
        names = self.booster.feature_name()
        if names != FEATURES:
            raise ValueError(f"model features differ from engine.features.FEATURES: {set(names) ^ set(FEATURES)}")
        sidecar = self.path.with_suffix(".json")
        self.meta: dict = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
        serving = self.meta.get("serving", {})
        self.kind: str = serving.get("kind", "booster")
        self.pc: dict | None = serving.get("pc") if self.kind == "factored" else None
        self._lock = threading.Lock()

    def score(self, X: np.ndarray) -> np.ndarray:
        with self._lock:
            p = self.booster.predict(X, num_threads=self.num_threads)
        if self.kind == "factored":
            p = p * pc_predict(self.pc, X)
        return p
