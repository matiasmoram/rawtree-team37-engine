"""Replay of logged carousel impressions (``shop.history_sessions``)."""
from __future__ import annotations

import logging
from typing import Sequence

import numpy as np

from ..policies.base import Policy
from ..rt import RawTree
from ..snapshot import Snapshot
from ..types import Request, parse_ts, sql_ts
from .common import (Case, EvalSet, Evaluator, PolicyRun, is_unknown_user, load_new_products, paged, hash_sample,
                     run_policies, segment_masks, theta_at, views_before, SETTINGS)
from .stats import Metric, Row, summarize

log = logging.getLogger("eval.logged")


class LoggedImpressionEval(Evaluator):
    """Counterfactual replay of the old system's logged impressions in [T, T + window).

    Each impression is rebuilt as the ``Request`` the old system received (context, recent views strictly before
    its ts; ``is_new_user`` = user unknown to the snapshot) and handed to the policy with the snapshot at T.

    Estimators
    ----------
    hit_purchase (main)
        Mean over impressions with a purchase of THETA[rank of the purchased item in the policy list] (0 if absent).
        Reads as "how high would we have put what the user actually bought".
    hit_click
        Same with the clicked item, over impressions with a click (3x more data, noisier intent signal).
    snips_slot1
        Self-normalised IPS estimate of the slot-1 purchase rate. For each sampled impression, if the policy's first
        item equals the logged ``shown[0]``, weight w = 1 / propensity[0] (old policy's probability of that slot-1
        item); reward r = (purchased == shown[0]). Estimate = sum(d * w * r) / sum(d * w), where d is the sampling
        design weight of the impression's stratum. ``logging-policy`` rows give the on-policy slot-1 rate for scale.
        ``snips_matches`` / ``snips_ess`` report how many impressions carry the estimate (effective sample size
        = (sum dw)^2 / sum (dw)^2).
    ips_slot1
        Plain (unnormalised) IPS of the same quantity: sum(d * w * r) / sum(d).
    ips_support
        Mean importance weight sum(d * w * match) / sum(d). With correct propensities it equals the share of contexts
        where the logging policy could have shown the policy's slot-1 item at slot 1 (1.0 = full support).

    Sampling
    --------
    Two strata, pulled deterministically by hash of request_id: impressions with a click (includes every purchase;
    all of them unless ``max_clicked`` caps it) and impressions without a click (``nonclick_sample`` of them). The
    hit metrics only use the click stratum, which is a uniform sample, so they are unbiased means. SNIPS reweights
    each stratum by N_stratum / n_sampled.

    Biases and limitations
    ----------------------
    * Selection bias of the hit metrics: the purchased/clicked item was necessarily among the 10 items the *old*
      policy showed, and its position influenced the click. A policy that imitates the old one (e.g.
      ``ref-lastview-category``) is favoured by construction; items the old policy never showed can never score.
      Use the hit metrics to rank policies close to the logging policy, not as an absolute conversion forecast.
    * Support deficiency (the main caveat of the slot-1 estimators): the old policy only puts an item at slot 1 in
      contexts where it is relevant (its category). A policy that always opens with the same global best seller is
      matched only in those favourable contexts; SNIPS renormalises over them and is biased UPWARD (it estimates the
      purchase rate conditional on supported contexts), while IPS counts unsupported contexts as 0 and is biased
      DOWNWARD. Compare policies with SNIPS only when ``ips_support`` is close to 1 for all of them; otherwise prefer
      IPS (a lower bound) and the hit metrics.
    * SNIPS only covers impressions where the policy agrees with the logged slot 1. Policies far from the logging
      policy get few matches and a high-variance estimate (check ``snips_matches`` / ``snips_ess``). It also assumes
      the slot-1 reward depends only on the slot-1 item, ignoring the other 9 items of the logged slate.
      Propensities near 0 create huge weights; ``max_weight`` clips them (bias for variance), off by default.
      Self-normalisation adds a small O(1/n) bias.
    * The snapshot is frozen at T: impressions late in a long window are scored with stale knowledge, which
      penalises policies that rely on recent popularity more than live serving would.
    """

    name = "logged"

    def __init__(self, window_hours: float = 168.0, max_clicked: int = 20000, nonclick_sample: int = 30000,
                 max_weight: float | None = None, parts: int = 4, n_boot: int = 500, seed: int = 0) -> None:
        super().__init__(window_hours, n_boot, seed)
        self.max_clicked = max_clicked
        self.nonclick_sample = nonclick_sample
        self.max_weight = max_weight
        self.parts = parts

    def params(self) -> dict:
        return {"max_clicked": self.max_clicked, "nonclick_sample": self.nonclick_sample}

    # ---- pull ---------------------------------------------------------------------------------------------------
    def pull(self, rt: RawTree, snap: Snapshot) -> EvalSet:
        t0, t1 = self.window(snap.T)
        where = f"ts::DateTime64(3) >= '{sql_ts(t0)}' AND ts::DateTime64(3) < '{sql_ts(t1)}'"
        c = rt.query(f"""
            SELECT count() AS n, countIf(isNotNull(clicked::Nullable(String))) AS n_click,
                   countIf(isNotNull(purchased::Nullable(String))) AS n_buy
            FROM shop.history_sessions WHERE {where} {SETTINGS}""", timeout=300)[0]
        n_all, n_click, n_buy = int(c["n"]), int(c["n_click"]), int(c["n_buy"])
        info = {"impressions": n_all, "with_click": n_click, "with_purchase": n_buy}
        if n_all == 0:
            return EvalSet(self.name, snap.T, self.window_hours, [], info)

        strata = {
            "click": ("isNotNull(clicked::Nullable(String))", n_click, min(1.0, self.max_clicked / max(n_click, 1))),
            "noclick": ("isNull(clicked::Nullable(String))", n_all - n_click,
                        min(1.0, self.nonclick_sample / max(n_all - n_click, 1))),
        }
        new_products = load_new_products(rt)
        cases: list[Case] = []
        dropped_views = 0  # recent views at or after the request ts (should be 0)
        # Note: SELECT aliases must not reuse column names used in WHERE (ClickHouse resolves aliases first there).
        for stratum, (cond, n_total, rate) in strata.items():
            if n_total == 0:
                continue
            rows = paged(rt, f"""
                SELECT request_id::String AS request_id, ts::DateTime64(3) AS ts, user_id::String AS user_id,
                       context.page::String AS page, context.device::String AS device, context.region::String AS region,
                       recent_views, shown::Array(String) AS shown, propensity::Array(Float64) AS propensity,
                       ifNull(clicked::Nullable(String), '') AS clk, ifNull(purchased::Nullable(String), '') AS pur
                FROM shop.history_sessions
                WHERE {where} AND {cond} AND {hash_sample('request_id::String', rate)} AND {{part}}
                {SETTINGS}""", self.parts, "request_id::String")
            design_w = n_total / max(len(rows), 1)  # realised inverse sampling rate of the stratum
            info[f"sampled_{stratum}"] = len(rows)
            for r in rows:
                req = Request.from_row(r)
                n_views = len(req.recent_views)
                req.recent_views = views_before(req.recent_views, req.ts)
                dropped_views += n_views - len(req.recent_views)
                req.is_new_user = is_unknown_user(req.user_id, snap)
                cases.append(Case(req, {
                    "shown": list(r["shown"]), "p0": float(r["propensity"][0]),
                    "clicked": r["clk"], "purchased": r["pur"],
                    "stratum": stratum, "d": design_w,
                }))
        info["views_at_or_after_ts_dropped"] = dropped_views
        return EvalSet(self.name, snap.T, self.window_hours, cases, info, new_products=new_products)

    # ---- score --------------------------------------------------------------------------------------------------
    def score(self, policies: Sequence[Policy], snap: Snapshot, es: EvalSet) -> tuple[list[Row], dict[str, PolicyRun]]:
        reqs = [c.req for c in es.cases]
        labels = [c.label for c in es.cases]
        runs = run_policies(policies, reqs, snap)
        segs = segment_masks(reqs, snap, es.new_products)

        buy = np.array([lb["purchased"] != "" for lb in labels])
        clk = np.array([lb["clicked"] != "" for lb in labels])
        d = np.array([lb["d"] for lb in labels])
        p0 = np.array([lb["p0"] for lb in labels])
        w = np.where(p0 > 0, 1.0 / np.maximum(p0, 1e-12), 0.0)
        if self.max_weight is not None:
            w = np.minimum(w, self.max_weight)
        r = np.array([lb["purchased"] != "" and lb["purchased"] == lb["shown"][0] for lb in labels], dtype=float)
        ones = np.ones(len(labels))
        everyone = np.ones(len(labels), dtype=bool)

        hit_buy, hit_clk, snips, ips, support = {}, {}, {}, {}, {}
        matches: dict[str, np.ndarray] = {}
        for name, run in runs.items():
            hit_buy[name] = (np.array([theta_at(L, lb["purchased"]) if lb["purchased"] else 0.0
                                       for L, lb in zip(run.lists, labels)]), ones)
            hit_clk[name] = (np.array([theta_at(L, lb["clicked"]) if lb["clicked"] else 0.0
                                       for L, lb in zip(run.lists, labels)]), ones)
            m = np.array([bool(L) and L[0] == lb["shown"][0] for L, lb in zip(run.lists, labels)])
            matches[name] = m
            snips[name] = (d * w * r * m, d * w * m)
            ips[name] = (d * w * r * m, d)
            support[name] = (d * w * m, d)
        snips["logging-policy"] = (d * r, d)  # on-policy slot-1 purchase rate (design weighted), for scale
        ips["logging-policy"] = (d * r, d)

        metrics = [
            Metric("hit_purchase", buy, hit_buy, main=True),
            Metric("hit_click", clk, hit_clk),
            Metric("snips_slot1", everyone, snips),
            Metric("ips_slot1", everyone, ips),
            Metric("ips_support", everyone, support, lift=False),
        ]
        rows = summarize(self.name, metrics, segs, n_boot=self.n_boot, seed=self.seed)
        # Support of the SNIPS estimate per policy and segment.
        for seg_name, seg in segs.items():
            for name, m in matches.items():
                sel = seg & m
                dw = (d * w)[sel]
                ess = float(dw.sum() ** 2 / (dw ** 2).sum()) if sel.any() else 0.0
                rows.append(Row(self.name, name, seg_name, "snips_matches", float(sel.sum()), None, None, int(seg.sum())))
                rows.append(Row(self.name, name, seg_name, "snips_ess", ess, None, None, int(seg.sum())))
        return rows, runs
