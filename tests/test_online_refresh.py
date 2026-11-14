import copy
import unittest
from datetime import datetime, timezone

from scripts.refresh_calibration import build_calibration


class OnlineRefreshTests(unittest.TestCase):
    def setUp(self):
        self.now = 1800000000.0
        self.items = [f"p{i}" for i in range(10)]
        self.row = {"request_id": "r1", "ts": datetime.fromtimestamp(self.now - 180, timezone.utc).isoformat(),
                    "items": self.items, "metadata": {"model_id": "model", "propensity_valid": True,
                    "base_probabilities": [0.01] * 10, "subcategories": ["sub"] * 10}}
        self.feedback = {"r1": {"sb": "team", "shown": self.items, "purchased": "p3"}}

    def run_fit(self, rows=None, feedback=None):
        return build_calibration(rows or [self.row], feedback or self.feedback, "model", self.now, min_n=1)

    def test_actual_exposure_not_proposal_count_and_duplicate(self):
        result = self.run_fit([self.row, self.row])
        self.assertEqual(result["accepted_requests"], 1)
        self.assertAlmostEqual(result["expected_purchases"], 0.1)
        self.assertEqual(result["observed_purchases"], 1)
        self.assertEqual(result["groups"]["sub|1"]["observed"], 1)

    def test_arbitration_loser_wrong_order_and_fallback_are_excluded(self):
        for patch in ({"shown": list(reversed(self.items))}, {"sb": "fallback"}):
            feedback = copy.deepcopy(self.feedback)
            feedback["r1"].update(patch)
            self.assertEqual(self.run_fit(feedback=feedback)["accepted_requests"], 0)

    def test_incomplete_predictions_repaired_or_wrong_model_excluded(self):
        for patch in ({"model_id": "other"}, {"base_probabilities": [0.1]}, {"propensity_valid": False}):
            row = copy.deepcopy(self.row)
            row["metadata"].update(patch)
            self.assertEqual(self.run_fit([row])["accepted_requests"], 0)

    def test_maturity_and_temporal_window(self):
        for age in (30, 8000, -1):
            row = copy.deepcopy(self.row)
            row["ts"] = datetime.fromtimestamp(self.now - age, timezone.utc).isoformat()
            self.assertEqual(self.run_fit([row])["accepted_requests"], 0)


if __name__ == "__main__":
    unittest.main()
