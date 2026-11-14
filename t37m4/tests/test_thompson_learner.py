import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from tests.thompson_fixtures import state


def fb_row(rid, shown, clicked="", purchased="", user="u1", ts="2026-11-14 18:00:00", views=(), served_by="team"):
    return dict(request_id=rid, ts=ts, user_id=user, is_new_user=False,
                context={"page": "product"}, recent_views=[{"product_id": p, "ts": "2026-11-14 17:59:00"} for p in views],
                shown=None if shown is None else list(shown), clicked=clicked, purchased=purchased, served_by=served_by)


def shown10(c="B"):
    return [f"p_{c}{k}" for k in range(10)]


class TestLearner(unittest.TestCase):
    def setUp(self):
        from recsys.thompson import learner as L
        self.L = L

    def test_rows_to_training_slots_and_ban(self):
        st = state()
        # u1 bought p_A0 in history (before the request) -> dropped; p_A1 bought *in this row* -> kept
        st.apply_purchases(pd.DataFrame([dict(user_id="u1", product_id="p_A1", ts="2026-11-14 18:00:05")]))
        rows = pd.DataFrame([fb_row("r1", shown10("A"), clicked="p_A1", purchased="p_A1")])
        tr = self.L.rows_to_training(st, rows)
        self.assertEqual(len(tr.yc), 9)                                  # p_A0 dropped
        self.assertNotIn(st.pid2i["p_A0"], set(tr.items))
        k = list(tr.items).index(st.pid2i["p_A1"])
        self.assertEqual(tr.yc[k], 1)
        from recsys.thompson.features import CLICK_FEATURES
        self.assertEqual(tr.Xc[k, CLICK_FEATURES.index("slot_2")], 1)   # p_A1 was shown in slot 2
        self.assertEqual(list(tr.yb), [1.0])                             # buy model: clicked rows only

    def test_bad_rows_skipped(self):
        st = state()
        rows = pd.DataFrame([fb_row("r1", ["p_UNKNOWN"] + shown10()[1:]),
                             fb_row("r2", []),
                             fb_row("r3", None),
                             fb_row("r4", shown10("C"), clicked="p_C3")])
        tr = self.L.rows_to_training(st, rows)
        self.assertEqual(len(tr.yc), 9 + 10)
        self.assertTrue(np.isfinite(tr.Xc).all())

    def test_fallback_flag(self):
        st = state()
        from recsys.thompson.features import CLICK_FEATURES
        tr = self.L.rows_to_training(st, pd.DataFrame([fb_row("r1", shown10(), served_by="fallback")]))
        self.assertTrue((tr.Xc[:, CLICK_FEATURES.index("served_by_fallback")] == 1).all())

    def _post(self, st):
        rng = np.random.default_rng(0)
        rows = []
        for n in range(300):
            sh = shown10("BC"[n % 2])
            c = sh[0] if rng.random() < 0.3 else ""
            rows.append(fb_row(f"r{n}", sh, clicked=c, purchased=c if c and rng.random() < .3 else "",
                               user=f"x{n}"))
        return self.L.initial_fit(st, pd.DataFrame(rows))

    def test_initial_fit_sets_anchor(self):
        st = state()
        post = self._post(st)
        self.assertIsNotNone(post.anchor)
        from recsys.thompson.features import CLICK_FEATURES
        self.assertGreater(post.click.m[CLICK_FEATURES.index("slot_1")], post.click.m[CLICK_FEATURES.index("slot_5")])

    def test_step_saves_and_bumps_version(self):
        st = state()
        post = self._post(st)
        with tempfile.TemporaryDirectory() as d:
            lr = self.L.Learner(st, post, Path(d))
            v0 = lr.current().version
            out = lr.step(pd.DataFrame([fb_row("z1", shown10(), clicked="p_B4")]))
            self.assertTrue(out["ok"])
            self.assertEqual(lr.current().version, v0 + 1)
            self.assertTrue((Path(d) / "posterior_latest.pkl").exists())
            self.assertGreaterEqual(len(list(Path(d).glob("posterior_v*.pkl"))), 1)

    def test_step_nonfinite_keeps_last_good(self):
        st = state()
        post = self._post(st)
        with tempfile.TemporaryDirectory() as d:
            lr = self.L.Learner(st, post, Path(d))
            st.items.loc[st.pid2i["p_B4"], "price"] = np.nan
            m0 = lr.current().click.m.copy()
            out = lr.step(pd.DataFrame([fb_row("z1", shown10(), clicked="p_B4")]))
            self.assertFalse(out["ok"])
            np.testing.assert_array_equal(lr.current().click.m, m0)

    def test_reset_to_anchor(self):
        st = state()
        post = self._post(st)
        with tempfile.TemporaryDirectory() as d:
            lr = self.L.Learner(st, post, Path(d))
            a = post.anchor[0].m.copy()
            lr.step(pd.DataFrame([fb_row("z1", shown10(), clicked="p_B4")] * 50))
            lr.reset_to_anchor()
            np.testing.assert_array_equal(lr.current().click.m, a)
            self.assertEqual(lr.current().items.m, {})


class TestWatermark(unittest.TestCase):
    def _learner(self, d):
        from recsys.thompson import learner as L
        st = state()
        rows = pd.DataFrame([fb_row(f"r{n}", shown10(), clicked=shown10()[0] if n % 3 == 0 else "", user=f"x{n}")
                             for n in range(100)])
        return L.Learner(st, L.initial_fit(st, rows), Path(d)), st

    def test_mature_margin(self):
        import inspect
        from recsys.thompson import learner as L
        self.assertGreaterEqual(inspect.signature(L.Learner.__init__).parameters["mature_s"].default, 480)

    def test_mark_kept_when_step_raises(self):
        import threading
        with tempfile.TemporaryDirectory() as d:
            lr, st = self._learner(d)
            mark0 = lr.mark
            lr.fetch = lambda: pd.DataFrame([fb_row("z1", shown10(), ts="2026-11-14 19:00:00")])
            def boom(rows):
                raise RuntimeError("transient")
            lr.step = boom
            stop = threading.Event()
            lr.every_s = 0.01
            t = threading.Thread(target=lr.loop, args=(stop,)); t.start()
            import time; time.sleep(0.05); stop.set(); t.join()
            self.assertEqual(lr.mark, mark0)

    def test_mark_advances_after_ok_step(self):
        import threading, time
        with tempfile.TemporaryDirectory() as d:
            lr, st = self._learner(d)
            calls = {"n": 0}
            def fetch():
                calls["n"] += 1
                return pd.DataFrame([fb_row("z1", shown10(), ts="2099-01-01 00:00:00")]) if calls["n"] == 1 \
                    else pd.DataFrame()
            lr.fetch = fetch
            lr.every_s = 0.01
            stop = threading.Event()
            t = threading.Thread(target=lr.loop, args=(stop,)); t.start()
            time.sleep(0.1); stop.set(); t.join()
            self.assertTrue(lr.mark.startswith("2099-01-01"))


if __name__ == "__main__":
    unittest.main()
