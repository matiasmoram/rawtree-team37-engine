import tempfile
import unittest
from pathlib import Path

import pandas as pd


class TestReport(unittest.TestCase):
    def test_own_shown_counts_only_exact_lists(self):
        from recsys.thompson.report import own_shown
        a, b = [f"p{k}" for k in range(10)], [f"q{k}" for k in range(10)]
        log = pd.DataFrame([dict(request_id="r1", items=a, status="ok", ts=pd.Timestamp("2026-11-14 18:00")),
                            dict(request_id="r2", items=a, status="ok", ts=pd.Timestamp("2026-11-14 18:01")),
                            dict(request_id="r3", items=a, status="dropped_late", ts=pd.Timestamp("2026-11-14 18:02"))])
        fb = pd.DataFrame([dict(request_id="r1", shown=a, clicked="p1", purchased="p1"),
                           dict(request_id="r2", shown=b, clicked="q1", purchased="q1"),   # someone else's list shown
                           dict(request_id="r3", shown=a, clicked="", purchased="")])
        out = own_shown(log, fb)
        self.assertEqual(out["sent"], 2)
        self.assertEqual(out["shown_ours"], 1)
        self.assertEqual(out["buys_per_100"], 100.0)

    def test_weight_table(self):
        from recsys.thompson.features import CLICK_FEATURES, BUY_FEATURES
        from recsys.thompson.model import Posterior
        from recsys.thompson.report import weight_table
        with tempfile.TemporaryDirectory() as d:
            for v in (1, 2, 3):
                p = Posterior.new(len(CLICK_FEATURES), len(BUY_FEATURES))
                p.click.m[CLICK_FEATURES.index("slot_1")] = v
                p.version = v
                p.save(Path(d) / f"posterior_v{v:05d}.pkl")
            t = weight_table(Path(d), every=1)
        self.assertEqual(list(t.columns), ["v1", "v2", "v3"])
        self.assertEqual(t.loc["slot_1"].tolist(), [1.0, 2.0, 3.0])


if __name__ == "__main__":
    unittest.main()
