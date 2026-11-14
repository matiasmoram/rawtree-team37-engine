"""Replay invariants: chronology, complete observed support and honest metrics."""
import copy
import unittest
from datetime import datetime, timedelta, timezone

from engine.eval.replay import (evaluate_replay, focused_session_policy, positive_gain,
                                rerank_observed, sample_feedback)
from engine.policies.evidence import EvidencePolicy
from engine.snapshot import Product, Snapshot
from engine.types import Request


T = datetime(2026, 11, 14, 14, tzinfo=timezone.utc)


def fixture():
    products = {f"p{i}": Product(f"p{i}", "c", "s", "b", 10., 10., "description", True)
                for i in range(30)}
    snap = Snapshot(T, products, {}, {}, {}, {}, {}, {}, {}, {}, {},
                    pop_global=[f"p{i}" for i in range(15)], sub_quality={"s": 1.})
    req = Request("r", T + timedelta(minutes=1), "u", False, "product", "ios", "ES",
                  [("p0", T + timedelta(seconds=1))])
    return req, snap


def feedback(req, shown=None, clicked="", purchased=""):
    return {"request_id": req.request_id, "ts": req.ts, "user_id": req.user_id,
            "is_new_user": req.is_new_user, "page": req.page, "device": req.device,
            "region": req.region, "recent_views": [{"product_id": p, "ts": ts} for p, ts in req.recent_views],
            "shown": shown or [f"p{i}" for i in range(10)], "clicked": clicked, "purchased": purchased,
            "served_by": "team", "fallback_reason": "", "model_version": "logged-model"}


