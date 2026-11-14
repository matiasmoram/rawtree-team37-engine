import time
import unittest

import numpy as np
import pandas as pd

from tests.thompson_fixtures import frames
from tests.test_thompson_features import row


def make(n_per_cat=10):
    from recsys.thompson.state import LiveState
    return LiveState.from_frames(*frames(n_per_cat))


def draw(**weights):
    from recsys.thompson import features as F
    from recsys.thompson.model import Draw
    wc = np.zeros(len(F.CLICK_FEATURES)); wc[0] = -4
    for k in range(10):
        wc[1 + k] = -0.3 * k          # position decay
    for n, v in weights.items():
        wc[F.CLICK_FEATURES.index(n)] = v
    wb = np.zeros(len(F.BUY_FEATURES)); wb[0] = -1
    return Draw(wc, wb, {}, 1)


class TestRanker(unittest.TestCase):
    def setUp(self):
        from recsys.thompson import ranker as R
        from recsys.thompson.features import Req
        self.R, self.Req = R, Req

    def req(self, st, views=(), **kw):
        return self.Req.from_row(row([(p, "2026-11-14 17:59:00") for p in views], **kw), st)

    def test_never_bought_or_oos(self):
        st = make()
        st.oos |= {st.pid2i["p_A1"], st.pid2i["p_A2"]}
        out = self.R.rank(st, self.req(st, ["p_A1", "p_A0", "p_A3"]), draw(earlier_viewed_top3=3))
        bad = {st.pid2i[p] for p in ("p_A0", "p_A1", "p_A2")}   # p_A0 bought by u1
        self.assertFalse(set(out) & bad)

    def test_ten_distinct(self):
        st = make()
        out = self.R.rank(st, self.req(st, ["p_B1"]), draw())
        self.assertEqual(len(out), 10)
        self.assertEqual(len(set(out)), 10)

    def test_fill_when_pool_small(self):
        st = make()  # 30 items
        st.oos |= set(range(18))
        out = self.R.rank(st, self.req(st, [], user="new", page="home", new_user=True), draw())
        self.assertEqual(len(set(out)), 10)
        self.assertFalse(set(out) & st.oos)

    def test_viewed_item_goes_top_when_weight_high(self):
        st = make()
        out = self.R.rank(st, self.req(st, ["p_C3", "p_B2"]), draw(earlier_viewed_top3=5))
        self.assertIn(st.pid2i["p_C3"], out[:2])

    def test_near_tie_prefers_pricier(self):
        st = make()
        # zero all item effects: every candidate ties exactly -> the most expensive must take slot 1
        out = self.R.rank(st, self.req(st, [], user="new", page="product"), draw())
        cands = [i for i in self.R.candidates(st, self.req(st, [], user="new", page="product"))
                 if i not in st.oos]
        price = st.items.price.to_numpy()
        self.assertEqual(price[out[0]], price[cands].max())

    def test_new_product_candidate(self):
        st = make()
        st.apply_updates(pd.DataFrame([dict(ts="2026-11-14 17:00:00", change="new_product", product_id="p_NEW",
                                            category="B", subcategory="B0", brand="z", price=20.0)]))
        c = self.R.candidates(st, self.req(st, ["p_B2"]))
        self.assertIn(st.pid2i["p_NEW"], set(c))

    def test_rank_fast(self):
        st = make(n_per_cat=120)
        req = self.req(st, ["p_A1", "p_B2", "p_C3"])
        self.assertGreaterEqual(len(self.R.candidates(st, req)), 150)
        d = draw()
        self.R.rank(st, req, d)
        t = time.perf_counter()
        for _ in range(10):
            self.R.rank(st, req, d)
        self.assertLess((time.perf_counter() - t) / 10, 0.05)


if __name__ == "__main__":
    unittest.main()
