"""Serving/updater contract: residual corrections are learned against a fixed base."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from engine.calibration import OnlineCalibration, group_multipliers, shift_probability
from engine.features import FEATURES, FIDX
from engine.learn.scoring import ServingModel
from engine.policies.lgbm import LgbmPolicy
from scripts.refresh_calibration import build_calibration


class FakeBooster:
    def predict(self, X, num_threads=1):
        return np.full(len(X), .04)


class CalibrationParityTests(unittest.TestCase):
    def setUp(self):
        self.now = 1800000000.
        self.items = [f"p{i}" for i in range(10)]
        self.req = SimpleNamespace(ts=datetime.fromtimestamp(self.now, timezone.utc))
        self.snap = SimpleNamespace(products={p: SimpleNamespace(sub="s") for p in self.items})
        self.X = np.zeros((10, len(FEATURES)), dtype=np.float32)
        self.X[:, FIDX["slot"]] = range(10)
        self.groups = {"s|0": {"multiplier": 1.5}, "s|1": {"multiplier": 1.2}, "s|2": {"multiplier": .8}}
        model = ServingModel.__new__(ServingModel)
        model.booster = FakeBooster()
        model.num_threads = 1
        model._lock = threading.Lock()
        model.kind = "factored"
        model.pc = {"kind": "rate", "p": .5}
        model.meta = {"calibration": {"kind": "logit_shift", "shift": float(np.log(2)), "groups": self.groups}}
        self.policy = LgbmPolicy.__new__(LgbmPolicy)
        self.policy.model = model
        self.policy.model_id = "identity"
        self.policy.online_calibration = OnlineCalibration({
            "model_id": "identity", "built_at": self.now - 1,
            "groups": {"s|0": {"multiplier": .5}, "s|1": {"multiplier": .5}, "s|2": {"multiplier": .5}}})

    def test_global_static_and_online_layers_are_each_applied_once(self):
        slots = list(range(10))
        expected_base = shift_probability(np.full(10, .04 * .5), np.log(2))
        expected_base *= group_multipliers(self.groups, ["s"] * 10, slots)
        base = self.policy._probabilities(self.req, self.snap, self.items, self.X, slots, online=False)
        online = self.policy._probabilities(self.req, self.snap, self.items, self.X, slots, online=True)
        np.testing.assert_allclose(base, expected_base, rtol=1e-13)
        np.testing.assert_allclose(online, expected_base * .5, rtol=1e-13)

    def test_metadata_does_not_record_already_online_corrected_probabilities(self):
        with patch("engine.policies.lgbm.build_context", return_value=object()), \
                patch("engine.policies.lgbm.featurize", return_value=self.X):
            metadata = self.policy.exposure_metadata(self.req, self.snap, self.items)
        expected = self.policy._probabilities(self.req, self.snap, self.items, self.X, list(range(10)), online=False)
        np.testing.assert_allclose(metadata["base_probabilities"], expected)
        self.assertEqual(metadata["model_id"], "identity")

    def proposal(self, rid="r", age=180):
        return {"request_id": rid,
                "ts": datetime.fromtimestamp(self.now - age, timezone.utc).isoformat(),
                "items": self.items,
                "metadata": {"model_id": "identity", "propensity_valid": True,
                             "base_probabilities": [.01] * 10, "subcategories": ["s"] * 10}}

    def test_repeated_refresh_replaces_residual_instead_of_compounding(self):
        rows = [self.proposal(f"r{i}") for i in range(100)]
        feedback = {r["request_id"]: {"sb": "team", "shown": self.items, "purchased": "p0" if i % 10 == 0 else ""}
                    for i, r in enumerate(rows)}
        first = build_calibration(rows, feedback, "identity", self.now, min_n=200)
        second = build_calibration(rows, feedback, "identity", self.now + 1, min_n=200)
        self.assertEqual(first["groups"], second["groups"])
        self.assertAlmostEqual(first["expected_purchases"], 10.)
        self.assertEqual(first["observed_purchases"], 10)
        self.assertEqual(first["accepted_requests"], 100)

    def test_exact_maturity_boundary_and_unknown_fingerprint(self):
        rows = [self.proposal("mature", 120), self.proposal("too-recent", 119.999),
                self.proposal("stale", 7200.001), self.proposal("unknown", 180)]
        rows[-1]["metadata"]["model_id"] = "other"
        feedback = {r["request_id"]: {"sb": "team", "shown": self.items, "purchased": ""} for r in rows}
        result = build_calibration(rows, feedback, "identity", self.now, min_n=1)
        self.assertEqual(result["accepted_requests"], 1)

    def test_identity_checked_at_load_and_temporal_bounds_checked_at_apply(self):
        data = {"model_id": "other", "built_at": 1000., "groups": {"s|0": {"multiplier": 2.}}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            calibration = OnlineCalibration.load(path, "identity")
        self.assertFalse(calibration.payload)
        valid_identity = OnlineCalibration({**data, "model_id": "identity"})
        np.testing.assert_allclose(valid_identity.apply([.1], ["s"], [0], 999.), [.1])
        np.testing.assert_allclose(valid_identity.apply([.1], ["s"], [0], 8201.), [.1])


if __name__ == "__main__":
    unittest.main()
