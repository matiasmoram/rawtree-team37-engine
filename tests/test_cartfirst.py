"""Offline tests with a synthetic snapshot (no RawTree access). Run: python -m unittest discover -s tests -v"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

import numpy as np

os.environ.setdefault("TEAM_ID", "team_test")          # config.py needs these at import; dummy values, never used
os.environ.setdefault("RAWTREE_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.learn.linucb import RidgeBandit, exposure_weight
from engine.policies.cartfirst import CartFirstPolicy
from engine.snapshot import Product, Snapshot
from engine.types import Request

NOW = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)
STAT = dict(view_all=200.0, buy_all=8.0, buy_7d=1.0, buy_1d=0.1, view_7d=40.0, view_3h=2.0)


def make_snapshot(n: int = 120) -> Snapshot:
    products, stats = {}, {}
    for i in range(n):
        pid = f"p{i}"
        sub = f"s{i % 6}"
        products[pid] = Product(pid, f"c{i % 2}", sub, "b", 10.0 + i, 10.0 + i, "d", True)
        stats[pid] = dict(STAT, buy_7d=1.0 + (n - i) / n)  # p0 is the most popular
    snap = Snapshot(NOW, products, stats, {}, {}, {}, {}, {}, {}, {}, {})
    from engine.snapshot import _rank_lists
    _rank_lists(snap)
    return snap


def req(user="u1", views=(), new=False) -> Request:
    return Request("r1", NOW, user, new, "product", "ios", "eu",
                   [(p, NOW - timedelta(minutes=i + 1)) for i, p in enumerate(views)])


class CartFirstTests(unittest.TestCase):
    def setUp(self):
        self.snap = make_snapshot()
        self.pol = CartFirstPolicy()

    def check_valid(self, out):
        self.assertEqual(len(out), 10)
        self.assertEqual(len(set(out)), 10)
        self.assertTrue(all(self.snap.is_valid(p) for p in out))

    def test_cold_user_gets_valid_list(self):
        self.check_valid(self.pol.recommend(req("nobody", new=True), self.snap))

    def test_bought_never_shown_even_if_carted_viewed_or_popular(self):
        s = self.snap
        s.user_buy["u1"] = {"p0": (1, NOW), "p5": (1, NOW), "p7": (2, NOW)}
        s.user_cart = {"u1": {"p5": NOW, "p9": NOW}}
        s.recent_user_buys = {"u1": {"p11"}}
        out = self.pol.recommend(req("u1", views=["p7", "p11", "p3"]), s)
        self.check_valid(out)
        for banned in ("p0", "p5", "p7", "p11"):
            self.assertNotIn(banned, out)
        self.assertIn("p9", out)

    def test_cart_cap_and_cart_first(self):
        s = self.snap
        s.user_cart = {"u1": {f"p{i}": NOW - timedelta(days=i) for i in range(50, 60)}}
        out = self.pol.recommend(req("u1"), s)
        self.check_valid(out)
        carts = [p for p in out if p in s.user_cart["u1"]]
        self.assertEqual(len(carts), self.pol.cart_cap)
        self.assertEqual(set(out[: self.pol.cart_cap]), set(carts))

    def test_recent_views_are_surfaced(self):
        out = self.pol.recommend(req("u1", views=["p80", "p81"]), self.snap)
        self.check_valid(out)
        self.assertIn("p80", out)
        self.assertIn("p81", out)

    def test_out_of_stock_removed(self):
        s = self.snap
        s.user_cart = {"u1": {"p50": NOW}}
        s.products["p50"].active = False
        self.assertNotIn("p50", self.pol.recommend(req("u1"), s))

    def test_all_popular_bought_still_valid(self):
        s = self.snap
        s.user_buy["u1"] = {p: (1, NOW) for p in s.pop_global[:60]}
        out = self.pol.recommend(req("u1"), s)
        self.check_valid(out)
        self.assertFalse(set(out) & set(s.user_buy["u1"]))


class BanditTests(unittest.TestCase):
    def test_recovers_linear_signal_and_uncertainty_shrinks(self):
        rng = np.random.default_rng(0)
        true = np.array([1.0, -0.5, 0.0, 2.0])
        b = RidgeBandit(4, lam=1.0, gamma=1.0, seed=1)
        x0 = np.ones(4)
        u0 = float(b.uncertainty(x0)[0])
        for _ in range(3000):
            x = rng.normal(size=4)
            b.update(x, float(x @ true + rng.normal(scale=0.1)))
        self.assertTrue(np.allclose(b.theta, true, atol=0.05))
        self.assertLess(float(b.uncertainty(x0)[0]), 0.1 * u0)

    def test_batch_equals_online_without_forgetting(self):
        rng = np.random.default_rng(2)
        X = rng.normal(size=(400, 3))
        r = X @ np.array([0.5, 1.0, -1.0]) + rng.normal(scale=0.05, size=400)
        a = RidgeBandit(3, gamma=1.0, refresh_every=50)
        for x, y in zip(X, r):
            a.update(x, y)
        c = RidgeBandit(3, gamma=1.0)
        c.fit_batch(X, r)
        self.assertTrue(np.allclose(a.theta, c.theta, atol=1e-6))

    def test_thompson_explores_more_when_uncertain(self):
        b = RidgeBandit(2, seed=3)
        draws = [float(b.thompson(np.ones((1, 2)))[0]) for _ in range(200)]
        trained = RidgeBandit(2, seed=3)
        trained.fit_batch(np.random.default_rng(4).normal(size=(500, 2)), np.zeros(500))
        draws2 = [float(trained.thompson(np.ones((1, 2)))[0]) for _ in range(200)]
        self.assertGreater(np.std(draws), 3 * np.std(draws2))

    def test_exposure_weight_curve(self):
        self.assertAlmostEqual(exposure_weight(1), 1.0)
        self.assertAlmostEqual(exposure_weight(1) / exposure_weight(10), 2.9, delta=0.1)


if __name__ == "__main__":
    unittest.main()
