from __future__ import annotations

import itertools
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from engine.experiments import health_snapshot, owns_request, promotion_gate, request_bucket, write_health
from engine.policies.explore import TailExplorePolicy, tail_probability
from engine.snapshot import Product, Snapshot
from engine.types import Request


NOW = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)


def fixture():
    products = {f"p{i}": Product(f"p{i}", "cat", "sub", "brand", 10.0, 10.0, "item", True)
                for i in range(30)}
    snap = Snapshot(NOW, products, {}, {}, {}, {}, {}, {}, {}, {}, {})
    snap.pop_global = list(products)
    snap.pop_by_sub = {"sub": list(products)}
    return snap


class Base:
    name = "fixed"

    def recommend(self, req, snap):
        return [f"p{i}" for i in range(10)]


class TestTailProbabilities(unittest.TestCase):
    def test_probability_mass_and_conditionals(self):
        pool = ["a", "b", "c", "d"]
        for epsilon in (0.0, 0.05, 0.2, 1.0):
            probs = {pair: tail_probability(["a", "b"], pool, epsilon, pair)
                     for pair in itertools.permutations(pool, 2)}
            self.assertAlmostEqual(sum(p[0] for p in probs.values()), 1.0)
            for a in pool:
                first = sum(p[0] for pair, p in probs.items() if pair[0] == a)
                expected = epsilon / len(pool) + (1.0 - epsilon) * (a == "a")
                self.assertAlmostEqual(first, expected)
                for pair, (joint, marginal, conditional) in probs.items():
                    if pair[0] == a:
                        self.assertAlmostEqual(joint, marginal * conditional)
                if first:
                    self.assertAlmostEqual(sum(p[2] for pair, p in probs.items() if pair[0] == a), 1.0)

    def test_duplicate_and_outside_pair_have_no_support(self):
        self.assertEqual(tail_probability(["a", "b"], ["a", "b"], .1, ["a", "a"])[0], 0)
        self.assertEqual(tail_probability(["a", "b"], ["a", "b"], .1, ["a", "x"])[0], 0)

    def test_reject_invalid_support(self):
        with self.assertRaises(ValueError):
            tail_probability(["a", "b"], ["a", "a"], .1, ["a", "b"])
        with self.assertRaises(ValueError):
            TailExplorePolicy(Base(), epsilon=0.5)


class TestTailPolicy(unittest.TestCase):
    def test_determinism_and_safe_tail(self):
        snap = fixture()
        snap.products["p14"].active = False
        snap.user_buy = {"u": {"p8": (1, NOW)}}
        snap.recent_user_buys = {"u": {"p9"}}
        policy = TailExplorePolicy(Base(), epsilon=.2, max_pool=12, seed="test")
        explored = 0
        for i in range(300):
            req = Request(str(i), NOW, "u", False, "home", "ios", "ES")
            items, metadata = policy.recommend_with_metadata(req, snap)
            self.assertEqual((items, metadata), policy.recommend_with_metadata(req, snap))
            self.assertEqual(items[:8], [f"p{j}" for j in range(8)])
            self.assertEqual(len(items), 10)
            self.assertEqual(len(set(items)), 10)
            self.assertFalse(set(items) & {"p8", "p9", "p14"})
            self.assertTrue(all(snap.is_valid(p) for p in items))
            self.assertLessEqual(metadata["pool_size"], 12)
            self.assertAlmostEqual(metadata["slate_propensity"],
                                   metadata["slot9_propensity"] * metadata["slot10_conditional_propensity"])
            explored += metadata["explored"]
        self.assertGreater(explored, 20)
        self.assertLess(explored, 100)

    def test_zero_epsilon_preserves_valid_clean_base(self):
        snap = fixture()
        req = Request("r", NOW, "u", False, "home", "ios", "ES")
        items, meta = TailExplorePolicy(Base(), epsilon=0, seed="test").recommend_with_metadata(req, snap)
        self.assertEqual(items, Base().recommend(req, snap))
        self.assertEqual(meta["slate_propensity"], 1)

    def test_too_few_clean_items_disables_exploration(self):
        snap = fixture()
        snap.user_buy = {"u": {p: (1, NOW) for p in snap.products}}
        req = Request("r", NOW, "u", False, "home", "ios", "ES")
        items, meta = TailExplorePolicy(Base(), seed="test").recommend_with_metadata(req, snap)
        self.assertEqual(items, Base().recommend(req, snap))
        self.assertFalse(meta["exploration_enabled"])
        self.assertEqual(meta["reason"], "fewer_than_ten_nonbought_candidates")


class TestOwnership(unittest.TestCase):
    def test_complete_disjoint_partition(self):
        for n in (1, 2, 3, 7, 100):
            for rid in map(str, range(100)):
                owners = [j for j in range(n) if owns_request(rid, j, n)]
                self.assertEqual(owners, [request_bucket(rid, n)])

    def test_default_owns_all(self):
        self.assertTrue(owns_request("r"))

    def test_reject_invalid_shards(self):
        for index, count in ((0, 0), (-1, 2), (2, 2), (0, 1.5), (True, 2)):
            with self.assertRaises(ValueError):
                owns_request("r", index, count)

    def test_health_atomic_document_is_explicitly_not_lease(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "health.json"
            payload = health_snapshot({"pushed": 5}, now=123.0, shard_index=1, shard_count=2)
            write_health(path, payload)
            self.assertEqual(json.loads(path.read_text()), payload)
            self.assertFalse(payload["distributed_lease"])
            write_health(path, {**payload, "updated_at": 124.0})
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)


class TestPromotionGate(unittest.TestCase):
    def valid(self):
        return dict(candidate_requests=1000, control_requests=1000,
                    metric="simulator_expected_conversion", preregistered=True,
                    window_complete=True, same_window=True, randomization_verified=True,
                    ci_method="fixed_horizon_user_clustered", looks=1,
                    difference_lower_bound=.01, multi_model_requests=0,
                    invalid_answers=0, on_time_share=1., p95_ms=1400.)

    def test_valid_fixed_horizon_evidence_allows_review_not_automatic_promotion(self):
        gate = promotion_gate(self.valid())
        self.assertTrue(gate["allow_promotion_review"])
        self.assertFalse(gate["automatic_promotion"])

    def test_competing_emitters_block(self):
        gate = promotion_gate({**self.valid(), "multi_model_requests": 1})
        self.assertFalse(gate["allow_promotion_review"])
        self.assertIn("competing_emitters_or_missing_audit", gate["reasons"])

    def test_repeated_looks_and_offline_metric_block(self):
        self.assertFalse(promotion_gate({**self.valid(), "looks": 2})["allow_promotion_review"])
        self.assertFalse(promotion_gate({**self.valid(), "metric": "offline_model_value"})["allow_promotion_review"])

    def test_missing_support_invalid_latency_and_nan_block(self):
        for key, value in (("candidate_requests", 20), ("invalid_answers", 1), ("p95_ms", 3001),
                           ("difference_lower_bound", float("nan")), ("on_time_share", .95)):
            self.assertFalse(promotion_gate({**self.valid(), key: value})["allow_promotion_review"], key)
        self.assertFalse(promotion_gate({})["allow_promotion_review"])

    def test_booleans_cannot_impersonate_numeric_evidence(self):
        for key in ("candidate_requests", "difference_lower_bound", "multi_model_requests",
                    "invalid_answers", "on_time_share", "p95_ms", "looks"):
            for value in (True, False):
                self.assertFalse(promotion_gate({**self.valid(), key: value})["allow_promotion_review"], key)


if __name__ == "__main__":
    unittest.main()
