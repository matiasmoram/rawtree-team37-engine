"""Serving integration checks: no real submissions or process signals occur."""
from __future__ import annotations

import queue
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from engine.config import CACHE
from engine.content import ContentIndex
from engine.experiments import owns_request
from engine.live import LiveRunner
from engine.policies.lgbm import LgbmPolicy
from engine.policies.registry import get_policy
from engine.snapshot import Product, Snapshot
from engine.types import Request, parse_ts


NOW = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)


def fixture():
    products = {f"p{i}": Product(f"p{i}", "cat", "sub", "brand", 10., 10., "description", True)
                for i in range(30)}
    snap = Snapshot(NOW, products, {}, {}, {}, {}, {}, {}, {}, {}, {},
                    pop_global=list(products), pop_by_sub={"sub": list(products)}, sub_quality={"sub": 1.})
    req = Request("r1", NOW, "u", False, "product", "ios", "region",
                  [("p0", NOW - timedelta(seconds=1))])
    return req, snap


class Fixed:
    name = "fixed"

    def recommend(self, req, snap):
        return [f"p{i}" for i in range(10)]


class WithMetadata(Fixed):
    name = "meta"

    def recommend_with_metadata(self, req, snap):
        return self.recommend(req, snap), {"slate_propensity": .1, "explored": True}

    def exposure_metadata(self, req, snap, items):
        return {"model_id": "test-model", "base_probabilities": [.01] * len(items),
                "subcategories": [snap.products[p].sub for p in items]}


class TestLiveAnswer(unittest.TestCase):
    def runner(self, policy=None, dry_run=False, **kwargs):
        req, snap = fixture()
        runner = LiveRunner([(policy or Fixed(), 100)], "test_team", dry_run=dry_run, **kwargs)
        runner.snap = snap
        return runner, req

    def test_metadata_is_separate_from_submission_schema(self):
        runner, req = self.runner(WithMetadata())
        runner.answer(req)
        queued_req, submission = runner.outbox.get_nowait()
        record = runner.metadata_queue.get_nowait()
        self.assertEqual(queued_req, req)
        self.assertEqual(set(submission), {"request_id", "items", "model_version"})
        self.assertEqual(submission["model_version"], "t37-meta")
        self.assertEqual(record["items"], submission["items"])
        self.assertTrue(record["proposal_only"])
        self.assertTrue(record["metadata"]["propensity_valid"])
        self.assertEqual(len(record["metadata"]["base_probabilities"]), 10)
        self.assertEqual(runner.stats["answered"], 1)

    def test_validation_repair_invalidates_logged_propensity(self):
        class Duplicated(WithMetadata):
            def recommend(self, req, snap): return ["p0"] * 10
        runner, req = self.runner(Duplicated())
        runner.answer(req)
        _, submission = runner.outbox.get_nowait()
        record = runner.metadata_queue.get_nowait()
        self.assertEqual(len(set(submission["items"])), 10)
        self.assertFalse(record["metadata"]["propensity_valid"])

    def test_metadata_backpressure_preserves_response(self):
        runner, req = self.runner(WithMetadata())
        runner.metadata_queue = queue.Queue(maxsize=1)
        runner.metadata_queue.put({"occupied": True})
        runner.answer(req)
        self.assertEqual(runner.outbox.qsize(), 1)
        self.assertEqual(runner.metadata_queue.qsize(), 1)

    def test_metadata_failure_preserves_response(self):
        class BadMetadata(WithMetadata):
            def exposure_metadata(self, *args): raise ValueError("invalid calibration")
        runner, req = self.runner(BadMetadata())
        runner.answer(req)
        _, submission = runner.outbox.get_nowait()
        self.assertEqual(submission["model_version"], "t37-meta")
        self.assertEqual(len(submission["items"]), 10)

    def test_policy_crash_uses_valid_safety_response(self):
        class Broken(Fixed):
            def recommend(self, req, snap): raise ValueError("broken policy")
        runner, req = self.runner(Broken())
        runner.answer(req)
        _, submission = runner.outbox.get_nowait()
        self.assertEqual(submission["model_version"], "t37-safety")
        self.assertEqual(len(set(submission["items"])), 10)

    def test_dryrun_does_not_queue_exposure_records(self):
        runner, req = self.runner(WithMetadata(), dry_run=True)
        runner.answer(req)
        self.assertTrue(runner.metadata_queue.empty())
        self.assertEqual(runner.outbox.qsize(), 1)


