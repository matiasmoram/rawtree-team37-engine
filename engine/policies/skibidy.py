"""Standalone online learner, parallel to the LightGBM models (it does NOT use or wrap them).

Method: contextual Thompson sampling with a log-odds click model and a diagonal Laplace posterior.

    P(click of item i shown at slot k) = e_k * sigmoid(theta . z_i)        e_k = 0.27 + 0.73 / k (position examination)
    score_i = sigmoid(theta . z_i) * price_factor_i                          rank by expected purchase value
    theta ~ N(mu, diag(1/P)) drawn once per request (Thompson); mu, P learned online from our feedback

* z = standardised generic features (engine.features, without `slot`) + cart features + intercept. Parameters are
  shared across items (150-440 purchases cannot support per-item arms).
* Informative prior mean `PRIOR` (signs/sizes from the logged-carousel relation rates and the live checks:
  carted-not-bought items convert ~9x, bought items ~0) and prior sd 0.5, so it is sensible from request 1 and
  the data moves it where it disagrees.
* Update = diagonal online Newton (natural-gradient) step on the Bernoulli likelihood of each shown slot;
  purchases get extra weight (`buy_weight`) because they are what is scored. Forgetting `gamma` tracks drift.
* Bounded exploration: only `explore_frac` of requests (stable hash of request_id) use the sampled theta, and the
  first `greedy_slots` slots always use the posterior mean.
* Hard exclusions: every item the user already bought; out-of-stock items are removed by `fill`.
"""
from __future__ import annotations

import hashlib
import math
import threading
import time
from collections import OrderedDict

import numpy as np

from ..config import CACHE
from ..features import FEATURES, FIDX, build_context, featurize, generate_candidates
from ..learn.linucb import exposure_weight
from ..snapshot import Snapshot
from ..types import Request
from .base import K, fill
from .prepare import prepare_snapshot

USE = [f for f in FEATURES if f != "slot"]
USE_IDX = [FIDX[f] for f in USE]
NAMES = USE + ["in_cart", "cart_recency", "intercept"]
D = len(NAMES)

# Prior mean in standardised units (everything not listed starts at 0).
PRIOR = {
    "is_last_view": 0.6, "covis_vb": 0.3, "user_sub_share": 0.3, "q_organic": 0.3, "q_carousel": 0.2, "log_buy_7d": 0.2,
    "log_trend": 0.1, "user_bought_n": -0.8, "bought_in_event": -1.5, "in_cart": 0.9, "cart_recency": 0.2,
    "intercept": -6.0,
}


class _Std:
    """Running mean/std (Welford) of every candidate row served."""

    def __init__(self, d: int) -> None:
        self.n, self.mean, self.m2 = 0, np.zeros(d), np.zeros(d)

    def update(self, X: np.ndarray) -> None:
        for row in X:
            self.n += 1
            delta = row - self.mean
            self.mean += delta / self.n
            self.m2 += delta * (row - self.mean)

    def __call__(self, X: np.ndarray) -> np.ndarray:
        sd = np.sqrt(self.m2 / max(1, self.n - 1)) if self.n > 30 else np.ones_like(self.mean)
        return np.clip((X - self.mean) / np.maximum(sd, 1e-6), -4.0, 4.0)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


