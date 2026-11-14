"""Bayesian logistic regression with a Gaussian (Laplace) posterior, updated sequentially (Chapelle & Li 2011, Alg. 3,
with full precision instead of diagonal) + diagonal per-item offsets.

Each update treats the current posterior N(m, P^-1) as the prior, finds the MAP by Newton and takes the Hessian
there as the new precision. Thompson sampling draws w ~ N(m, P^-1).
"""
from __future__ import annotations

import copy
import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))


def _map(X, y, m, P, offset=None, iters=20):
    """MAP under prior N(m, P^-1); returns (w, posterior precision = Hessian at the MAP)."""
    w = m.copy()
    off = 0 if offset is None else offset
    for _ in range(iters):
        p = sigmoid(X @ w + off)
        g = X.T @ (y - p) - P @ (w - m)
        H = (X * (p * (1 - p))[:, None]).T @ X + P
        step = np.linalg.solve(H, g)
        w = w + step
        if np.abs(step).max() < 1e-6:
            break
    p = sigmoid(X @ w + off)
    return w, (X * (p * (1 - p))[:, None]).T @ X + P


class BayesLogit:
    """Gaussian posterior N(m, P^-1) with full precision P (dims are small; the slot one-hots and the bias
    are collinear, so a diagonal posterior would bias sequential updates)."""

    def __init__(self, dim: int, prior_var: float = 1.0):
        self.dim = dim
        self.q0 = 1.0 / prior_var
        self.P0 = np.eye(dim) * self.q0
        self.m = np.zeros(dim)
        self.P = self.P0.copy()

    @property
    def q(self) -> np.ndarray:
        """Diagonal of the precision (for logging)."""
        return np.diag(self.P).copy()

    def std(self) -> np.ndarray:
        return np.sqrt(np.diag(np.linalg.inv(self.P)))

    def fit(self, X, y, iters: int = 20, offset=None) -> bool:
        """Batch MAP from the prior (resets the posterior)."""
        self.m, self.P = np.zeros(self.dim), self.P0.copy()
        return self.update(X, y, iters=iters, offset=offset)

    def update(self, X, y, iters: int = 20, offset=None) -> bool:
        X, y = np.asarray(X, float), np.asarray(y, float)
        if not len(y):
            return True
        if not (np.isfinite(X).all() and np.isfinite(y).all()) or (offset is not None and not np.isfinite(offset).all()):
            return False
        try:
            m, P = _map(X, y, self.m, self.P, offset, iters)
            np.linalg.cholesky(P)
        except np.linalg.LinAlgError:
            return False
        if not (np.isfinite(m).all() and np.isfinite(P).all()):
            return False
        self.m, self.P = m, P
        return True

    def decay(self, factor: float):
        """Forget toward the prior: P <- factor * P + (1 - factor) * P0."""
        self.P = factor * self.P + (1 - factor) * self.P0

    def sample(self, rng) -> np.ndarray:
        L = np.linalg.cholesky(self.P)               # P = L L^T  ->  w = m + L^-T z
        return self.m + np.linalg.solve(L.T, rng.normal(size=self.dim))

    def clip_to(self, anchor: "BayesLogit", k: float = 4):
        r = k * anchor.std()
        self.m = np.clip(self.m, anchor.m - r, anchor.m + r)

    def copy(self) -> "BayesLogit":
        return copy.deepcopy(self)


class ItemOffsets:
    """Per-item logit offsets u_i ~ N(m_i, 1/q_i), prior N(0, sigma^2). Unknown items -> 0."""

    def __init__(self, sigma: float = 0.5):
        self.q0 = 1.0 / sigma ** 2
        self.m: dict[int, float] = {}
        self.q: dict[int, float] = {}

    def update(self, items, base_logit, y, iters: int = 8) -> bool:
        items, base_logit, y = np.asarray(items, int), np.asarray(base_logit, float), np.asarray(y, float)
        if not len(items):
            return True
        if not (np.isfinite(base_logit).all() and np.isfinite(y).all()):
            return False
        uniq, inv = np.unique(items, return_inverse=True)
        m0 = np.array([self.m.get(int(i), 0.0) for i in uniq])
        q0 = np.array([self.q.get(int(i), self.q0) for i in uniq])
        u = m0.copy()
        for _ in range(iters):
            p = sigmoid(base_logit + u[inv])
            g = np.bincount(inv, y - p, len(uniq)) - q0 * (u - m0)
            h = np.bincount(inv, p * (1 - p), len(uniq)) + q0
            u = u + g / h
        p = sigmoid(base_logit + u[inv])
        q = q0 + np.bincount(inv, p * (1 - p), len(uniq))
        if not (np.isfinite(u).all() and np.isfinite(q).all()):
            return False
        for i, a, b in zip(uniq.tolist(), u, q):
            self.m[i], self.q[i] = float(a), float(b)
        return True

    def decay(self, factor: float):
        self.q = {i: max(v * factor, self.q0) for i, v in self.q.items()}

    def mean(self, items) -> np.ndarray:
        return np.array([self.m.get(int(i), 0.0) for i in np.asarray(items)])

    def sample_all(self, rng) -> dict[int, float]:
        keys = list(self.m)
        if not keys:
            return {}
        m = np.array([self.m[i] for i in keys])
        s = 1 / np.sqrt(np.array([self.q[i] for i in keys]))
        return dict(zip(keys, (m + rng.normal(size=len(keys)) * s).tolist()))


@dataclass
class Draw:
    wc: np.ndarray
    wb: np.ndarray
    offsets: dict = field(default_factory=dict)
    id: int = 0

    def item_offset(self, items) -> np.ndarray:
        return np.array([self.offsets.get(int(i), 0.0) for i in np.asarray(items)])


def p_buy(draw: Draw, Xc, Xb, items) -> np.ndarray:
    return sigmoid(Xc @ draw.wc + draw.item_offset(items)) * sigmoid(Xb @ draw.wb)


class Posterior:
    def __init__(self, click: BayesLogit, buy: BayesLogit, items: ItemOffsets):
        self.click, self.buy, self.items = click, buy, items
        self.anchor: tuple[BayesLogit, BayesLogit] | None = None
        self.version = 0
        self._draws = 0

    @classmethod
    def new(cls, n_click: int, n_buy: int, prior_var: float = 4.0, sigma: float = 0.5) -> "Posterior":
        return cls(BayesLogit(n_click, prior_var), BayesLogit(n_buy, prior_var), ItemOffsets(sigma))

    def set_anchor(self):
        self.anchor = (self.click.copy(), self.buy.copy())

    def draw(self, rng) -> Draw:
        self._draws += 1
        return Draw(self.click.sample(rng), self.buy.sample(rng), self.items.sample_all(rng), self._draws)

    def mean_draw(self) -> Draw:
        return Draw(self.click.m.copy(), self.buy.m.copy(), dict(self.items.m), 0)

    def anchor_draw(self) -> Draw:
        c, b = self.anchor if self.anchor else (self.click, self.buy)
        return Draw(c.m.copy(), b.m.copy(), {}, -1)

    def copy(self) -> "Posterior":
        return copy.deepcopy(self)

    def save(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            pickle.dump(self, f)
        tmp.replace(path)

    @staticmethod
    def load(path: Path) -> "Posterior":
        with open(path, "rb") as f:
            return pickle.load(f)
