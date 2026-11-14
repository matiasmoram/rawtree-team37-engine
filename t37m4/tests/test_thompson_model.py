import tempfile
import unittest
from pathlib import Path

import numpy as np


def synth(n, w, seed=0):
    rng = np.random.default_rng(seed)
    X = np.column_stack([np.ones(n), rng.normal(size=(n, len(w) - 1))])
    p = 1 / (1 + np.exp(-X @ w))
    return X, (rng.random(n) < p).astype(float)


W = np.array([-3.0, 1.5, -1.0])


class TestBayesLogit(unittest.TestCase):
    def setUp(self):
        from recsys.thompson import model as M
        self.M = M

    def test_fit_recovers_weights(self):
        X, y = synth(20000, W)
        m = self.M.BayesLogit(3, prior_var=10.0)
        m.fit(X, y)
        self.assertLess(np.abs(m.m - W).max(), 0.15)

    def test_update_moves_toward_truth(self):
        m = self.M.BayesLogit(3, prior_var=10.0)
        X1, y1 = synth(2000, W, seed=1)
        m.fit(X1, y1)
        q0 = m.q.copy()
        X2, y2 = synth(20000, W, seed=2)
        for k in range(10):
            self.assertTrue(m.update(X2[k::10], y2[k::10]))
        batch = self.M.BayesLogit(3, prior_var=10.0)
        batch.fit(np.vstack([X1, X2]), np.concatenate([y1, y2]))
        self.assertLess(np.abs(m.m - batch.m).max(), 0.02)   # online ≈ batch MAP
        self.assertTrue((m.q > 5 * q0).all())                 # certainty grows with data
        self.assertLess(np.abs(m.m - W).max(), 0.15)

    def test_update_rejects_nonfinite(self):
        m = self.M.BayesLogit(3)
        X, y = synth(500, W)
        m.fit(X, y)
        m0, P0 = m.m.copy(), m.P.copy()
        X[3, 1] = np.nan
        self.assertFalse(m.update(X, y))
        np.testing.assert_array_equal(m.m, m0)
        np.testing.assert_array_equal(m.P, P0)

    def test_decay_floor(self):
        m = self.M.BayesLogit(3, prior_var=4.0)
        X, y = synth(5000, W)
        m.fit(X, y)
        P = m.P.copy()
        m.decay(0.5)
        np.testing.assert_allclose(m.P, 0.5 * P + 0.5 * np.eye(3) / 4.0)
        for _ in range(60):
            m.decay(0.5)
        np.testing.assert_allclose(m.P, np.eye(3) / 4.0, atol=1e-9)

    def test_sample_spread_shrinks_with_data(self):
        rng = np.random.default_rng(0)
        small, big = self.M.BayesLogit(3), self.M.BayesLogit(3)
        small.fit(*synth(300, W))
        big.fit(*synth(30000, W))
        s1 = np.std([small.sample(rng) for _ in range(300)], axis=0)
        s2 = np.std([big.sample(rng) for _ in range(300)], axis=0)
        self.assertTrue((s2 < s1).all())

    def test_clip_to_anchor(self):
        a = self.M.BayesLogit(3)
        a.fit(*synth(5000, W))
        m = a.copy()
        m.m = a.m + 100
        m.clip_to(a, k=4)
        np.testing.assert_allclose(m.m, a.m + 4 * a.std())


class TestPosterior(unittest.TestCase):
    def test_save_load_roundtrip_and_pbuy(self):
        from recsys.thompson import model as M
        post = M.Posterior.new(n_click=3, n_buy=2)
        post.click.fit(*synth(3000, W))
        post.items.update(np.array([7, 7, 8]), np.zeros(3), np.array([1.0, 1.0, 0.0]))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "post.pkl"
            post.save(p)
            back = M.Posterior.load(p)
        np.testing.assert_array_equal(back.click.m, post.click.m)
        self.assertEqual(back.items.mean(np.array([7]))[0], post.items.mean(np.array([7]))[0])
        d = back.mean_draw()
        Xc = np.array([[1, 0, 0], [1, 2, 0]]); Xb = np.array([[1, 0], [1, 0]])
        p = M.p_buy(d, Xc, Xb, np.array([7, 99]))
        self.assertEqual(p.shape, (2,))
        self.assertTrue(((p > 0) & (p < 1)).all())

    def test_item_offset_learns_good_item(self):
        from recsys.thompson import model as M
        off = M.ItemOffsets(sigma=0.5)
        base = np.full(4000, -3.0)
        rng = np.random.default_rng(0)
        y = (rng.random(4000) < 1 / (1 + np.exp(-(base + 1.0)))).astype(float)
        for k in range(10):
            off.update(np.full(400, 5), base[k::10], y[k::10])
        self.assertGreater(off.mean(np.array([5]))[0], 0.5)
        self.assertEqual(off.mean(np.array([6]))[0], 0.0)


if __name__ == "__main__":
    unittest.main()
