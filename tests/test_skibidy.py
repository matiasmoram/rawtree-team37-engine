"""Offline tests for SkibidyPolicy (synthetic candidates, no RawTree, no LightGBM)."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from test_cartfirst import NOW, make_snapshot, req  # noqa: E402
from engine.learn.linucb import exposure_weight  # noqa: E402
from engine.policies.skibidy import NAMES, D, SkibidyPolicy  # noqa: E402

N = 60
HIDDEN = "log_view_3h"      # feature the prior knows nothing about (prior 0)


class Fake(SkibidyPolicy):
    def __init__(self, snap, seed=0, name="skibidy-v1", **kw):
        super().__init__(name=name, seed=seed, **kw)
        self.pids = list(snap.products)[:N]
        self.r = np.random.default_rng(seed + 100)

    def candidates_and_features(self, req, snap):
        X = np.zeros((N, D - 1))
        X[:, NAMES.index(HIDDEN)] = self.r.normal(size=N)
        X[:, NAMES.index("is_last_view")] = (self.r.random(N) < 0.1)
        self.X = X
        return self.pids, X


class SkibidyTests(unittest.TestCase):
    def test_valid_list_excludes_bought_and_has_prior_sense(self):
        snap = make_snapshot(); snap.user_buy["u"] = {"p0": (1, NOW), "p1": (1, NOW)}
        pol = Fake(snap, explore_frac=0.0)
        out = pol.recommend(req("u"), snap)
        self.assertEqual(len(set(out)), 10)
        self.assertFalse({"p0", "p1"} & set(out))
        w = pol.weights()
        self.assertGreater(w["in_cart"], 0); self.assertLess(w["bought_in_event"], 0)

    def test_learns_hidden_signal(self):
        snap = make_snapshot()
        pol = Fake(snap, explore_frac=0.3, seed=1)
        rng = np.random.default_rng(7)
        clicks = 0
        for i in range(5000):
            r = req(f"u{i}"); r.request_id = f"r{i}"
            items = pol.recommend(r, snap)
            idx = {p: j for j, p in enumerate(pol.pids)}
            z_true = -5.5 + 0.9 * pol.X[:, NAMES.index(HIDDEN)] + 1.0 * pol.X[:, NAMES.index("is_last_view")]
            clicked = ""
            for k, pid in enumerate(items, 1):
                if not clicked and rng.random() < exposure_weight(k) / (1 + np.exp(-z_true[idx[pid]])):
                    clicked = pid
            clicks += bool(clicked)
            pol.observe([{"request_id": r.request_id, "served_by": "team", "shown": items,
                          "model_version": "t37-skibidy-v1", "clicked": clicked, "purchased": clicked}])
        w = pol.weights()
        self.assertGreater(w[HIDDEN], 0.2, w)
        self.assertGreater(pol.stats["explored"], 1000)

    def test_ignores_fallback_and_unknown(self):
        snap = make_snapshot(); pol = Fake(snap)
        r = req("u"); r.request_id = "rx"; pol.recommend(r, snap)
        self.assertEqual(pol.observe([{"request_id": "rx", "served_by": "fallback"}]), 0)
        self.assertEqual(pol.observe([{"request_id": "zz", "served_by": "team"}]), 0)

    def test_repaired_or_mismatched_slate_is_not_used_as_negative_feedback(self):
        snap = make_snapshot(); pol = Fake(snap, explore_frac=0.0)
        r = req("u"); r.request_id = "repaired"
        shown = pol.recommend(r, snap)
        before = pol.theta.copy()
        changed = list(shown); changed[0], changed[1] = changed[1], changed[0]
        self.assertEqual(pol.observe([{"request_id": r.request_id, "served_by": "team", "shown": changed,
                                       "model_version": "t37-skibidy-v1"}]), 0)
        self.assertTrue(np.array_equal(before, pol.theta))

    def test_ignores_identical_slate_attributed_to_another_arm(self):
        snap = make_snapshot(); pol = Fake(snap, explore_frac=0.0)
        r = req("u"); r.request_id = "same-slate"
        shown = pol.recommend(r, snap)
        before = pol.theta.copy()
        self.assertEqual(pol.observe([{"request_id": r.request_id, "served_by": "team", "shown": shown,
                                       "model_version": "t37-cf-v1", "clicked": shown[0]}]), 0)
        self.assertTrue(np.array_equal(before, pol.theta))


if __name__ == "__main__":
    unittest.main()


class PersistTests(unittest.TestCase):
    def test_state_survives_restart(self):
        import tempfile, pathlib
        snap = make_snapshot(); a = Fake(snap, name="skibidy-test-persist")
        a.state_path = pathlib.Path(tempfile.mkdtemp()) / "s.npz"
        r = req("u"); r.request_id = "r1"; slate = a.recommend(r, snap)
        a.observe([{"request_id": "r1", "served_by": "team", "shown": slate,
                    "model_version": "t37-skibidy-test-persist", "clicked": slate[0], "purchased": ""}])
        a.save_state()
        b = Fake(snap, name="skibidy-test-persist"); b.state_path = a.state_path
        self.assertTrue(b.load_state())
        self.assertTrue(np.allclose(a.theta, b.theta)); self.assertEqual(a.std.n, b.std.n)
