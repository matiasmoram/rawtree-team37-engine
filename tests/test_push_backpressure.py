"""Regression checks for bounded HTTP push admission.

No RawTree network calls, no submissions and no process signals.
"""
from __future__ import annotations

import threading
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from engine.live import LiveRunner, PUSH_WORKERS
from engine.snapshot import Product, Snapshot
from engine.types import Request


class Fixed:
    name = "fixed"
    def recommend(self, req, snap):
        return [f"p{i}" for i in range(10)]


def runner_and_batch():
    runner = LiveRunner([(Fixed(), 100)], "team_37", dry_run=True)
    products = {
        f"p{i}": Product(f"p{i}", "c", "s", "b", 12.0, 12.0, "d", True)
        for i in range(12)
    }
    runner.snap = Snapshot(
        datetime.now(timezone.utc), products, {}, {}, {}, {}, {}, {}, {}, {}, {},
        pop_global=list(products),
    )
    req = Request("test-reliability-r1", datetime.now(timezone.utc),
                  "u", False, "home", "ios", "ES")
    runner.answer(req)
    return runner, runner.outbox.get_nowait()


class PushAdmissionTests(unittest.TestCase):
    def test_bounded_worker_releases_slot_on_success(self):
        runner, batch = runner_and_batch()
        self.assertTrue(runner.push_slots.acquire(blocking=False))
        runner._send = MagicMock()
        runner._send_bounded([batch])
        runner._send.assert_called_once()
        for _ in range(PUSH_WORKERS):
            self.assertTrue(runner.push_slots.acquire(blocking=False))
        self.assertFalse(runner.push_slots.acquire(blocking=False))

    def test_bounded_worker_releases_slot_on_error(self):
        runner, batch = runner_and_batch()
        self.assertTrue(runner.push_slots.acquire(blocking=False))
        runner._send = MagicMock(side_effect=RuntimeError("transient"))
        with self.assertRaises(RuntimeError):
            runner._send_bounded([batch])
        for _ in range(PUSH_WORKERS):
            self.assertTrue(runner.push_slots.acquire(blocking=False))
        self.assertFalse(runner.push_slots.acquire(blocking=False))

    def test_saturated_pool_requeues_instead_of_creating_future(self):
        runner, batch = runner_and_batch()
        for _ in range(PUSH_WORKERS):
            self.assertTrue(runner.push_slots.acquire(blocking=False))
        with patch("engine.live.ThreadPoolExecutor") as pool, patch("engine.live.time.sleep"):
            runner.stop = MagicMock()
            runner.stop.is_set.side_effect = [False, True]
            runner.pusher()
            pool.return_value.submit.assert_not_called()
            self.assertEqual(runner.outbox.get_nowait(), batch)
            self.assertEqual(runner.stats["push_saturated"], 1)

    def test_unsaturated_pool_admits_only_one_batch(self):
        runner, batch = runner_and_batch()
        with patch("engine.live.ThreadPoolExecutor") as pool, patch("engine.live.time.sleep"):
            runner.stop = MagicMock()
            runner.stop.is_set.side_effect = [False, True]
            runner.pusher()
            pool.return_value.submit.assert_called_once()
            self.assertEqual(pool.return_value.submit.call_args.args[0], runner._send_bounded)
            self.assertEqual(pool.return_value.submit.call_args.args[1], [batch])


if __name__ == "__main__":
    unittest.main()
