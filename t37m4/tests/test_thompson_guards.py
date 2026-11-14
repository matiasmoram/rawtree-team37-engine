import hashlib
import unittest

import pandas as pd


class TestGuards(unittest.TestCase):
    def setUp(self):
        from recsys.thompson import guards as G
        self.G = G

    def test_owns_matches_engine(self):
        ids = [f"r_{k:016x}" for k in range(1000)]
        for r in ids:
            engine = int(hashlib.md5(r.encode()).hexdigest()[:8], 16) % 2
            self.assertEqual(self.G.owns(r, 1, 2), engine == 1)
            self.assertNotEqual(self.G.owns(r, 0, 2), self.G.owns(r, 1, 2))   # shards partition the ids
        share = sum(self.G.owns(r) for r in ids) / len(ids)
        self.assertTrue(0.4 < share < 0.6)

    def test_collision_rate(self):
        ours = [r for r in (f"r{k}" for k in range(400)) if self.G.owns(r)][:10]
        rows = [dict(request_id=r, mv="t37-m4") for r in ours]
        rows += [dict(request_id=ours[0], mv="t37-cf-v1"), dict(request_id=ours[1], mv="t37-cf-v1")]
        rows += [dict(request_id="other", mv="t37-cf-v1")]
        self.assertAlmostEqual(self.G.collision_rate(pd.DataFrame(rows), "t37-m4"), 0.2)
        self.assertEqual(self.G.collision_rate(pd.DataFrame(columns=["request_id", "mv"]), "t37-m4"), 0.0)

    def test_perfguard_sequence(self):
        g = self.G.PerfGuard()
        self.assertEqual(g.observe(1.0, 1.5, 400), "ok")      # 1st loss
        self.assertEqual(g.observe(1.0, 1.5, 400), "reset")   # 2nd consecutive loss
        self.assertEqual(g.observe(1.0, 1.5, 400), "ok")
        self.assertEqual(g.observe(1.0, 1.5, 400), "stop")
        g = self.G.PerfGuard()
        self.assertEqual(g.observe(1.0, 1.5, 400), "ok")
        self.assertEqual(g.observe(2.0, 1.5, 400), "ok")      # a win clears the streak
        self.assertEqual(g.observe(1.0, 1.5, 400), "ok")
        self.assertEqual(g.observe(1.0, 1.5, 100), "ok")      # too few requests: ignored

    def test_parse_state(self):
        j = {"teams": [{"team_id": "team_37", "on_time": 97.0, "versions": [
            dict(model_version="t37-m4", requests=500, conversion=1.6, cold_conversion=2.0, revenue_per_request=.7),
            dict(model_version="t37-cf-v1", requests=600, conversion=1.4, cold_conversion=1.9, revenue_per_request=.9),
            dict(model_version="t37-skibidy-v1", requests=200, conversion=3.0, cold_conversion=2.0, revenue_per_request=.9)]},
            {"team_id": "team_06", "versions": [dict(model_version="x", requests=900, conversion=2.2)]}]}
        w = self.G.parse_state(j, "t37-m4", "team_37")
        self.assertEqual((w.ours, w.ctrl, w.n_ours, w.ctrl_version), (1.6, 1.4, 500, "t37-cf-v1"))
        self.assertIsNone(self.G.parse_state({"teams": []}, "t37-m4", "team_37"))


class TestControl(unittest.TestCase):
    def test_named_control_and_margin(self):
        from recsys.thompson import guards as G
        j = {"teams": [{"team_id": "team_37", "versions": [
            dict(model_version="t37-m4", requests=500, conversion=1.5),
            dict(model_version="t37-cf-v1", requests=600, conversion=1.6),
            dict(model_version="t37-skibidy-v1", requests=600, conversion=2.4)]}]}
        w = G.parse_state(j, "t37-m4", "team_37", control="t37-cf-v1")
        self.assertEqual(w.ctrl_version, "t37-cf-v1")
        g = G.PerfGuard(margin=0.1)
        self.assertEqual(g.observe(1.5, 1.6, 500), "ok")   # within 10%: not a loss
        self.assertEqual(g.observe(1.5, 1.6, 500), "ok")
        self.assertEqual(g.observe(1.0, 1.6, 500), "ok")
        self.assertEqual(g.observe(1.0, 1.6, 500), "reset")


if __name__ == "__main__":
    unittest.main()
