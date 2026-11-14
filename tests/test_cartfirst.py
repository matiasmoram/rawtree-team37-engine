import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("TEAM_ID", "team_test")
os.environ.setdefault("RAWTREE_API_KEY", "test-key")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.policies.cartfirst import CartFirstPolicy
from engine.content import ContentIndex
from engine.policies.registry import get_policy
from engine.snapshot import Product, Snapshot, _rank_lists
from engine.types import Request


NOW = datetime(2026, 11, 14, 15, tzinfo=timezone.utc)


def make_snapshot(n=120):
    products, stats = {}, {}
    for i in range(n):
        pid = f"p{i}"
        products[pid] = Product(pid, f"c{i % 2}", f"s{i % 6}", "brand", 10 + i, 10 + i, "", True)
        stats[pid] = dict(view_all=200., buy_all=8., buy_7d=1. + (n-i)/n,
                          buy_1d=.1, view_7d=40., view_3h=2.)
    snap = Snapshot(NOW, products, stats, {}, {}, {}, {}, {}, {}, {}, {})
    _rank_lists(snap)
    return snap


def request(user="u1", views=(), new=False):
    return Request("r1", NOW, user, new, "product", "ios", "eu",
                   [(p, NOW - timedelta(minutes=i + 1)) for i, p in enumerate(views)])


class CartFirstTests(unittest.TestCase):
    def setUp(self):
        self.snap = make_snapshot()
        self.policy = CartFirstPolicy()

    def assert_valid(self, items):
        self.assertEqual(len(items), 10)
        self.assertEqual(len(set(items)), 10)
        self.assertTrue(all(self.snap.is_valid(p) for p in items))

    def test_cart_candidates_lead_and_cap(self):
        self.snap.user_cart = {"u1": {f"p{i}": NOW - timedelta(days=i) for i in range(50, 60)}}
        items = self.policy.recommend(request(), self.snap)
        self.assert_valid(items)
        carts = set(self.snap.user_cart["u1"])
        self.assertEqual(len(set(items[:6]) & carts), 6)

    def test_bought_and_inactive_products_never_show(self):
        self.snap.user_cart = {"u1": {"p50": NOW, "p51": NOW}}
        self.snap.user_buy = {"u1": {"p50": (1, NOW), "p1": (1, NOW)}}
        self.snap.recent_user_buys = {"u1": {"p2"}}
        self.snap.products["p51"].active = False
        items = self.policy.recommend(request(views=("p1", "p2", "p3")), self.snap)
        self.assert_valid(items)
        self.assertFalse({"p1", "p2", "p50", "p51"} & set(items))

    def test_new_user_falls_back_to_valid_popular_items(self):
        self.assert_valid(self.policy.recommend(request("new", new=True), self.snap))

    def test_session_views_are_candidate_sources(self):
        items = self.policy.recommend(request(views=("p80", "p81")), self.snap)
        self.assert_valid(items)
        self.assertTrue({"p80", "p81"} & set(items))

    def test_new_product_uses_content_neighbour(self):
        source, neighbour = "p110", "p40"
        self.snap.products[source].is_new = True
        self.snap.products[source].added_ts = NOW - timedelta(minutes=5)
        self.policy.content_index = ContentIndex(forward={source: ((neighbour, .98),)}, reverse={})
        items = self.policy.recommend(request(views=(source,)), self.snap)
        self.assert_valid(items)
        self.assertIn(neighbour, items)

    def test_rotation_puts_earlier_view_first(self):
        policy = get_policy("cf-rot")
        captured = {}
        policy.inner.recommend = lambda req, snap: captured.setdefault("views", req.viewed) or []
        policy.recommend(request(views=("p80", "p81")), self.snap)
        self.assertEqual(captured["views"][:2], ["p81", "p80"])


if __name__ == "__main__":
    unittest.main()
