import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from tests.thompson_fixtures import state
from tests.test_thompson_learner import fb_row, shown10


def requests_df(n=40):
    return pd.DataFrame([dict(request_id=f"r_{k:04d}", ts="2026-11-14 18:00:00", user_id="u1" if k % 2 else f"n{k}",
                              is_new_user=bool(k % 3 == 0), context={"page": "product"},
                              recent_views=[{"product_id": "p_B2", "ts": "2026-11-14 17:59:00"}],
                              srv_now="2026-11-14 18:00:00.500") for k in range(n)])


class FakeResp:
    def __init__(self, data):
        self.data = data
        self.ok = True

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": self.data}


class FakeHttp:
    def __init__(self, fails, data):
        self.fails, self.data, self.calls = fails, data, 0

    def post(self, *a, **kw):
        self.calls += 1
        if self.calls <= self.fails:
            raise ConnectionError("down")
        return FakeResp(self.data)


class TestServe(unittest.TestCase):
    def setUp(self):
        from recsys.thompson.learner import Learner, initial_fit
        from recsys.thompson.serve import Server
        self.st = state()
        rows = pd.DataFrame([fb_row(f"r{n}", shown10("BC"[n % 2]), clicked=shown10("BC"[n % 2])[0] if n % 3 == 0 else "",
                                    user=f"x{n}") for n in range(200)])
        self.tmp = tempfile.TemporaryDirectory()
        self.lr = Learner(self.st, initial_fit(self.st, rows), Path(self.tmp.name))
        self.srv = Server(st=self.st, learner=self.lr, dry_run=True, log_path=Path(self.tmp.name) / "log.pkl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_answer_only_owned_requests(self):
        from recsys.thompson.guards import owns
        df = requests_df()
        out = self.srv.answer(df)
        self.assertEqual({a["request_id"] for a in out}, {r for r in df.request_id if owns(r)})
        self.assertTrue(all(a["model_version"] == "t37-m4" for a in out))

    def test_answer_valid_lists(self):
        out = self.srv.answer(requests_df())
        bought = {p for p, i in self.st.pid2i.items() if i in self.st.bought["u1"]}
        for a in out:
            self.assertEqual(len(set(a["items"])), 10)
            self.assertTrue(all(p in self.st.pid2i for p in a["items"]))
            self.assertFalse({self.st.pid2i[p] for p in a["items"]} & self.st.oos)
            if a["user_id"] == "u1":
                self.assertFalse(set(a["items"]) & bought)

    def test_answer_fallback_on_exception(self):
        from recsys.thompson import ranker
        real = ranker.rank
        calls = {"n": 0}

        def flaky(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return real(*a, **kw)

        with mock.patch("recsys.thompson.serve.rank", side_effect=flaky):
            out = self.srv.answer(requests_df(6))
        self.assertTrue(out)
        self.assertEqual(out[0]["fallback"], 1)
        self.assertEqual(len(set(out[0]["items"])), 10)
        with mock.patch("recsys.thompson.serve.rank", side_effect=RuntimeError("always")):
            out = self.srv.answer(requests_df(6))
        self.assertTrue(all(a["fallback"] == 3 and len(set(a["items"])) == 10 for a in out))

    def test_poll_error_survives(self):
        df = requests_df(10)
        http = FakeHttp(3, df.to_dict("records"))
        got = []
        for _ in range(4):
            got += self.srv.poll_once(http)
        self.assertEqual(http.calls, 4)
        self.assertEqual(got, [])                 # first successful poll is skipped (already-present requests)
        df2 = requests_df(20).assign(request_id=lambda d: d.request_id + "x")
        http.data = df2.to_dict("records")
        got = self.srv.poll_once(http)
        self.assertTrue(len(got) > 0)


class TestParallelPoll(TestServe):
    def test_parallel_claims_disjoint(self):
        import threading
        import time as _t

        class SlowSet(set):
            def __contains__(self, x):      # widen the check->update window so the threads interleave
                _t.sleep(0.001)
                return super().__contains__(x)

        self.srv.seen = SlowSet()
        ids = [f"r{k}" for k in range(50)]
        got, lock = [], threading.Lock()

        def worker():
            out = self.srv._claim(ids)
            with lock:
                got.extend(out)

        ts = [threading.Thread(target=worker) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(sorted(got), sorted(ids))   # every id claimed exactly once


if __name__ == "__main__":
    unittest.main()
