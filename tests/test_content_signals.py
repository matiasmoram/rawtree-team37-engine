"""Safety and information-cutoff tests for content and recent co-visitation."""
import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.content import ContentIndex, borrowed_quality, content_candidates
from engine.policies.content import ContentPolicy, RecentCovisPolicy
from engine.policies.evidence import EvidencePolicy
from engine.recent_covis import RecentCovisIndex, build_recent_covis, save_recent_covis
from engine.snapshot import Product, Snapshot
from engine.types import Request


NOW = datetime(2026, 11, 14, 14, tzinfo=timezone.utc)


def fixture():
    products = {f"old{i}": Product(f"old{i}", "cat", "sub", "brand", 10., 10., "description", True)
                for i in range(15)}
    products["new"] = Product("new", "cat", "sub", "brand", 10., 10., "new", True,
                              is_new=True, added_ts=NOW - timedelta(hours=1))
    products["inactive"] = Product("inactive", "cat", "sub", "brand", 10., 10., "off", False)
    products["future"] = Product("future", "cat", "sub", "brand", 10., 10., "future", True,
                                 is_new=True, added_ts=NOW + timedelta(hours=1))
    snap = Snapshot(NOW, products, {}, {}, {}, {}, {}, {}, {}, {}, {},
                    pop_global=[f"old{i}" for i in range(15)], sub_quality={"sub": 1.0})
    req = Request("r1", NOW, "u", True, "product", "ios", "region", [("old0", NOW - timedelta(seconds=1))])
    return req, snap


