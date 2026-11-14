"""P2 validation: chronological replay of live feedback through the online head (V2 plan §3.4, §8).

For each feedback event in time order: score with current theta (prequential) -> then one update.
Hyper-parameters (D_MAX, learning rate) are chosen on the first 60% of the stream only; the last 40% is
the untouched test. Reported: NLL of the displayed-slate choice, calibration (predicted vs real purchases),
and the learned theta (what the stream taught the model).

    python -m recsys.online_eval
"""
from __future__ import annotations

import dataclasses
import itertools

import numpy as np
import pandas as pd

from . import data as D
from .config import V2
from .features import Store
from .online_head import PHI, OnlineHead, phi
from .policies import Ranker


def build_slates(S: Store, fb: pd.DataFrame):
    """A's frozen per-item purchase probability at the DISPLAYED slot + phi + observed choice."""
    R = S.requests(fb)
    ri, ii, slot = [], [], []
    for r, shown in enumerate(fb.shown):
        for k, p in enumerate(shown):
            if p in S.pid2i:
                ri.append(r); ii.append(S.pid2i[p]); slot.append(k)
    ri, ii, slot = map(np.array, (ri, ii, slot))
    A = Ranker.load(S)
    p, X = A.base_probs(S, R, ri, ii, slot)
    P = phi(S, X)
    pid = S.items.product_id.to_numpy()
    slates = []
    starts = np.searchsorted(ri, np.arange(len(fb) + 1))
    for r in range(len(fb)):
        a, b = starts[r], starts[r + 1]
        bought = fb.purchased.iloc[r]
        items = pid[ii[a:b]]
        chosen = int(np.flatnonzero(items == bought)[0]) if bought and bought in items else -1
        slates.append((fb.request_id.iloc[r], p[a:b], P[a:b], chosen))
    return slates


def replay(slates, cfg, train_until: int):
    head = OnlineHead(cfg)
    out = []
    for n, (rid, p, P, ch) in enumerate(slates):
        on = head.n_updates >= cfg.MIN_FINAL_FEEDBACK
        d = np.clip(P @ head.theta, -cfg.MAX_ONLINE_CORRECTION, cfg.MAX_ONLINE_CORRECTION) if on else 0 * p
        pk, p0 = OnlineHead.slate_probs(p, d)
        pa, pa0 = OnlineHead.slate_probs(p, 0 * p)
        out.append((n, ch >= 0, -np.log(pk[ch] if ch >= 0 else p0), -np.log(pa[ch] if ch >= 0 else pa0),
                    1 - p0, 1 - pa0))
        head.update(rid, p, P, ch)
    return head, pd.DataFrame(out, columns=["n", "buy", "nll_v2", "nll_a", "pred_v2", "pred_a"])


def main():
    S = Store.build("live")
    fb = D.live_feedback()
    slates = build_slates(S, fb)
    n = len(slates)
    cut = int(0.6 * n)
    print(f"{n} feedback events ({int((fb.purchased != '').sum())} purchases), tuning on first {cut}, test on last {n - cut}")

    # chronological tuning on the first 60% only: train on 0-40%, validate on 40-60%
    best = None
    for dmax, lr in itertools.product([0.5, 1.0, 1.5, 2.5], [0.01, 0.03, 0.1]):
        cfg = dataclasses.replace(V2, MAX_ONLINE_CORRECTION=dmax, ONLINE_LEARNING_RATE=lr)
        _, res = replay(slates[:cut], cfg, cut)
        v = res[res.n >= int(0.4 * n)]
        gain = v.nll_a.mean() - v.nll_v2.mean()
        if best is None or gain > best[0]:
            best = (gain, dmax, lr)
    _, dmax, lr = best
    cfg = dataclasses.replace(V2, MAX_ONLINE_CORRECTION=dmax, ONLINE_LEARNING_RATE=lr)
    print(f"chosen on validation: MAX_ONLINE_CORRECTION={dmax}, ONLINE_LEARNING_RATE={lr}")

    head, res = replay(slates, cfg, n)
    test = res[res.n >= cut]
    k = len(test)
    se = np.std(test.nll_a - test.nll_v2, ddof=1) / np.sqrt(k)
    print(f"\nTEST (last {k} events, {int(test.buy.sum())} purchases), prequential: predict then update")
    print(f"  mean NLL   A (frozen): {test.nll_a.mean():.5f}   V2.1 (online head): {test.nll_v2.mean():.5f}   "
          f"gain {test.nll_a.mean() - test.nll_v2.mean():+.5f} ± {1.96 * se:.5f} (95% CI)")
    print(f"  purchases  real: {int(test.buy.sum())}   predicted by A: {test.pred_a.sum():.1f}   by V2.1: {test.pred_v2.sum():.1f}")
    print(f"  updates applied: {head.n_updates} (one per request_id; duplicates rejected: "
          f"{int(not head.update(slates[0][0], *slates[0][1:]))})")
    print("\nlearned theta (positive = live shoppers buy MORE than A predicts):")
    print(pd.Series(head.theta, index=PHI).round(3).sort_values().to_string())
    head.save()
    print("\nsaved models/online_head.json")


if __name__ == "__main__":
    main()
