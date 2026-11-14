"""Regression checks for chronology, held-out calibration and clustered comparisons."""
import unittest

import numpy as np
import pandas as pd

from engine.learn.recent import (apply_calibration, apply_shift, fit_groups, fit_shift,
                                 paired_cluster_interval, positive_ranking, probability_metrics,
                                 temporal_split)


class RecentEvaluationTests(unittest.TestCase):
    def test_request_and_timestamp_ties_stay_together(self):
        rows = []
        for i in range(100):
            for slot in range(10):
                rows.append({"request_id": str(i), "ts": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(seconds=i // 2),
                             "purchase": int(slot == 2 and i % 9 == 0), "click": int(slot == 2)})
        frame = pd.DataFrame(rows)
        masks, info = temporal_split(frame)
        assignment = sum(np.asarray(m, dtype=int) for m in masks.values())
        np.testing.assert_array_equal(assignment, np.ones(len(frame)))
        partitions = []
        for name, mask in masks.items():
            partitions.append(set(frame.loc[mask, "request_id"]))
        for i, one in enumerate(partitions):
            for two in partitions[i + 1:]:
                self.assertFalse(one & two)
        for left, right in zip(list(masks), list(masks)[1:]):
            self.assertLess(frame.loc[masks[left], "ts"].max(), frame.loc[masks[right], "ts"].min())

    def test_inconsistent_request_timestamps_rejected(self):
        frame = pd.DataFrame({"request_id": ["same", "same"], "ts": [1, 2]})
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            temporal_split(frame)

    def test_shift_calibration_is_finite_with_no_positives(self):
        fit = fit_shift(np.zeros(100), np.full(100, .02))
        out = apply_shift(np.array([0, .01, 1]), fit["shift"])
        self.assertTrue(np.isfinite(out).all())
        self.assertTrue(((out > 0) & (out < 1)).all())
        self.assertLess(fit["shift"], 0)

    def test_global_shift_targets_separate_calibration_slice(self):
        y = np.r_[np.ones(20), np.zeros(980)]
        p = np.full(1000, .01)
        fit = fit_shift(y, p, strength=0)
        self.assertAlmostEqual(float(apply_shift(p, fit["shift"]).mean()), .02, places=8)

    def test_sparse_groups_are_skipped_and_ratios_bounded(self):
        frame = pd.DataFrame({"subcategory": ["a"] * 300 + ["b"] * 10,
                              "slot": [0] * 310})
        groups = fit_groups(frame, np.r_[np.ones(300), np.zeros(10)], np.full(310, .001))
        self.assertNotIn("b|0", groups)
        self.assertEqual(groups["a|0"]["multiplier"], 2.)
        shifted = apply_calibration(np.full(310, .01), {"shift": 0., "groups": groups}, frame)
        self.assertAlmostEqual(shifted[0], .02)
        self.assertAlmostEqual(shifted[-1], .01)

    def test_logged_positive_rank_and_pairing(self):
        frame = pd.DataFrame({"request_id": ["a"] * 4 + ["b"] * 4,
                              "user_id": ["u"] * 8, "slot": list(range(4)) * 2,
                              "purchase": [0, 0, 0, 1, 0, 1, 0, 0]})
        result = positive_ranking(frame, -frame.slot.to_numpy())
        self.assertEqual(result.loc["a", "rank"], 4)
        self.assertEqual(result.loc["b", "rank"], 2)
        self.assertEqual(result.loc["a", "top3"], 0)

    def test_bootstrap_clusters_users(self):
        result = paired_cluster_interval([1., 1., -1.], ["u", "u", "v"], n_boot=200)
        self.assertEqual(result["users"], 2)
        self.assertEqual(result["requests"], 3)
        self.assertAlmostEqual(result["mean"], 1 / 3)
        self.assertLessEqual(result["ci95"][0], result["mean"])
        self.assertGreaterEqual(result["ci95"][1], result["mean"])

    def test_no_positive_segment_keeps_diagnostics_without_auc(self):
        metrics = probability_metrics(np.zeros(5), np.full(5, .01))
        self.assertIsNone(metrics["auc"])
        self.assertEqual(metrics["positives"], 0)
        self.assertIsNotNone(metrics["logloss"])


if __name__ == "__main__":
    unittest.main()
