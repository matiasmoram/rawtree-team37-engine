import unittest

import numpy as np
import pandas as pd

from tests.thompson_fixtures import state


def row(views, ts="2026-11-14 18:00:00", user="u1", page="product", new_user=False):
    return dict(request_id="r1", ts=ts, user_id=user, is_new_user=new_user,
                context={"page": page, "device": "web", "region": "x"},
                recent_views=[{"product_id": p, "ts": t} for p, t in views])


class TestFeatures(unittest.TestCase):
    def setUp(self):
        from recsys.thompson import features as F
        self.F, self.st = F, state()

    def test_shapes_and_names(self):
        F, st = self.F, self.st
        req = F.Req.from_row(row([("p_A1", "2026-11-14 17:59:00")]), st)
        items = np.array([0, 1, 2, 3])
        Xc = F.click_matrix(st, req, items, np.array([1, 2, 3, 4]))
        Xb = F.buy_matrix(st, req, items)
        self.assertEqual(Xc.shape, (4, len(F.CLICK_FEATURES)))
        self.assertEqual(Xb.shape, (4, len(F.BUY_FEATURES)))
        self.assertEqual(F.CLICK_FEATURES[0], "bias")
        self.assertEqual(F.CLICK_FEATURES[1:11], [f"slot_{k}" for k in range(1, 11)])
        self.assertTrue(np.isfinite(Xc).all() and np.isfinite(Xb).all())

    def test_last_viewed_flags(self):
        F, st = self.F, self.st
        req = F.Req.from_row(row([("p_A1", "2026-11-14 17:58:00"), ("p_A2", "2026-11-14 17:59:00")]), st)
        c = {n: k for k, n in enumerate(F.CLICK_FEATURES)}
        a1, a2 = st.pid2i["p_A1"], st.pid2i["p_A2"]
        X = F.click_matrix(st, req, np.array([a2, a1, a2, a1]), np.array([1, 2, 5, 6]))
        self.assertEqual(X[0, c["last_viewed"]], 1); self.assertEqual(X[0, c["earlier_viewed"]], 0)
        self.assertEqual(X[0, c["last_viewed_top3"]], 1)
        self.assertEqual(X[1, c["earlier_viewed"]], 1); self.assertEqual(X[1, c["earlier_viewed_top3"]], 1)
        self.assertEqual(X[2, c["last_viewed_top3"]], 0)  # slot 5
        self.assertEqual(X[3, c["earlier_viewed_top3"]], 0)
        self.assertEqual(X[0, c["slot_1"]], 1); self.assertEqual(X[2, c["slot_5"]], 1)

    def test_future_views_dropped(self):
        F, st = self.F, self.st
        req = F.Req.from_row(row([("p_A1", "2026-11-14 17:59:00"), ("p_B1", "2026-11-14 18:00:01")]), st)
        self.assertEqual(req.views, [st.pid2i["p_A1"]])

    def test_no_views_price_ratio_zero(self):
        F, st = self.F, self.st
        req = F.Req.from_row(row([], page="home"), st)
        c = {n: k for k, n in enumerate(F.CLICK_FEATURES)}
        X = F.click_matrix(st, req, np.array([0, 5]), np.array([1, 2]))
        self.assertTrue((X[:, c["log_price_ratio"]] == 0).all())
        self.assertTrue((X[:, c["nviews_0"]] == 1).all())
        self.assertTrue((X[:, c["page_home"]] == 1).all())

    def test_unknown_view_ignored(self):
        F, st = self.F, self.st
        req = F.Req.from_row(row([("p_UNKNOWN", "2026-11-14 17:59:00")]), st)
        self.assertEqual(req.views, [])

    def test_cold_flag(self):
        F, st = self.F, self.st
        self.assertTrue(F.Req.from_row(row([], new_user=True), st).cold)
        st.apply_updates(pd.DataFrame([dict(ts="2026-11-14 17:00:00", change="new_product", product_id="p_N",
                                            category="A", subcategory="A0", brand="b", price=9.0)]))
        self.assertTrue(F.Req.from_row(row([("p_N", "2026-11-14 17:59:00")]), st).cold)
        self.assertFalse(F.Req.from_row(row([("p_A1", "2026-11-14 17:59:00")]), st).cold)

    def test_history_and_bought_sub(self):
        F, st = self.F, self.st
        c = {n: k for k, n in enumerate(F.CLICK_FEATURES)}
        req = F.Req.from_row(row([]), st)
        a3 = st.pid2i["p_A2"]  # subcategory A0, same as bought p_A0
        X = F.click_matrix(st, req, np.array([a3]), np.array([1]))
        self.assertEqual(X[0, c["bought_same_sub"]], 1)
        self.assertAlmostEqual(X[0, c["hist_cat_share"]], 23 / 28, places=5)


if __name__ == "__main__":
    unittest.main()