class ReplayTests(unittest.TestCase):
    def test_every_observed_item_is_scored_without_mutating_policy(self):
        req, snap = fixture()
        policy = EvidencePolicy("test", bought_factor=.02, covis_gain=0.)
        shown = [f"p{i}" for i in range(20, 30)]  # outside normal candidates/popularity
        self.assertFalse(set(shown) & {p for _, p in policy.scored_candidates(req, snap)})
        ranking = rerank_observed(policy, req, snap, shown)
        self.assertEqual(set(ranking), set(shown))
        self.assertEqual(ranking, shown)  # tie handling preserves logged order
        self.assertEqual(tuple(policy.extra_candidates(req, snap)), ())
        self.assertFalse(set(shown) & {p for _, p in policy.scored_candidates(req, snap)})

    def test_missing_or_inactive_observed_items_are_explicitly_unsupported(self):
        req, snap = fixture()
        policy = EvidencePolicy("test")
        shown = [f"p{i}" for i in range(10)]
        snap.products["p1"].active = False
        self.assertIsNone(rerank_observed(policy, req, snap, shown))
        report = evaluate_replay([feedback(req)], snap, [policy], n_boot=5)
        self.assertEqual(report["unsupported_observed_lists"], 1)
        self.assertEqual(report["segments"]["all"]["models"]["test"]["observed_list_purchase_ranking"]["positive_requests"], 0)

    def test_future_snapshot_is_rejected(self):
        req, snap = fixture()
        snap.T = req.ts + timedelta(seconds=1)
        with self.assertRaisesRegex(ValueError, "cutoff"):
            evaluate_replay([feedback(req)], snap, [EvidencePolicy("test")], n_boot=5)

    def test_feedback_sampling_ignores_labels_and_never_splits_requests(self):
        req, snap = fixture()
        rows = []
        for i in range(100):
            r = copy.copy(req)
            r.request_id = str(i)
            r.ts += timedelta(seconds=i)
            rows.append(feedback(r))
        sampled = [r["request_id"] for r in sample_feedback(rows, 20)]
        for row in rows: row["purchased"] = "p0"
        self.assertEqual(sampled, [r["request_id"] for r in sample_feedback(rows, 20)])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            sample_feedback([rows[0], rows[0]], 10)

    def test_catalogue_and_recent_buys_are_replayed_strictly_before_request(self):
        req, snap = fixture()
        seen = []
        class Observe(EvidencePolicy):
            def recommend(self, request, pit):
                seen.append((request.request_id, pit.products["p0"].active,
                             set(pit.recent_user_buys.get("u", set())), tuple(request.recent_views)))
                return super().recommend(request, pit)
        rows = []
        for i, seconds in enumerate((5, 10, 11)):
            current = copy.copy(req)
            current.request_id = str(i)
            current.ts = T + timedelta(seconds=seconds)
            current.recent_views = [("p5", T), ("p6", T + timedelta(seconds=20))]
            rows.append(feedback(current))
        update = {"pid": "p0", "uts": T + timedelta(seconds=10), "change": "out_of_stock",
                  "cat": "c", "sub": "s", "brand": "b", "price": 10., "descr": "off", "active": False}
        buys = {"u": ([T + timedelta(seconds=9), T + timedelta(seconds=10), T + timedelta(seconds=50)],
                       ["p1", "p2", "p3"])}
        report = evaluate_replay(rows, snap, [Observe("test")], updates=[update], recent_buys=buys, n_boot=5)
        self.assertEqual([r[1] for r in seen], [True, True, False])
        self.assertEqual([r[2] for r in seen], [set(), {"p1"}, {"p1", "p2"}])
        self.assertTrue(all(r[3] == (("p5", T),) for r in seen))
        self.assertEqual(report["future_views_dropped"], 3)
        self.assertTrue(snap.products["p0"].active)  # source snapshot was not mutated

    def test_cold_segment_uses_platform_flag(self):
        req, snap = fixture()
        req.is_new_user = True
        snap.user_view[req.user_id] = {"p1": (1, T)}  # known in snapshot but platform says new
        report = evaluate_replay([feedback(req)], snap, [EvidencePolicy("test")], n_boot=5)
        self.assertEqual(report["segments"]["cold_request"]["requests"], 1)
        self.assertEqual(report["segments"]["new_user"]["requests"], 1)

    def test_catalogue_updates_sort_by_instant_not_iso_text(self):
        req, snap = fixture()
        req.ts = T + timedelta(hours=1)
        states = []
        class Observe(EvidencePolicy):
            def recommend(self, request, pit):
                states.append(pit.products["p0"].active)
                return super().recommend(request, pit)
        base = {"pid": "p0", "change": "stock", "cat": "c", "sub": "s", "brand": "b",
                "price": 10., "descr": "item"}
        updates = [{**base, "uts": "2026-11-14T15:30:00+01:00", "active": True},
                   {**base, "uts": "2026-11-14T14:45:00+00:00", "active": False}]
        evaluate_replay([feedback(req)], snap, [Observe("test")], updates=updates, n_boot=5)
        self.assertEqual(states, [False])

    def test_proxy_metrics_are_not_named_or_claimed_as_simulator_conversion(self):
        req, snap = fixture()
        report = evaluate_replay([feedback(req, clicked="p2", purchased="p2")], snap,
                                  [EvidencePolicy("test")], n_boot=5)
        self.assertFalse(report["counterfactual_policy_value_estimated"])
        self.assertFalse(report["automatic_promotion"])
        metrics = report["segments"]["all"]["models"]["test"]
        self.assertIn("observed_purchase_recall_proxy", metrics)
        self.assertNotIn("expected_conversion", metrics)
        interval = metrics["paired_purchase_ndcg_vs_logged_order"]
        self.assertEqual(interval["requests"], 1)
        self.assertEqual(interval["users"], 1)

    def test_observed_label_outside_shown_is_a_data_error(self):
        req, snap = fixture()
        with self.assertRaisesRegex(ValueError, "absent from shown"):
            evaluate_replay([feedback(req, purchased="p29")], snap, [EvidencePolicy("test")], n_boot=5)

    def test_focused_variant_is_explicit_and_not_fitted(self):
        policy = focused_session_policy()
        self.assertEqual(policy.name, "ev-v4-session")
        self.assertEqual(policy.rel["earlier_view"], 3.)
        self.assertEqual(policy.rel["user_viewed"], 1.)
        self.assertEqual(policy.bought_factor, .02)

    def test_positive_gain_is_zero_for_unshown_positive_not_missing_negative(self):
        self.assertIsNone(positive_gain(["a"], ""))
        self.assertEqual(positive_gain(["a"], "b")["ndcg"], 0.)
        self.assertEqual(positive_gain(["a", "b"], "a")["ndcg"], 1.)


if __name__ == "__main__":
    unittest.main()