class TestLiveSend(unittest.TestCase):
    def runner(self, dry_run=False):
        req, snap = fixture()
        req.ts = datetime.now(timezone.utc)
        runner = LiveRunner([(Fixed(), 100)], "test_team", dry_run=dry_run)
        runner.snap = snap
        runner._tls = threading.local()
        runner._tls.rt = MagicMock()
        runner.answer(req)
        return runner, runner.outbox.get_nowait()

    def test_send_uses_only_submission_columns(self):
        runner, batch = self.runner()
        runner._send([batch])
        runner._tls.rt.insert.assert_called_once()
        call = runner._tls.rt.insert.call_args
        self.assertEqual(call.args, ("submissions", [batch[1]]))
        self.assertEqual(call.kwargs["database"], "test_team")
        self.assertGreater(call.kwargs["timeout"], 0)
        self.assertLessEqual(call.kwargs["timeout"], 2.)
        self.assertEqual(runner.stats["pushed"], 1)
        self.assertIsNotNone(runner.last_success_at)

    def test_dryrun_send_never_inserts_or_marks_real_success(self):
        runner, batch = self.runner(dry_run=True)
        runner._send([batch])
        runner._tls.rt.insert.assert_not_called()
        self.assertIsNone(runner.last_success_at)
        self.assertEqual(runner.stats["pushed"], 1)

    def test_transport_failure_requeues_without_claiming_success(self):
        runner, batch = self.runner()
        runner._tls.rt.insert.side_effect = ConnectionError("transport failed")
        runner._send([batch])
        self.assertEqual(runner.stats["push_fail"], 1)
        self.assertEqual(runner.stats["pushed"], 0)
        self.assertEqual(runner.outbox.get_nowait(), batch)

    def test_row_retry_success_updates_health(self):
        runner, batch = self.runner()
        runner._tls.rt.insert.side_effect = [RuntimeError("insert HTTP 400: bad batch"), {}]
        runner._send([batch])
        self.assertEqual(runner.stats["pushed"], 1)
        self.assertIsNotNone(runner.last_success_at)
        self.assertEqual(len(runner.latencies), 1)

    def test_expired_batch_is_dropped_when_worker_starts(self):
        runner, batch = self.runner()
        batch[0].ts = datetime.now(timezone.utc) - timedelta(seconds=10)
        runner._send([batch])
        runner._tls.rt.insert.assert_not_called()
        self.assertEqual(runner.stats["late"], 1)
        self.assertEqual(runner.stats["pushed"], 0)

    def test_worker_revalidates_stock_after_collection(self):
        runner, batch = self.runner()
        runner.snap.products["p0"].active = False
        runner._send([batch])
        runner._tls.rt.insert.assert_called_once()
        submitted = runner._tls.rt.insert.call_args.args[1][0]["items"]
        self.assertEqual(len(set(submitted)), 10)
        self.assertNotIn("p0", submitted)
        self.assertTrue(all(runner.snap.is_valid(p) for p in submitted))


class TestDryRunAndOwnership(unittest.TestCase):
    def test_dryrun_takeover_preserves_pid_and_does_not_signal(self):
        with tempfile.TemporaryDirectory() as d, patch("engine.live.LOGS", Path(d)), patch("engine.live.os.kill") as kill:
            p = Path(d) / "live.pid"
            p.write_text("12345")
            runner = LiveRunner([(Fixed(), 100)], "test_team", dry_run=True)
            runner.takeover()
            self.assertEqual(p.read_text(), "12345")
            kill.assert_not_called()

    def test_dryrun_reporter_does_not_write_shared_health(self):
        runner = LiveRunner([(Fixed(), 100)], "test_team", dry_run=True)
        runner.stop = MagicMock()
        runner.stop.wait.side_effect = [False, True]
        with patch("engine.live.RawTree"), patch("engine.live.write_health") as write:
            runner.reporter()
            write.assert_not_called()

    def test_dryrun_metadata_writer_does_not_touch_shared_log(self):
        runner = LiveRunner([(Fixed(), 100)], "test_team", dry_run=True)
        runner.stop.set()
        with tempfile.TemporaryDirectory() as d, patch("engine.live.LOGS", Path(d)):
            runner.metadata_writer()
            self.assertFalse((Path(d) / "exposure_metadata.jsonl").exists())

    def test_poller_only_claims_owned_requests(self):
        runner = LiveRunner([(Fixed(), 100)], "test_team", dry_run=True, shard_index=1, shard_count=3)
        req, snap = fixture()
        runner.snap = snap
        runner.stop = MagicMock()
        runner.stop.is_set.side_effect = [False, True]
        runner.answer = MagicMock()
        rows = [{"request_id": str(i), "ts": NOW, "user_id": "u", "is_new_user": False,
                 "page": "home", "device": "ios", "region": "ES", "recent_views": []} for i in range(12)]
        with patch("engine.live.RawTree") as rt, patch("engine.live.time.sleep"):
            rt.return_value.query.return_value = rows
            runner.poller()
        answered = {call.args[0].request_id for call in runner.answer.call_args_list}
        expected = {str(i) for i in range(12) if owns_request(str(i), 1, 3)}
        self.assertEqual(answered, expected)
        self.assertEqual(set(runner.seen), expected)


