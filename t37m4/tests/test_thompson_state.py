import unittest

import numpy as np
import pandas as pd

from tests.thompson_fixtures import state


class TestLiveState(unittest.TestCase):
    def test_new_product_delta_is_indexed(self):
        st = state()
        n = st.apply_updates(pd.DataFrame([dict(ts="2026-11-14 18:00:00", change="new_product", product_id="p_NEW",
                                                category="B", subcategory="B0", brand="y", price=12.0)]))
        self.assertEqual(n, 1)
        self.assertIn("p_NEW", st.pid2i)
        i = st.pid2i["p_NEW"]
        self.assertTrue(bool(st.items.new[i]))
        self.assertIn(i, st.cat_best[int(st.items.cat[i])])
        self.assertIn(i, st.sub_best[int(st.items["sub"][i])])

    def test_live_purchase_bans_item(self):
        st = state()
        st.apply_purchases(pd.DataFrame([dict(user_id="u2", product_id="p_B3", ts="2026-11-14 18:00:00")]))
        i = st.pid2i["p_B3"]
        self.assertIn(i, st.bought["u2"])
        self.assertIn(int(st.items["sub"][i]), st.bought_sub["u2"])
        self.assertIn(st.pid2i["p_A0"], st.bought["u1"])  # history purchase

    def test_bought_before_uses_purchase_time(self):
        st = state()
        st.apply_purchases(pd.DataFrame([dict(user_id="u1", product_id="p_B3", ts="2026-11-14 18:00:05")]))
        before = st.bought_before("u1", "2026-11-14 18:00:00")
        self.assertIn(st.pid2i["p_A0"], before)
        self.assertNotIn(st.pid2i["p_B3"], before)
        self.assertIn(st.pid2i["p_B3"], st.bought_before("u1", "2026-11-14 18:00:06"))

    def test_stock_toggle(self):
        st = state()
        i = st.pid2i["p_C1"]
        st.apply_updates(pd.DataFrame([dict(ts="2026-11-14 18:00:00", change="out_of_stock", product_id="p_C1")]))
        self.assertIn(i, st.oos)
        st.apply_updates(pd.DataFrame([dict(ts="2026-11-14 18:01:00", change="back_in_stock", product_id="p_C1")]))
        self.assertNotIn(i, st.oos)

    def test_price_change(self):
        st = state()
        st.apply_updates(pd.DataFrame([dict(ts="2026-11-14 18:00:00", change="price_change", product_id="p_C1",
                                            price=99.0)]))
        self.assertEqual(st.items.price[st.pid2i["p_C1"]], 99.0)

    def test_ucat_shares_sum_to_one(self):
        st = state()
        s = st.ucat["u1"]
        self.assertAlmostEqual(float(s.sum()), 1.0, places=6)
        # A: 10 + 3 + 10 = 23, B: 5 -> A share 23/28
        self.assertAlmostEqual(float(s[st.cats.index("A")]), 23 / 28, places=6)

    def test_cat_best_sorted_by_popularity(self):
        st = state()
        lst = st.cat_best[st.cats.index("A")]
        lp = st.items.logp.to_numpy()[lst]
        self.assertTrue(np.all(np.diff(lp) <= 1e-12))

    def test_coview_index(self):
        st = state()
        self.assertEqual(st.cov[st.pid2i["p_A0"]][0], st.pid2i["p_B1"])


class TestPurchaseRefresh(unittest.TestCase):
    def test_purchase_query_overlaps_and_polls_fast(self):
        import inspect
        from recsys.thompson import state as S
        w = S.purchases_where("2026-11-14 18:00:30.123000")
        self.assertIn("2026-11-14 17:59:30", w)          # re-reads a 60 s overlap
        self.assertLessEqual(inspect.signature(S.LiveState.refresh_loop).parameters["buys_every"].default, 3)


if __name__ == "__main__":
    unittest.main()
