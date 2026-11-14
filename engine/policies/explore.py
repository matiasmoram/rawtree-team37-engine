"""Bounded randomized exploration of the last two slots, with auditable probabilities.

The analytical probabilities are conditional on the logged candidate pool, clean
base slate and owning arm. They are not probabilities for arbitrary catalog lists.
No HTTP, filesystem reads or posterior fitting occur in recommend().
"""
from __future__ import annotations

import hashlib
import random
import secrets
from collections.abc import Sequence

from ..features import build_context, generate_candidates
from .base import K


def tail_probability(base_tail: Sequence[str], pool: Sequence[str], epsilon: float,
                     pair: Sequence[str]) -> tuple[float, float, float]:
    """Return P(a,b), P(a), P(b|a) for the deterministic/uniform-tail mixture."""
    if not 0.0 <= epsilon <= 1.0:
        raise ValueError("epsilon must be in [0, 1]")
    if len(pool) < 2 or len(set(pool)) != len(pool):
        raise ValueError("pool must contain at least two distinct items")
    if len(base_tail) != 2 or base_tail[0] == base_tail[1] or not set(base_tail) <= set(pool):
        raise ValueError("base tail must be a distinct ordered pair in the pool")
    if len(pair) != 2 or pair[0] == pair[1] or not set(pair) <= set(pool):
        return 0.0, 0.0, 0.0
    m = len(pool)
    joint = epsilon / (m * (m - 1)) + (1.0 - epsilon) * (tuple(pair) == tuple(base_tail))
    first = epsilon / m + (1.0 - epsilon) * (pair[0] == base_tail[0])
    return float(joint), float(first), float(joint / first) if first else 0.0


class TailExplorePolicy:
    """Keep eight clean base items; explore an ordered tail pair on epsilon of requests.

    A process-random salt makes assignments independent of the recommender inputs;
    hashing that salt with request_id gives repeatable retries within the deployment.
    Pass an explicit seed in experiments/tests to reproduce the entire deployment.
    The salt identifier (not the salt) is logged with the selection probabilities.
    """

    def __init__(self, base, epsilon: float = 0.05, max_pool: int = 40,
                 name: str | None = None, seed: str | None = None):
        if not 0.0 <= epsilon <= 0.2:
            raise ValueError("serving exploration epsilon must be in [0, 0.2]")
        if max_pool < 2:
            raise ValueError("max_pool must be at least 2")
        self.base = base
        self.epsilon = float(epsilon)
        self.max_pool = int(max_pool)
        self.name = name or f"{base.name}-tail"
        self._seed = seed if seed is not None else secrets.token_hex(16)
        self.seed_id = hashlib.sha256(self._seed.encode()).hexdigest()[:16]

    def recommend_with_metadata(self, req, snap) -> tuple[list[str], dict]:
        original = list(self.base.recommend(req, snap))
        bought = set(snap.user_buy.get(req.user_id, {})) | set(
            getattr(snap, "recent_user_buys", {}).get(req.user_id, set()))
        candidates = generate_candidates(build_context(req, snap), snap)
        eligible = list(dict.fromkeys(p for p in original + candidates + list(snap.pop_global)
                                      if snap.is_valid(p) and p not in bought))
        if len(eligible) < K:
            # Preserve the base policy's safe fill when the clean catalog is too small.
            # This is deterministic and is explicitly outside the exploration support.
            return original, {"exploration_enabled": False, "explored": False,
                              "reason": "fewer_than_ten_nonbought_candidates",
                              "slate_propensity": 1.0, "seed_id": self.seed_id,
                              "propensity_scope": "conditional_on_owning_arm"}
        base = eligible[:K]
        prefix, base_tail = base[:8], base[8:10]
        pool = list(dict.fromkeys(base_tail + [p for p in eligible if p not in prefix]))[:self.max_pool]
        digest = hashlib.sha256((self._seed + ":" + req.request_id).encode()).digest()
        rng = random.Random(int.from_bytes(digest, "big"))
        explored = rng.random() < self.epsilon
        tail = rng.sample(pool, 2) if explored else base_tail
        joint, first, conditional = tail_probability(base_tail, pool, self.epsilon, tail)
        items = prefix + tail
        return items, {
            "exploration_enabled": True, "explored": explored,
            "epsilon": self.epsilon, "seed_id": self.seed_id,
            "base_slate": base, "base_tail": base_tail, "pool": pool,
            "pool_size": len(pool), "selected_tail": tail,
            "slate_propensity": joint, "joint_tail_propensity": joint,
            "slot9_propensity": first, "slot10_conditional_propensity": conditional,
            "propensity_scope": "conditional_on_pool_clean_base_and_owning_arm",
            "randomization": "deployment_random_salt_and_request_id_sha256",
            "items": items,
        }

    def recommend(self, req, snap) -> list[str]:
        return self.recommend_with_metadata(req, snap)[0]
