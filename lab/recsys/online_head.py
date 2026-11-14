"""P2: bounded online contextual correction on top of frozen A (V2 plan §3).

Choice model over the DISPLAYED slate with a no-purchase alternative:

    p_k        = A's P(click at displayed slot k) * P(buy | click)        (frozen LightGBM)
    u_k        = log p_k + clip(theta . phi_k, -D, D)
    u_0        = log(1 - sum_k p_k)                                        (no purchase)
    P(Y = k)   = exp(u_k) / (exp(u_0) + sum_j exp(u_j))

With theta = 0 this gives P(Y = k) = p_k exactly, i.e. A's own probabilities. theta is learned by SGD on
-log P(observed choice) + L2 * |theta|^2 from finalised feedback, one update per request_id, in time order.
Only displayed items enter the likelihood; organic purchases are never used as rewards.
At ranking time the correction is added to A's slot-0 log-score: rank by log p_A + clip(theta . phi).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import Config
from .features import Requests, Store

STATE = Path(__file__).resolve().parent.parent / "models" / "online_head.json"

# compact, stable, shared features (no item / user IDs)
PHI = ["last_cat", "s_cat_share", "last_sub", "coview", "u_cat_share", "bought", "in_views",
       "new_item", "logprice", "price_vs_user", "price_vs_last", "trend", "known_user", "i_logp", "home"]


def phi(S: Store, X: np.ndarray, R: Requests | None = None, ri: np.ndarray | None = None) -> np.ndarray:
    F = S.FEATURES
    col = lambda n: X[:, F.index(n)]
    cols = []
    for n in PHI:
        if n == "home":
            v = (col("page") == 0).astype(float)
        elif n == "coview":
            v = np.minimum(col("coview") * 10, 3)
        elif n in ("price_vs_user", "price_vs_last"):
            v = np.nan_to_num(col(n), nan=0.0).clip(-3, 3)
        elif n == "logprice":
            v = col(n) - 3.0
        elif n == "trend":
            v = np.log(np.maximum(col(n), 1e-3)).clip(-2, 2)
        elif n == "i_logp":
            v = (col(n) - 6.0) / 2
        elif n == "u_cat_share":
            v = col(n) * 3
        else:
            v = col(n)
        cols.append(np.nan_to_num(v.astype(float)))
    return np.column_stack(cols)


@dataclass
class OnlineHead:
    cfg: Config
    theta: np.ndarray = field(default_factory=lambda: np.zeros(len(PHI)))
    n_updates: int = 0
    seen: set = field(default_factory=set)

    def delta(self, P: np.ndarray) -> np.ndarray:
        if not self.cfg.USE_ONLINE_CORRECTION or self.n_updates < self.cfg.MIN_FINAL_FEEDBACK:
            return np.zeros(len(P))
        return np.clip(P @ self.theta, -self.cfg.MAX_ONLINE_CORRECTION, self.cfg.MAX_ONLINE_CORRECTION)

    @staticmethod
    def slate_probs(p: np.ndarray, d: np.ndarray) -> tuple[np.ndarray, float]:
        """Choice probabilities for one slate (items, no-purchase)."""
        p = np.clip(p, 1e-7, 0.5)
        p0 = max(1.0 - p.sum(), 1e-3)
        e = p * np.exp(d)
        z = p0 + e.sum()
        return e / z, p0 / z

    def nll(self, p: np.ndarray, P: np.ndarray, chosen: int, use_theta: bool = True) -> float:
        d = np.clip(P @ self.theta, -self.cfg.MAX_ONLINE_CORRECTION, self.cfg.MAX_ONLINE_CORRECTION) if use_theta else 0 * p
        pk, p0 = self.slate_probs(p, d)
        return -np.log(pk[chosen] if chosen >= 0 else p0)

    def update(self, request_id: str, p: np.ndarray, P: np.ndarray, chosen: int) -> bool:
        """One SGD step for one finalised feedback event. Returns False if already processed."""
        if request_id in self.seen:
            return False
        self.seen.add(request_id)
        raw = P @ self.theta
        D = self.cfg.MAX_ONLINE_CORRECTION
        d = np.clip(raw, -D, D)
        pk, _ = self.slate_probs(p, d)
        y = np.zeros(len(p))
        if chosen >= 0:
            y[chosen] = 1
        active = (np.abs(raw) < D).astype(float)            # no gradient through the clip
        g = ((pk - y) * active) @ P + 2 * self.cfg.ONLINE_L2 * self.theta
        n = np.linalg.norm(g)
        if n > self.cfg.GRAD_CLIP:
            g *= self.cfg.GRAD_CLIP / n
        self.theta -= self.cfg.ONLINE_LEARNING_RATE * g
        self.n_updates += 1
        return True

    # --------------------------------------------------------------- persistence (atomic)
    def save(self, path: Path = STATE) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"theta": self.theta.tolist(), "phi": PHI, "n_updates": self.n_updates,
                                   "seen": sorted(self.seen)}))
        tmp.replace(path)

    @classmethod
    def load(cls, cfg: Config, path: Path = STATE) -> "OnlineHead":
        if not path.exists():
            return cls(cfg)
        s = json.loads(path.read_text())
        if s.get("phi") != PHI:   # feature definition changed -> start from A
            return cls(cfg)
        return cls(cfg, np.array(s["theta"]), s["n_updates"], set(s["seen"]))
