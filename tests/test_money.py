"""Offline tests for MoneyPolicy. Run: python -m unittest discover -s tests -v"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_cartfirst import NOW, make_snapshot, req  # noqa: E402
from engine.policies.money import MoneyPolicy  # noqa: E402


class MoneyTests(unittest.TestCase):
    def test_valid_and_excludes_bought(self):
        s = make_snapshot()
        s.user_buy["u1"] = {"p0": (1, NOW), "p1": (1, NOW)}
        out = MoneyPolicy().recommend(req("u1", views=["p3"]), s)
        self.assertEqual(len(set(out)), 10)
        self.assertTrue(all(s.is_valid(p) for p in out))
        self.assertFalse({"p0", "p1"} & set(out))

    def test_price_lifts_expensive_items(self):
        s = make_snapshot()
        lo = MoneyPolicy(alpha=0.0).recommend(req("u9", new=True), s)
        hi = MoneyPolicy(alpha=1.0).recommend(req("u9", new=True), s)
        avg = lambda l: sum(s.products[p].price for p in l) / len(l)
        self.assertGreaterEqual(avg(hi), avg(lo))


if __name__ == "__main__":
    unittest.main()
