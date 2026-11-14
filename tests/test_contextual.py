from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine.contextual import ContextIndex, context_tables, pair_key, save_contextual, share_lifts
from engine.policies.contextual import ContextualPolicy
from engine.policies.evidence import EvidencePolicy
from engine.snapshot import Product, Snapshot
from engine.types import Request

NOW = datetime(2026, 11, 14, 15, 40, tzinfo=timezone.utc)


def snap_fixture():
    products = {f"p{i}": Product(f"p{i}", "cat", "sub", "brand", 10., 10., "item", True)
                for i in range(35)}
    snap = Snapshot(NOW - timedelta(minutes=5), products, {}, {}, {}, {}, {}, {}, {}, {}, {})
    snap.pop_global = list(products)
    snap.pop_by_sub = {"sub": list(products)}
    return snap


def index_fixture():
    rows = tuple((f"p{i}", 1. / (i + 2)) for i in range(35))
    tables = {"global": {"*": rows}, "device": {"ios": rows}, "region": {"ES": rows},
              "pair": {pair_key("ios", "ES"): rows}}
    support = {"global": {"*": {"events": 2000, "mass": 100.}},
               "device": {"ios": {"events": 1000, "mass": 50.}},
               "region": {"ES": {"events": 800, "mass": 30.}},
               "pair": {pair_key("ios", "ES"): {"events": 600, "mass": 20.}}}
    return ContextIndex(NOW, tables, support, {"sub": 2.}, {"brand": 2.})


def request(device="ios", region="ES", ts=None, viewed=None, new=True):
    return Request("r", ts or NOW + timedelta(seconds=1), "u", new, "home", device, region,
                   viewed or [])