class TestFixedExperimentDeadline(unittest.TestCase):
    def test_before_deadline_preserves_experimental_arms(self):
        experiment, fallback = [(Fixed(), 100)], [(WithMetadata(), 100)]
        runner = LiveRunner(experiment, "test_team", dry_run=True,
                            experiment_until=NOW.timestamp() + 10, after_arms=fallback)
        runner.clock_offset = 0
        with patch("engine.live.time.time", return_value=NOW.timestamp()):
            self.assertEqual(runner.pick("r1").name, "fixed")
        self.assertIs(runner.arms, experiment)
        self.assertIsNotNone(runner.experiment_until)

    def test_deadline_restores_fixed_fallback_once_without_restart(self):
        experiment, fallback = [(Fixed(), 100)], [(WithMetadata(), 100)]
        runner = LiveRunner(experiment, "test_team", dry_run=True,
                            experiment_until=NOW.timestamp(), after_arms=fallback)
        runner.clock_offset = 0
        with patch("engine.live.time.time", return_value=NOW.timestamp()):
            self.assertEqual(runner.pick("r1").name, "meta")
        self.assertIs(runner.arms, fallback)
        self.assertIsNone(runner.experiment_until)
        # Once closed, a later local clock adjustment cannot revive the experiment.
        with patch("engine.live.time.time", return_value=NOW.timestamp() - 100):
            self.assertEqual(runner.pick("r1").name, "meta")
        self.assertIs(runner.arms, fallback)

    def test_missing_or_invalid_fallback_rejected(self):
        for fallback in (None, [], [(Fixed(), 99)]):
            with self.assertRaises(ValueError):
                LiveRunner([(Fixed(), 100)], "test_team", experiment_until=NOW.timestamp(), after_arms=fallback)


class TestTimestampParsing(unittest.TestCase):
    def test_metadata_iso_offsets_without_fraction(self):
        self.assertEqual(parse_ts("2026-11-14T15:00:00+00:00"), NOW)
        self.assertEqual(parse_ts("2026-11-14T16:00:00+01:00"), NOW)
        self.assertEqual(parse_ts("2026-11-14T14:00:00-01:00"), NOW)

    def test_nanos_and_timezone_are_both_preserved(self):
        expected = NOW + timedelta(microseconds=123456)
        self.assertEqual(parse_ts("2026-11-14 15:00:00.123456789"), expected)
        self.assertEqual(parse_ts("2026-11-14T16:00:00.123456789+01:00"), expected)
        self.assertEqual(parse_ts("2026-11-14T15:00:00.123456789Z"), expected)

    def test_naive_rawtree_timestamp_means_utc(self):
        self.assertEqual(parse_ts("2026-11-14 15:00:00"), NOW)


@unittest.skipUnless((CACHE / "lgbm_recent.txt").exists(), "recent model not yet trained")
class TestLearnedPolicyIntegration(unittest.TestCase):
    def test_recent_registered_model_scores_and_logs_finite_probabilities(self):
        policy = get_policy("lgbm-recent")
        req, snap = fixture()
        items = policy.recommend(req, snap)
        metadata = policy.exposure_metadata(req, snap, items)
        self.assertEqual(len(items), 10)
        self.assertEqual(len(set(items)), 10)
        probs = np.asarray(metadata["base_probabilities"])
        self.assertEqual(probs.shape, (10,))
        self.assertTrue(np.isfinite(probs).all())
        self.assertTrue(((probs >= 0) & (probs <= 1)).all())
        self.assertEqual(len(metadata["subcategories"]), 10)

    def test_content_merged_candidates_enforce_information_cutoff(self):
        policy = get_policy("lgbm-recent")
        req, snap = fixture()
        snap.products["future"] = Product("future", "cat", "sub", "brand", 10., 10., "future", True,
                                          is_new=True, added_ts=NOW + timedelta(hours=1))
        snap.pop_global.insert(0, "future")
        candidates, _, _ = policy.score_candidates(req, snap)
        self.assertNotIn("future", candidates)

    def test_content_artifact_is_loaded_before_request_handling(self):
        with patch("engine.content.ContentIndex.load", return_value=ContentIndex()) as load:
            policy = LgbmPolicy("learned", str(CACHE / "lgbm_recent.txt"), num_threads=2, use_content=True)
            construction_calls = load.call_count
            req, snap = fixture()
            policy.recommend(req, snap)
            self.assertGreaterEqual(construction_calls, 1)
            self.assertEqual(load.call_count, construction_calls)


if __name__ == "__main__":
    unittest.main()