class ContentTests(unittest.TestCase):
    def test_loader_validates_bounds_and_builds_reverse(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "content.json"
            p.write_text(json.dumps({"new": [["old0", .95], ["old0", .9], ["inactive", .92],
                                            ["bad", float("nan")], ["low", .2], ["self", 2.0]]}))
            index = ContentIndex.load(p)
            self.assertEqual(index.forward["new"], (("old0", .95), ("inactive", .92)))
            self.assertEqual(index.reverse["old0"], (("new", .95),))

    def test_missing_corrupt_and_noncontent_artifacts_degrade(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "none.json"
            self.assertEqual(ContentIndex.load(p).forward, {})
            p.write_text("{broken")
            self.assertEqual(ContentIndex.load(p).forward, {})
            p.write_text(json.dumps({"source_kind": "collaborative", "neighbors": {"new": [["old0", .95]]}}))
            self.assertEqual(ContentIndex.load(p).forward, {})

    def test_reverse_exposes_new_item_and_forward_borrows_peers(self):
        req, snap = fixture()
        index = ContentIndex({"new": (("old0", .95),)}, {"old0": (("new", .95),)})
        self.assertIn("new", content_candidates(req, snap, index))
        req.recent_views = [("new", NOW - timedelta(seconds=1))]
        snap.covis_vb = {"old0": [("old2", 5.)]}
        found = content_candidates(req, snap, index)
        self.assertIn("old0", found)
        self.assertIn("old2", found)
        self.assertTrue(all(0 <= v <= 1 for v in found.values()))

    def test_candidates_do_not_expose_unknown_inactive_or_future(self):
        req, snap = fixture()
        index = ContentIndex({}, {"old0": (("new", .95), ("inactive", .95), ("future", .95), ("unknown", .95))})
        self.assertEqual(set(content_candidates(req, snap, index)), {"new"})

    def test_borrowed_prior_diminishes_as_own_history_grows(self):
        _, snap = fixture()
        index = ContentIndex({"new": (("old0", .95),)}, {})
        quality = lambda pid: 1.0 if pid == "new" else 3.0
        cold = borrowed_quality("new", snap, index, quality)
        snap.stats["new"] = {"view_all": 300.}
        warm = borrowed_quality("new", snap, index, quality)
        self.assertGreater(cold, warm)
        self.assertGreater(warm, 1.0)
        self.assertEqual(borrowed_quality("old1", snap, index, quality), 3.0)

    def test_content_missing_matches_base_and_does_not_mutate_snapshot(self):
        req, snap = fixture()
        # A PIT snapshot cannot contain the future product; remove the deliberate bad fixture here.
        del snap.products["future"]
        base = EvidencePolicy("base", bought_factor=.02, covis_gain=0.,
                              rel={"user_viewed": 2.5, "same_cat": .25, "same_sub": .25})
        policy = ContentPolicy(index=ContentIndex())
        original = dict(snap.products)
        self.assertEqual(policy.recommend(req, snap), base.recommend(req, snap))
        self.assertEqual(snap.products, original)

    def test_content_repurchase_penalty_and_output_validity(self):
        req, snap = fixture()
        snap.user_buy = {"u": {"new": (1, NOW - timedelta(minutes=1))}}
        index = ContentIndex({"new": (("old0", .95),)}, {"old0": (("new", .95),)})
        policy = ContentPolicy(index=index)
        self.assertEqual(policy.item_multiplier(req, snap, "new"), 1.)
        items = policy.recommend(req, snap)
        self.assertEqual(len(items), 10)
        self.assertEqual(len(set(items)), 10)
        self.assertNotIn("new", items)
        self.assertNotIn("future", items)
        self.assertTrue(all(snap.is_valid(p) for p in items))

    def test_old_pickled_snapshots_without_recent_buys_still_serve(self):
        req, snap = fixture()
        del snap.recent_user_buys
        for policy in (ContentPolicy(index=ContentIndex()), RecentCovisPolicy(index=RecentCovisIndex())):
            items = policy.recommend(req, snap)
            self.assertEqual(len(items), 10)
            self.assertTrue(all(snap.is_valid(p) for p in items))


class RecentCovisTests(unittest.TestCase):
    def test_cutoff_and_staleness_are_enforced(self):
        index = RecentCovisIndex(NOW, {"p": (("q", 4.),)}, {})
        self.assertEqual(index.candidates(["p"], NOW - timedelta(microseconds=1)), {})
        self.assertIn("q", index.candidates(["p"], NOW))
        self.assertEqual(index.candidates(["p"], NOW + timedelta(hours=13)), {})

    def test_saved_index_round_trips_and_limits_per_source(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "covis.json"
            payload = {"version": 1, "as_of": NOW.isoformat(),
                       "vv": {"p": [[f"q{i}", i + 1.] for i in range(100)]}, "vb": {}}
            save_recent_covis(payload, p)
            index = RecentCovisIndex.load(p)
            self.assertEqual(len(index.vv["p"]), 40)
            self.assertEqual(index.built_at, NOW)
            self.assertFalse(list(Path(d).glob("*.tmp")))

    def test_query_is_bounded_and_purchase_order_is_chronological(self):
        class Recorder:
            def __init__(self): self.queries = []
            def query(self, sql, **kwargs):
                self.queries.append(sql)
                return [{"src_id": "p", "dst_id": "q", "weight": .5}]
        rt = Recorder()
        payload = build_recent_covis(rt, NOW, window_hours=3, half_life_hours=6, top=10, session_cap=20)
        self.assertEqual(payload["vv"]["p"], [["q", .5]])
        self.assertEqual(len(rt.queries), 2)
        for sql in rt.queries:
            self.assertIn("2026-11-14 11:00:00.000", sql)
            self.assertIn("ts::DateTime64(3) < '2026-11-14 14:00:00.000'", sql)
            self.assertIn("LIMIT 20 BY sid", sql)
            self.assertIn("LIMIT 10 BY src_id", sql)
            self.assertIn("max_threads = 2", sql)
            self.assertIn("exp2(", sql)
        self.assertNotIn("a.first_t <= b.first_t", rt.queries[0])
        self.assertIn("a.first_t <= b.first_t", rt.queries[1])

    def test_recent_policy_rejects_future_matrix(self):
        req, snap = fixture()
        index = RecentCovisIndex(NOW + timedelta(seconds=1), {"old0": (("old1", 1.),)}, {})
        self.assertEqual(RecentCovisPolicy(index=index).extra_candidates(req, snap), {})

    def test_invalid_query_parameters_rejected_before_network(self):
        for kwargs in ({"window_hours": 0}, {"window_hours": 25}, {"half_life_hours": 0},
                       {"top": 41}, {"session_cap": 1}):
            with self.assertRaises(ValueError): build_recent_covis(None, NOW, **kwargs)


if __name__ == "__main__":
    unittest.main()