class SkibidyPolicy:
    def __init__(self, name: str = "skibidy-v1", explore_frac: float = 0.3, greedy_slots: int = 2,
                 prior_sd: float = 0.5, gamma: float = 0.9998, buy_weight: float = 3.0, money_alpha: float = 0.25,
                 temp: float = 1.0, pending_ttl: float = 900.0, seed: int | None = None) -> None:
        self.name = name
        self.explore_frac, self.greedy_slots = explore_frac, greedy_slots
        self.gamma, self.buy_weight, self.money_alpha, self.temp = gamma, buy_weight, money_alpha, temp
        self.pending_ttl = pending_ttl
        self.mu0 = np.array([PRIOR.get(n, 0.0) for n in NAMES])
        self.theta = self.mu0.copy()
        self.P0 = np.full(D, 1.0 / prior_sd ** 2)
        self.P0[NAMES.index("intercept")] = 1.0 / 4.0       # intercept: wide prior
        self.P = self.P0.copy()                              # posterior precision (diagonal)
        self.std = _Std(len(USE_IDX) + 2)
        self.rng = np.random.default_rng(seed)
        self._pending: "OrderedDict[str, tuple[float, list[tuple[int, str]], np.ndarray]]" = OrderedDict()
        self._lock = threading.Lock()
        self._ref_price: tuple[int, float] | None = None
        self.stats = {"served": 0, "explored": 0, "updates": 0, "clicks": 0, "buys": 0}
        self.state_path = CACHE / f"policy_state_{name}.npz"
        self._last_save = time.time()
        self.load_state()

    # ---- inputs (overridable in tests) --------------------------------------------------------------------
    def candidates_and_features(self, req: Request, snap: Snapshot) -> tuple[list[str], np.ndarray]:
        if getattr(snap, "sub_price", None) is None or not getattr(snap, "sub_quality", None):
            prepare_snapshot(snap)
        if not hasattr(snap, "recent_user_buys"):
            snap.recent_user_buys = {}
        ctx = build_context(req, snap)
        carts = getattr(snap, "user_cart", {}).get(req.user_id, {})
        cands = list(dict.fromkeys(generate_candidates(ctx, snap) + list(carts)[:20]))
        X = featurize(ctx, snap, cands)[:, USE_IDX].astype(np.float64)
        in_cart = np.zeros(len(cands))
        recency = np.zeros(len(cands))
        for i, pid in enumerate(cands):
            ts = carts.get(pid)
            if ts is not None:
                in_cart[i] = 1.0
                recency[i] = 1.0 / (1.0 + max(0.0, (req.ts - ts).total_seconds() / 86400.0))
        return cands, np.hstack([X, in_cart[:, None], recency[:, None]])

    def _excluded(self, req: Request, snap: Snapshot) -> set[str]:
        return set(snap.user_buy.get(req.user_id, {})) | set(getattr(snap, "recent_user_buys", {}).get(req.user_id, ()))

    def _price_factor(self, cands: list[str], snap: Snapshot) -> np.ndarray:
        if self.money_alpha <= 0:
            return np.ones(len(cands))
        if self._ref_price is None or self._ref_price[0] != id(snap):
            prices = sorted(p.price for p in snap.products.values() if p.active and p.price > 0)
            self._ref_price = (id(snap), prices[len(prices) // 2] if prices else 1.0)
        ref = self._ref_price[1]
        pr = np.array([snap.products[c].price if c in snap.products else ref for c in cands])
        return np.clip(pr / ref, 0.5, 2.5) ** self.money_alpha

    def is_explore(self, request_id: str) -> bool:
        return int(hashlib.md5(request_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < self.explore_frac

    # ---- serving -------------------------------------------------------------------------------------------
    def recommend(self, req: Request, snap: Snapshot) -> list[str]:
        cands, X = self.candidates_and_features(req, snap)
        if not cands:
            return fill([], snap)
        excluded = self._excluded(req, snap)
        keep = [i for i, c in enumerate(cands) if c not in excluded and snap.is_valid(c)]
        if not keep:
            return fill([], snap)
        cands, X = [cands[i] for i in keep], X[keep]
        with self._lock:
            self.std.update(X)
            theta, P = self.theta.copy(), self.P.copy()
        Z = np.hstack([self.std(X), np.ones((len(X), 1))])
        price = self._price_factor(cands, snap)
        mean_s = _sigmoid(Z @ theta) * price
        order = np.argsort(-mean_s, kind="stable")
        explore = self.is_explore(req.request_id)
        if explore:
            draw = theta + self.temp * self.rng.standard_normal(D) / np.sqrt(P)
            samp = _sigmoid(Z @ draw) * price
            head = [int(i) for i in order[: self.greedy_slots]]
            hs = set(head)
            order = np.array(head + [int(i) for i in np.argsort(-samp, kind="stable") if int(i) not in hs])
        top = [int(i) for i in order[:K]]
        with self._lock:
            self._pending[req.request_id] = (time.time(), [(k + 1, cands[i]) for k, i in enumerate(top)], Z[top].copy())
            cutoff = time.time() - self.pending_ttl
            while self._pending and next(iter(self._pending.values()))[0] < cutoff:
                self._pending.popitem(last=False)
            self.stats["served"] += 1
            self.stats["explored"] += int(explore)
        return fill([cands[i] for i in order[: 3 * K]], snap)

    # ---- learning ------------------------------------------------------------------------------------------
    def observe(self, feedback: list[dict]) -> int:
        """Learn from feedback rows (request_id, served_by, clicked, purchased). Returns impressions used."""
        n = 0
        for row in feedback:
            rid = str(row.get("request_id", ""))
            # Feedback may be matched to another arm when two policies emit the same slate.
            # Train only on unambiguous submissions attributed to this exact model.
            if str(row.get("model_version", "")) != f"t37-{self.name}":
                continue
            with self._lock:
                entry = self._pending.pop(rid, None)
            if entry is None or str(row.get("served_by", "team")) != "team":
                continue
            _, slots, Z = entry
            shown = [str(pid) for pid in (row.get("shown") or [])]
            expected = [pid for _, pid in slots]
            if len(shown) != K or shown != expected:
                # Ignore fallback arbitration and any slate repaired after ranking (e.g. stock changes).
                continue
            clicked, purchased = str(row.get("clicked") or ""), str(row.get("purchased") or "")
            if (clicked and clicked not in shown) or (purchased and purchased not in shown):
                continue
            e = np.array([exposure_weight(k) for k, _ in slots])
            y = np.array([1.0 if (clicked and pid == clicked) else 0.0 for _, pid in slots])
            w = np.where((y > 0) & (purchased == clicked) & bool(purchased), self.buy_weight, 1.0)
            with self._lock:
                eta = Z @ self.theta
                sg = _sigmoid(eta)
                p = np.clip(e * sg, 1e-6, 1 - 1e-6)
                dp = e * sg * (1 - sg)                       # dp/d eta
                g_eta = w * (y - p) * dp / (p * (1 - p))     # d logL / d eta
                fisher = w * dp * dp / (p * (1 - p))
                grad = Z.T @ g_eta
                self.P = self.gamma * self.P + (Z * Z).T @ fisher
                self.P = np.maximum(self.P, 0.25 * self.P0)  # forgetting never loosens below a quarter of the prior
                self.theta = self.theta + grad / self.P
                self.stats["updates"] += 1
                self.stats["clicks"] += int(y.sum())
                self.stats["buys"] += int(bool(purchased) and purchased == clicked and y.sum() > 0)
            n += len(slots)
        if time.time() - self._last_save > 60:
            self.save_state()
        return n

    def save_state(self) -> None:
        """Persist what was learned (atomic), so a restart does not go back to the prior."""
        with self._lock:
            tmp = self.state_path.with_suffix(".tmp.npz")
            np.savez(tmp, theta=self.theta, P=self.P, n=self.std.n, mean=self.std.mean, m2=self.std.m2,
                     updates=self.stats["updates"], saved_at=time.time())
            tmp.replace(self.state_path)
            self._last_save = time.time()

    def load_state(self, max_age_h: float = 24.0) -> bool:
        try:
            z = np.load(self.state_path)
            if time.time() - float(z["saved_at"]) > max_age_h * 3600 or z["theta"].shape != (D,):
                return False
            self.theta, self.P = z["theta"].copy(), z["P"].copy()
            self.std.n, self.std.mean, self.std.m2 = int(z["n"]), z["mean"].copy(), z["m2"].copy()
            self.stats["updates"] = int(z["updates"])
            return True
        except Exception:
            return False

    def weights(self) -> dict[str, float]:
        return dict(zip(NAMES, map(float, self.theta)))