class TestContextIndex(unittest.TestCase):
    def test_fallback_pair_device_region_global(self):
        index = index_fixture()
        self.assertEqual(index.context(request())[1], "pair")
        index.support["pair"][pair_key("ios", "ES")]["events"] = 20
        self.assertEqual(index.context(request())[1], "device")
        self.assertEqual(index.context(request(device="unknown"))[1], "region")
        self.assertEqual(index.context(request(device="unknown", region="unknown"))[1], "global")

    def test_insufficient_intent_mass_falls_back_despite_many_views(self):
        index = index_fixture()
        index.support["pair"][pair_key("ios", "ES")]["mass"] = .1
        self.assertEqual(index.context(request())[1], "device")

    def test_future_and_stale_index_are_identity(self):
        index = index_fixture()
        for ts in (NOW - timedelta(seconds=1), NOW + timedelta(hours=2, seconds=1)):
            self.assertEqual(index.context(request(ts=ts)), ((), "unavailable"))
            self.assertEqual(index.trend("sub", "brand", ts), 1.)
        self.assertTrue(index.usable_at(NOW + timedelta(hours=2)))

    def test_unknown_group_trend_is_identity_and_lift_is_bounded(self):
        index = index_fixture()
        self.assertEqual(index.trend("unknown", "unknown", NOW), 1.)
        self.assertEqual(index.trend("sub", "brand", NOW), 2.)

    def test_tables_are_smoothed_toward_parent_and_order_invariant(self):
        rows = [{"pid": "a", "device": "ios", "region": "US", "events": 1000, "weight": 20.},
                {"pid": "b", "device": "ios", "region": "ES", "events": 5, "weight": 1.},
                {"pid": "b", "device": "android", "region": "ES", "events": 500, "weight": 10.}]
        tables, support = context_tables(rows)
        pair = dict(tables["pair"][pair_key("ios", "ES")])
        self.assertGreater(pair["a"], 0.)
        self.assertLess(pair["b"], 1.)
        self.assertAlmostEqual(sum(pair.values()), 1.)
        second, support2 = context_tables(list(reversed(rows)))
        self.assertEqual(tables, second)
        self.assertEqual(support, support2)

    def test_share_lift_is_compositional_and_requires_support(self):
        products = snap_fixture().products
        products["p0"].sub = "a"
        products["p1"].sub = "b"
        baseline = [{"pid": "p0", "events": 1000, "weight": 50.},
                    {"pid": "p1", "events": 1000, "weight": 50.}]
        same = [{"pid": "p0", "events": 10000, "weight": 500.},
                {"pid": "p1", "events": 10000, "weight": 500.}]
        lifts = share_lifts(same, baseline, products, attr="sub")
        self.assertAlmostEqual(lifts["a"]["lift"], 1.)
        sparse = [{"pid": "p0", "events": 5, "weight": 1.},
                  {"pid": "p1", "events": 1000, "weight": 1000.}]
        lifts = share_lifts(sparse, baseline, products, attr="sub")
        self.assertEqual(lifts["a"]["lift"], 1.)
        self.assertTrue(.5 <= lifts["b"]["lift"] <= 2.)

    def test_bad_signal_values_are_rejected(self):
        with self.assertRaises(ValueError):
            context_tables([{"pid": "a", "device": "ios", "region": "ES", "events": 1,
                             "weight": float("nan")}])

    def test_atomic_artifact_and_bad_load_fail_closed(self):
        index = index_fixture()
        payload = {"version": 1, "source_kind": "organic_contextual", "as_of": NOW.isoformat(),
                   "tables": index.tables, "support": index.support,
                   "subcategory_lift": {"sub": {"lift": 1.4}}, "brand_lift": {}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "context.json"
            save_contextual(payload, path)
            loaded = ContextIndex.load(path)
            self.assertEqual(loaded.context(request())[1], "pair")
            with self.assertRaises(ValueError):
                save_contextual({"bad": float("nan")}, path)
            self.assertEqual(ContextIndex.load(path).context(request())[1], "pair")
            path.write_text(json.dumps({**payload, "as_of": "2026-11-14T15:40:00"}))
            self.assertIsNone(ContextIndex.load(path).built_at)
            path.write_text("[]")
            self.assertIsNone(ContextIndex.load(path).built_at)
            self.assertEqual(len(list(Path(tmp).iterdir())), 1)


class TestContextualPolicy(unittest.TestCase):
    def test_inactive_future_and_bought_items_not_added(self):
        snap = snap_fixture()
        snap.products["p0"].active = False
        snap.products["p1"].added_ts = NOW + timedelta(minutes=1)
        snap.user_buy = {"u": {"p2": (1, NOW - timedelta(days=1))}}
        snap.recent_user_buys = {"u": {"p3"}}
        policy = ContextualPolicy(index=index_fixture())
        extra = policy.extra_candidates(request(), snap)
        self.assertFalse(set(extra) & {"p0", "p1", "p2", "p3"})
        scored = dict((pid, value) for value, pid in policy.scored_candidates(request(), snap))
        self.assertNotIn("p0", scored)
        self.assertNotIn("p1", scored)
        self.assertLess(scored["p2"], scored["p4"])
        self.assertEqual(policy.item_multiplier(request(), snap, "p2"), 1.)

    def test_known_preferences_are_preserved(self):
        snap = snap_fixture()
        snap.user_view = {"u": {"p3": (4, NOW - timedelta(days=1))}}
        policy = ContextualPolicy(index=index_fixture())
        self.assertEqual(policy.item_multiplier(request(), snap, "p3"), 1.)
        self.assertEqual(policy.recommend(request(), snap)[0], "p3")

    def test_known_user_with_views_does_not_add_context_candidates(self):
        snap = snap_fixture()
        req = request(viewed=[("p4", NOW - timedelta(seconds=1))], new=False)
        policy = ContextualPolicy(index=index_fixture())
        self.assertEqual(policy.extra_candidates(req, snap), {})
        self.assertEqual(policy.item_multiplier(req, snap, "p4"), 1.)

    def test_unavailable_index_equals_nocovis_control(self):
        snap = snap_fixture()
        req = request(ts=NOW - timedelta(seconds=1))
        policy = ContextualPolicy(index=index_fixture())
        control = EvidencePolicy("control", bought_factor=.02, covis_gain=0., rel={"user_viewed": 1.5})
        self.assertEqual(policy.recommend(req, snap), control.recommend(req, snap))

    def test_valid_lists_and_bounded_context_effect(self):
        snap = snap_fixture()
        policy = ContextualPolicy(index=index_fixture())
        items = policy.recommend(request(), snap)
        self.assertEqual(len(items), 10)
        self.assertEqual(len(set(items)), 10)
        self.assertTrue(all(snap.is_valid(p) for p in items))
        self.assertTrue(all(.5 <= policy.item_multiplier(request(), snap, p) <= 2. for p in items))


if __name__ == "__main__":
    unittest.main()
