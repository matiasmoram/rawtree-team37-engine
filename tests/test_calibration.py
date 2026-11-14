"""Calibration math and fail-closed handling of artifacts used by serving."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from engine.calibration import (OnlineCalibration, fit_groups, group_key,
                                group_multipliers, shift_probability)


class TestCalibrationMath(unittest.TestCase):
    def test_position_bands_cover_all_ten_slots(self):
        self.assertEqual([group_key("s", i) for i in range(10)],
                         ["s|0"] * 3 + ["s|1"] * 3 + ["s|2"] * 4)

    def test_group_ratio_uses_purchase_pseudocount(self):
        p = np.full(200, .01)
        y = np.r_[np.ones(8), np.zeros(192)]
        groups = fit_groups(p, y, ["s"] * 200, [0] * 200, min_n=200, prior=5.)
        self.assertAlmostEqual(groups["s|0"]["multiplier"], (8 + 5) / (2 + 5))
        self.assertAlmostEqual(groups["s|0"]["expected"], 2)
        self.assertEqual(groups["s|0"]["observed"], 8)
        self.assertEqual(groups["s|0"]["n"], 200)

    def test_sparse_groups_remain_identity(self):
        groups = fit_groups([.01] * 199, [0] * 199, ["s"] * 199, [0] * 199)
        self.assertEqual(groups, {})
        np.testing.assert_array_equal(group_multipliers(groups, ["s", "missing"], [0, 9]), [1., 1.])

    def test_extreme_group_corrections_are_bounded(self):
        high = fit_groups([.0001] * 200, [1] * 200, ["s"] * 200, [0] * 200)
        low = fit_groups([.9] * 200, [0] * 200, ["s"] * 200, [0] * 200)
        self.assertEqual(high["s|0"]["multiplier"], 2.)
        self.assertEqual(low["s|0"]["multiplier"], .5)
        np.testing.assert_array_equal(group_multipliers(
            {"s|0": {"multiplier": 99}, "s|1": {"multiplier": .01}}, ["s", "s"], [0, 3]), [2., .5])

    def test_group_fit_is_row_order_invariant(self):
        p = np.linspace(.001, .03, 600)
        y = (np.arange(600) % 30 == 0).astype(int)
        subs = np.array(["a"] * 300 + ["b"] * 300)
        slots = np.array([0] * 300 + [9] * 300)
        perm = np.random.default_rng(37).permutation(len(p))
        first = fit_groups(p, y, subs, slots)
        second = fit_groups(p[perm], y[perm], subs[perm], slots[perm])
        self.assertEqual(set(first), set(second))
        for group in first:
            for field in ("n", "expected", "observed", "multiplier"):
                self.assertAlmostEqual(first[group][field], second[group][field])

    def test_probability_shift_preserves_order_and_has_expected_odds(self):
        p = np.array([0., .01, .1, .5, .9, 1.])
        result = shift_probability(p, np.log(2.))
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertTrue(np.all((result > 0) & (result < 1)))
        self.assertTrue(np.all(np.diff(result) > 0))
        self.assertAlmostEqual(result[3], 2 / 3)

    def test_fit_rejects_invalid_values_instead_of_emitting_bad_corrections(self):
        for p, y in (([float("nan")], [0]), ([float("inf")], [0]), ([-.1], [0]),
                     ([1.1], [0]), ([.1], [2]), ([.1], [-1]), ([.1], [float("nan")])):
            with self.subTest(p=p, y=y), self.assertRaises(ValueError):
                fit_groups(p, y, ["s"], [0], min_n=1)

    def test_fit_rejects_mismatched_lengths(self):
        with self.assertRaises(ValueError):
            fit_groups([.1, .2], [0], ["s", "s"], [0, 1], min_n=1)
        with self.assertRaises(ValueError):
            group_multipliers({}, ["s", "s"], [0])

    def test_shift_rejects_nonfinite_parameters(self):
        for p, shift in (([float("nan")], 0), ([float("inf")], 0), ([.1], float("nan"))):
            with self.subTest(p=p, shift=shift), self.assertRaises(ValueError):
                shift_probability(p, shift)


class TestOnlineCalibration(unittest.TestCase):
    def payload(self):
        return {"model_id": "model-a", "built_at": 1000.,
                "groups": {"s|0": {"multiplier": 1.5, "n": 300, "observed": 8, "expected": 4.},
                           "s|2": {"multiplier": .5, "n": 300, "observed": 1, "expected": 4.}}}

    def load_payload(self, payload, model_id="model-a"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "calibration.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return OnlineCalibration.load(path, model_id)

    def test_correct_model_applies_matching_slot_band_only(self):
        calibration = self.load_payload(self.payload())
        p = calibration.apply([.1, .1, .1, .1], ["s", "s", "s", "unknown"], [0, 3, 9, 0], 1001.)
        np.testing.assert_allclose(p, [.15, .1, .05, .1])

    def test_wrong_model_is_rejected(self):
        calibration = self.load_payload(self.payload(), "different-model")
        self.assertFalse(calibration.payload)
        np.testing.assert_allclose(calibration.apply([.1], ["s"], [0], 1001.), [.1])

    def test_future_and_stale_artifacts_are_not_applied(self):
        calibration = self.load_payload(self.payload())
        np.testing.assert_allclose(calibration.apply([.1], ["s"], [0], 999.), [.1])
        np.testing.assert_allclose(calibration.apply([.1], ["s"], [0], 8201.), [.1])
        np.testing.assert_allclose(calibration.apply([.1], ["s"], [0], 8200.), [.15])

    def test_loaded_invalid_json_shapes_and_values_fail_closed(self):
        payloads = [[], 1, "bad", {**self.payload(), "groups": []},
                    {**self.payload(), "built_at": "not-a-timestamp"},
                    {**self.payload(), "built_at": float("nan")},
                    {**self.payload(), "built_at": float("inf")},
                    {**self.payload(), "groups": {"s|0": {"multiplier": float("nan")}}},
                    {**self.payload(), "groups": {"s|0": {"multiplier": "bad"}}}]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertFalse(self.load_payload(payload).payload)

    def test_missing_or_truncated_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            self.assertFalse(OnlineCalibration.load(path, "model-a").payload)
            path.write_text('{"model_id":', encoding="utf-8")
            self.assertFalse(OnlineCalibration.load(path, "model-a").payload)

    def test_applied_corrections_are_finite_valid_probabilities(self):
        calibration = self.load_payload(self.payload())
        result = calibration.apply([0., .9, 1.], ["s"] * 3, [0, 0, 9], 1001.)
        self.assertTrue(np.all(np.isfinite(result)))
        self.assertTrue(np.all((result > 0) & (result < 1)))


if __name__ == "__main__":
    unittest.main()
