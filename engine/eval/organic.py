"""Next-purchase prediction on the organic event stream (``shop.history_events`` / ``shop.events``)."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Sequence

import numpy as np

from ..policies.base import Policy
from ..rt import RawTree
from ..snapshot import Snapshot
from ..types import Request, sql_ts
from .common import (SETTINGS, Case, EvalSet, Evaluator, PolicyRun, event_source, from_ms, hash_sample,
                     is_unknown_user, load_new_products, paged, run_policies, segment_masks, theta_at, to_ms)
from .stats import Metric, Row, summarize

log = logging.getLogger("eval.organic")

VARIANTS = ("next", "reshow")


def last_distinct(views: list[tuple[int, str]], k: int) -> list[tuple[str, int]]:
    """Last ``k`` distinct products of a chronological view list, each with its latest view ms, oldest first."""
    seen: set[str] = set()
    out: list[tuple[str, int]] = []
    for ms, pid in reversed(views):
        if pid not in seen:
            seen.add(pid)
            out.append((pid, ms))
            if len(out) == k:
                break
    return out[::-1]


class OrganicNextPurchaseEval(Evaluator):
    """Can the policy anticipate what a shopper is about to buy, from organic sessions in [T, T + window)?

    For each purchase of product q in a session (first purchase of q in that session, at or after T), build a
    pseudo-request and use q as the single label:

    * ``next`` (reported as evaluator ``organic``): request just before the FIRST view of q in the session. Recent
      views = the session's previous distinct views (at most ``max_views``, latest ts each); page = 'product' if there
      are views else 'home'. The policy must surface q before the shopper found it. Cases whose first view of q is at
      or before T are dropped (the request would predate the snapshot).
    * ``reshow`` (evaluator ``organic_reshow``): request at the purchase moment, recent views include q. Measures
      whether the policy re-surfaces items the shopper is considering.

    ``is_new_user`` = user unknown to the snapshot. Metrics: ``theta_hit`` (main) = THETA[rank of q] (0 if absent)
    and ``recall10`` = q in the list.

    Biases and limitations
    ----------------------
    * Organic purchases happened without our carousel: this measures agreement with what shoppers found by
      themselves, not the causal uplift of showing an item. Popular items are rewarded even if users would have
      bought them anyway.
    * Most purchased items are the first item viewed in the session, so ``next`` is dominated by 'home' requests
      with no context, where context-aware policies reduce to their fallback.
    * In the live stream (``shop.events``) sessions are emitted as bursts (events ~7 ms apart, view, cart and
      purchase of the bought item share one timestamp). Real inter-event timing is lost; only order is meaningful.
      Ties at the same millisecond are resolved by keeping views strictly before the first view (``next``) or at
      or before the purchase (``reshow``).
    * Pseudo-requests are not real carousel requests: real requests also carry views from earlier sessions and
      arrive at other moments; the page type is inferred, not observed.
    * Sessions are sampled by hash when there are more than ``max_sessions`` purchasing sessions; views before T
      are taken from at most ``lookback_hours`` before T.
    """

    name = "organic"

    def __init__(self, window_hours: float = 3.0, max_sessions: int = 20000, lookback_hours: float = 2.0,
                 max_views: int = 6, parts: int = 4, n_boot: int = 500, seed: int = 0) -> None:
        super().__init__(window_hours, n_boot, seed)
        self.max_sessions = max_sessions
        self.lookback_hours = lookback_hours
        self.max_views = max_views
        self.parts = parts

    def params(self) -> dict:
        return {"max_sessions": self.max_sessions, "lookback_hours": self.lookback_hours, "max_views": self.max_views}

    # ---- pull ---------------------------------------------------------------------------------------------------
    def pull(self, rt: RawTree, snap: Snapshot) -> EvalSet:
        t0, t1 = self.window(snap.T)
        src, latest = event_source(rt, t0 - timedelta(hours=self.lookback_hours), t1)
        info: dict = {"latest_event": str(latest)}
        complete = latest is not None and latest >= t1
        if src is None:
            return EvalSet(self.name, snap.T, self.window_hours, [], info, complete=complete)

        buy_in_window = f"et = 'purchase' AND ts >= '{sql_ts(t0)}'"
        n_sessions = int(rt.query(f"SELECT uniqExact(s) AS n FROM {src} WHERE {buy_in_window} {SETTINGS}", timeout=300)[0]["n"])
        rate = min(1.0, self.max_sessions / max(n_sessions, 1))
        info.update({"purchasing_sessions": n_sessions, "session_sample_rate": round(rate, 4)})
        rows = paged(rt, f"""
            SELECT s, any(u) AS u, any(dev) AS device, any(reg) AS region,
                   groupArrayIf((p, toUnixTimestamp64Milli(ts)), et = 'view') AS views,
                   groupArrayIf((p, toUnixTimestamp64Milli(ts)), {buy_in_window}) AS buys
            FROM {src}
            WHERE s IN (SELECT s FROM {src} WHERE {buy_in_window} AND {hash_sample('s', rate)}) AND {{part}}
            GROUP BY s {SETTINGS}""", self.parts, "s")

        t0_ms = to_ms(t0)
        cases: list[Case] = []
        skipped = {"no_view_of_purchase": 0, "first_view_before_T": 0}
        for row in rows:
            views = sorted((int(ms), str(p)) for p, ms in row["views"])
            first_buy: dict[str, int] = {}
            for p, ms in row["buys"]:
                first_buy[str(p)] = min(int(ms), first_buy.get(str(p), int(ms)))
            for q, buy_ms in sorted(first_buy.items(), key=lambda x: x[1]):
                q_views = [ms for ms, p in views if p == q and ms <= buy_ms]
                if not q_views:
                    skipped["no_view_of_purchase"] += 1
                    continue
                fv = q_views[0]
                for variant, req_ms, prior in (
                    ("next", fv - 1, [v for v in views if v[0] < fv]),
                    ("reshow", buy_ms, [v for v in views if v[0] <= buy_ms]),
                ):
                    if variant == "next" and fv <= t0_ms:
                        skipped["first_view_before_T"] += 1
                        continue
                    recent = [(p, from_ms(ms)) for p, ms in last_distinct(prior, self.max_views)]
                    req = Request(
                        request_id=f"{row['s']}|{q}|{variant}", ts=from_ms(req_ms), user_id=str(row["u"]),
                        is_new_user=is_unknown_user(str(row["u"]), snap), page="product" if recent else "home",
                        device=str(row["device"]), region=str(row["region"]), recent_views=recent,
                    )
                    cases.append(Case(req, {"q": q, "variant": variant}))
        info.update({"sessions_pulled": len(rows), **skipped,
                     **{f"cases_{v}": sum(c.label["variant"] == v for c in cases) for v in VARIANTS}})
        return EvalSet(self.name, snap.T, self.window_hours, cases, info, complete=complete,
                       new_products=load_new_products(rt))

    # ---- score --------------------------------------------------------------------------------------------------
    def score(self, policies: Sequence[Policy], snap: Snapshot, es: EvalSet) -> tuple[list[Row], dict[str, PolicyRun]]:
        rows: list[Row] = []
        all_runs: dict[str, PolicyRun] = {}
        for variant in VARIANTS:
            cases = [c for c in es.cases if c.label["variant"] == variant]
            if not cases:
                continue
            reqs = [c.req for c in cases]
            qs = [c.label["q"] for c in cases]
            runs = run_policies(policies, reqs, snap)
            segs = segment_masks(reqs, snap, es.new_products)
            ones = np.ones(len(cases))
            everyone = np.ones(len(cases), dtype=bool)
            theta, recall = {}, {}
            for name, run in runs.items():
                theta[name] = (np.array([theta_at(L, q) for L, q in zip(run.lists, qs)]), ones)
                recall[name] = (np.array([float(q in L) for L, q in zip(run.lists, qs)]), ones)
                prev = all_runs.get(name)
                all_runs[name] = run if prev is None else PolicyRun(
                    prev.lists + run.lists,
                    (prev.ms_per_call * len(prev.lists) + run.ms_per_call * len(run.lists)) / (len(prev.lists) + len(run.lists)),
                    prev.invalid + run.invalid)
            evaluator = self.name if variant == "next" else f"{self.name}_{variant}"
            rows += summarize(evaluator, [Metric("theta_hit", everyone, theta, main=True),
                                          Metric("recall10", everyone, recall)],
                              segs, n_boot=self.n_boot, seed=self.seed)
        return rows, all_runs
