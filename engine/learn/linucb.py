"""M3 core - ridge contextual bandit with forgetting (LinUCB / LinTS), shared parameters across items.

    Q(s, a) = phi(s, a)^T theta        theta fitted by exponentially weighted ridge regression
    UCB:  Q + c * sqrt(phi^T C^-1 phi)             Thompson: draw theta ~ N(theta_hat, sigma^2 C^-1)

Course notes (Ch.2): shared theta because per-item learning is impossible with ~150-440 purchases in a
2 h final; forgetting `gamma` < 1 handles drift; exploration is a parameter (c / sigma), set to 0 for greedy.
The update is a Sherman-Morrison recursion on C^-1 with a periodic exact refresh, because the slides note
Sherman-Morrison can lose positive-definiteness.

Rewards here should be per-impression purchase indicators weighted by 1 / slot_weight (see `exposure`),
otherwise items often shown in slot 1 look better than they are.
"""
from __future__ import annotations

import threading

import numpy as np


class RidgeBandit:
    def __init__(self, dim: int, lam: float = 1.0, gamma: float = 0.9999, sigma: float = 1.0, refresh_every: int = 500,
                 seed: int | None = None) -> None:
        self.d = dim
        self.lam = lam
        self.gamma = gamma
        self.sigma = sigma
        self.refresh_every = refresh_every
        self.A = lam * np.eye(dim)          # lam*I + sum gamma^k x x^T
        self.b = np.zeros(dim)
        self.Ainv = np.eye(dim) / lam
        self.theta = np.zeros(dim)
        self.n = 0
        self.rng = np.random.default_rng(seed)
        self._lock = threading.Lock()

    # ---- learning ----
    def update(self, x: np.ndarray, reward: float, weight: float = 1.0) -> None:
        x = np.asarray(x, dtype=float)
        with self._lock:
            g = self.gamma
            self.A = g * self.A + weight * np.outer(x, x) + (1 - g) * self.lam * np.eye(self.d)  # keep the prior alive
            self.b = g * self.b + weight * reward * x
            self.n += 1
            if self.n % self.refresh_every == 0:
                self.Ainv = np.linalg.inv(self.A)
            else:  # rank-one update; ignores the small (1-g)*lam*I term, corrected by the periodic exact inverse
                Ainv = self.Ainv / g
                Ax = Ainv @ x
                self.Ainv = Ainv - weight * np.outer(Ax, Ax) / (1.0 + weight * float(x @ Ax))
            self.theta = self.Ainv @ self.b

    def fit_batch(self, X: np.ndarray, r: np.ndarray, w: np.ndarray | None = None) -> None:
        """Exact weighted ridge on a batch (offline warm start from logged feedback)."""
        w = np.ones(len(r)) if w is None else np.asarray(w, dtype=float)
        with self._lock:
            self.A = self.lam * np.eye(self.d) + (X * w[:, None]).T @ X
            self.b = X.T @ (w * r)
            self.Ainv = np.linalg.inv(self.A)
            self.theta = self.Ainv @ self.b
            self.n += len(r)

    # ---- scoring ----
    def mean(self, X: np.ndarray) -> np.ndarray:
        return np.atleast_2d(X) @ self.theta

    def uncertainty(self, X: np.ndarray) -> np.ndarray:
        X = np.atleast_2d(X)
        return np.sqrt(np.maximum(0.0, np.einsum("ij,jk,ik->i", X, self.Ainv, X)))

    def ucb(self, X: np.ndarray, c: float = 1.0) -> np.ndarray:
        return self.mean(X) + c * self.uncertainty(X)

    def thompson(self, X: np.ndarray) -> np.ndarray:
        """One posterior draw of theta shared by all candidates of a request (coherent exploration)."""
        cov = (self.sigma ** 2) * self.Ainv
        cov = (cov + cov.T) / 2.0
        draw = self.rng.multivariate_normal(self.theta, cov, method="cholesky" if self._pd(cov) else "svd")
        return np.atleast_2d(X) @ draw

    @staticmethod
    def _pd(m: np.ndarray) -> bool:
        try:
            np.linalg.cholesky(m)
            return True
        except np.linalg.LinAlgError:
            return False


def exposure_weight(slot: int) -> float:
    """Relative examination of slot k (1-based): 0.27 + 0.73 / k (fits the clean history curve; re-check live)."""
    return 0.27 + 0.73 / max(1, slot)
