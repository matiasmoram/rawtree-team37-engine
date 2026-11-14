"""Real live requests (``shop.requests``) labelled with the same user's later organic purchases and carts."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Sequence

import numpy as np

from ..policies.base import Policy
from ..rt import RawTree
from ..snapshot import Snapshot
from ..types import Request, sql_ts
from .common import (SETTINGS, THETA, Case, EvalSet, Evaluator, PolicyRun, event_source, is_unknown_user,
                     load_new_products, paged, run_policies, segment_masks, views_before)
from .stats import Metric, Row, summarize

log = logging.getLogger("eval.live")


def ndcg_theta(items: Sequence[str], rel: dict[str, float]) -> float:
    """THETA-weighted gain of ``items`` divided by the best achievable gain for these labels (1.0 = ideal order)."""
    gain = sum(THETA[i] * rel.get(p, 0.0) for i, p in enumerate(items[:len(THETA)]))
    best_rels = sorted(rel.values(), reverse=True)[:len(THETA)]
    ideal = sum(THETA[i] * r for i, r in enumerate(best_rels))
    return float(gain / ideal) if ideal > 0 else 0.0


class LiveRequestEval(Evaluator):
    """Score policies on the real live requests in [T, T + window).

    The request is used exactly as served (context, recent views before ts, the platform's own ``is_new_user``).
    Label: products the same user_id purchases (weight ``purchase_weight``) or adds to cart (``cart_weight``) in the
    organic stream within ``horizon_minutes`` after the request ts; a product with both keeps the max weight.

    Metrics, on requests with at least one label:
    * ``ndcg_theta`` (main): sum_i THETA[i] * rel(item_i) / best possible such sum for that request.
    * ``hit_any``: share of labelled requests where the list contains at least one labelled product.
    ``label_coverage`` (policy ``(data)``): share of requests with any label, per segment.

    Biases and limitations
    ----------------------
    * Low and selective coverage: only requests whose user buys or carts something soon after are scored, which
      over-represents active buyers; the segment mix of scored requests differs from all requests.
    * The label is organic behaviour, not a reaction to our carousel: it rewards predicting what the user does
      anyway. In this dataset the requests' recent views are not the same products as the user's organic events,
      so the request context is only weakly informative about the label (context-aware policies gain little).
    * Requests whose label horizon extends past the newest event are censored (dropped, counted in info); the eval
      set is cached only once the window plus horizon is fully available.
    * Static snapshot at T: stock changes and new products after T are unknown to the policy, while labels may
      include products added after T (they can never be hit).
    """

    name = "live"

    def __init__(self, window_hours: float = 3.0, horizon_minutes: float = 30.0, purchase_weight: float = 1.0,
                 cart_weight: float = 0.3, parts: int = 4, n_boot: int = 500, seed: int = 0) -> None:
        super().__init__(window_hours, n_boot, seed)
        self.horizon_minutes = horizon_minutes
        self.purchase_weight = purchase_weight
        self.cart_weight = cart_weight
        self.parts = parts

    def params(self) -> dict:
        return {"horizon_minutes": self.horizon_minutes, "purchase_weight": self.purchase_weight,
                "cart_weight": self.cart_weight}

    # ---- pull ---------------------------------------------------------------------------------------------------
    def pull(self, rt: RawTree, snap: Snapshot) -> EvalSet:
        t0, t1 = self.window(snap.T)
        horizon = timedelta(minutes=self.horizon_minutes)
        where = f"ts::DateTime64(3) >= '{sql_ts(t0)}' AND ts::DateTime64(3) < '{sql_ts(t1)}'"
        req_rows = paged(rt, f"""
            SELECT request_id::String AS request_id, ts::DateTime64(3) AS ts, user_id::String AS user_id,
                   is_new_user::Bool AS is_new_user, context.page::String AS page, context.device::String AS device,
                   context.region::String AS region, recent_views
            FROM shop.requests WHERE {where} AND {{part}} {SETTINGS}""", self.parts, "request_id::String")
        src, latest = event_source(rt, t0, t1 + horizon)
        info: dict = {"requests": len(req_rows), "latest_event": str(latest)}
        if not req_rows or src is None:
            return EvalSet(self.name, snap.T, self.window_hours, [], info, complete=False)

        label_rows = paged(rt, f"""
            SELECT r.rid AS rid, groupArray((e.p, e.et)) AS labels
            FROM (SELECT request_id::String AS rid, user_id::String AS u, ts::DateTime64(3) AS t
                  FROM shop.requests WHERE {where} AND {{part}}) AS r
            INNER JOIN (SELECT u, p, et, ts AS t FROM {src} WHERE et IN ('purchase', 'add_to_cart')) AS e ON r.u = e.u
            WHERE e.t > r.t AND e.t <= r.t + INTERVAL {int(self.horizon_minutes * 60)} SECOND
            GROUP BY rid {SETTINGS}""", self.parts, "request_id::String")
        weight = {"purchase": self.purchase_weight, "add_to_cart": self.cart_weight}
        labels: dict[str, dict[str, float]] = {}
        for r in label_rows:
            rel: dict[str, float] = {}
            for pid, et in r["labels"]:
                rel[str(pid)] = max(rel.get(str(pid), 0.0), weight[str(et)])
            labels[r["rid"]] = rel

        cases: list[Case] = []
        censored = dropped_views = 0
        for r in req_rows:
            req = Request.from_row(r)
            if latest is None or req.ts + horizon > latest:
                censored += 1  # label window not fully observed yet
                continue
            n_views = len(req.recent_views)
            req.recent_views = views_before(req.recent_views, req.ts)
            dropped_views += n_views - len(req.recent_views)
            cases.append(Case(req, labels.get(req.request_id, {})))
        cases.sort(key=lambda c: c.req.ts)
        n_lab = sum(bool(c.label) for c in cases)
        disagree = sum(c.req.is_new_user != is_unknown_user(c.req.user_id, snap) for c in cases)
        info.update({"censored": censored, "kept": len(cases), "labelled": n_lab,
                     "label_coverage": round(n_lab / max(len(cases), 1), 4),
                     "is_new_user_vs_snapshot_disagree": disagree, "views_at_or_after_ts_dropped": dropped_views})
        return EvalSet(self.name, snap.T, self.window_hours, cases, info, complete=censored == 0,
                       new_products=load_new_products(rt))

    # ---- score --------------------------------------------------------------------------------------------------
    def score(self, policies: Sequence[Policy], snap: Snapshot, es: EvalSet) -> tuple[list[Row], dict[str, PolicyRun]]:
        all_reqs = [c.req for c in es.cases]
        has_label = np.array([bool(c.label) for c in es.cases])
        segs_all = segment_masks(all_reqs, snap, es.new_products)
        rows = summarize(self.name, [Metric("label_coverage", np.ones(len(all_reqs), dtype=bool),
                                            {"(data)": (has_label.astype(float), np.ones(len(all_reqs)))})],
                         segs_all, n_boot=self.n_boot, seed=self.seed)

        cases = [c for c in es.cases if c.label]
        if not cases:
            return rows, {}
        reqs = [c.req for c in cases]
        runs = run_policies(policies, reqs, snap)
        segs = segment_masks(reqs, snap, es.new_products)
        ones = np.ones(len(cases))
        everyone = np.ones(len(cases), dtype=bool)
        ndcg, hit = {}, {}
        for name, run in runs.items():
            ndcg[name] = (np.array([ndcg_theta(L, c.label) for L, c in zip(run.lists, cases)]), ones)
            hit[name] = (np.array([float(any(p in c.label for p in L)) for L, c in zip(run.lists, cases)]), ones)
        rows += summarize(self.name, [Metric("ndcg_theta", everyone, ndcg, main=True), Metric("hit_any", everyone, hit)],
                          segs, n_boot=self.n_boot, seed=self.seed)
        return rows, runs
