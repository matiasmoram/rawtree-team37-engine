"""Offline + live-replay evaluation. Never submits anything.

    python -m recsys.evaluate                 # both test sets
    python -m recsys.evaluate --live          # only the live replay

Test sets
  offline : last 7 days of carousel history, held-out users (split B, never seen by the simulator)
  live    : the live requests our team was scored on (team_37.feedback), replayed with features built only
            from data before the window, and stock as it was at each request's timestamp

Metrics per policy
  valid%        lists with 10 distinct, available items (invalid -> fallback in the real game)
  sim_conv      expected purchases per 100 requests under the local simulator
  sim_rev       expected revenue per request (EUR), the tie-breaker
  score         100 * (policy - baseline) / (oracle - baseline), the leaderboard formula, with the
                simulator's own best list as oracle
  cold_score    the same on cold requests (new shopper, or viewed a product added during the event)
  hit_buy@10    real outcome: share of real purchases whose product is in our list
  hit_click@10  real outcome: share of real clicks whose product is in our list
  ms/req        compute time per request (batch), and p95 for single-request calls
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

from . import data as D
from .features import Store
from .policies import Baseline, CategoryFirst, Ranker
from .simulator import Simulator, split_users


def real_hits(S: Store, df: pd.DataFrame, lists: list[list[int]], col: str) -> float:
    pid = S.items.product_id.to_numpy()
    y = df[col].fillna("").to_numpy()
    m = y != ""
    if not m.any():
        return float("nan")
    return float(np.mean([y[r] in set(pid[lists[r]]) for r in np.flatnonzero(m)]))


def validity(lists, unavailable) -> float:
    return float(np.mean([len(l) == 10 and len(set(l)) == 10 and not (set(l) & u) for l, u in zip(lists, unavailable)]))


def single_call_latency(policy, S, R_full, df, unavailable, n=150) -> float:
    idx = np.random.default_rng(0).choice(len(df), size=min(n, len(df)), replace=False)
    times = []
    for r in idx:
        t = time.perf_counter()
        R = S.requests(df.iloc[[r]])
        policy.recommend(S, R, [unavailable[r]])
        times.append(1000 * (time.perf_counter() - t))
    return float(np.percentile(times, 95))


def run(S: Store, df: pd.DataFrame, unavailable: list[set[int]], sim: Simulator, policies: list,
        cold: np.ndarray, logged: dict[str, np.ndarray] | None = None) -> pd.DataFrame:
    R = S.requests(df)
    results, lists_by = {}, {}
    for pol in policies:
        name, Sp = (pol.name, S) if not isinstance(pol, tuple) else (pol[0], pol[2])
        pol = pol if not isinstance(pol, tuple) else pol[1]
        Rp = R if Sp is S else Sp.requests(df)
        t = time.perf_counter()
        lists = pol.recommend(Sp, Rp, unavailable)
        ms = 1000 * (time.perf_counter() - t) / len(df)
        lists_by[name] = lists
        results[name] = dict(valid=validity(lists, unavailable), ms_per_req=ms,
                             p95_single_ms=single_call_latency(pol, Sp, Rp, df, unavailable, n=60))
    if logged:  # what was really shown live (teammate model / fallback)
        pid2i = S.pid2i
        shown = [[pid2i[p] for p in s if p in pid2i] for s in df.shown]
        for name, mask in logged.items():
            lists_by[name] = shown
            results[name] = dict(valid=float("nan"), ms_per_req=float("nan"), p95_single_ms=float("nan"), mask=mask)

    # approximate oracle: the simulator's best 10 among a wide candidate pool
    cf = CategoryFirst(S)
    CS = cf.cat_scores(R)
    pool = []
    for r in range(len(df)):
        c = cf.candidates(R, r, CS[r], top_cats=6, per_cat=60, n_co=80)
        ban = unavailable[r] | ({int(R.last_item[r])} if R.last_item[r] >= 0 else set())
        pool.append(np.array([i for i in c if i not in ban]))
    lists_by["oracle(sim)"] = sim.oracle_lists(S, R, pool)
    results["oracle(sim)"] = dict(valid=validity(lists_by["oracle(sim)"], unavailable), ms_per_req=float("nan"),
                                  p95_single_ms=float("nan"))

    scored = {name: sim.score_lists(S, R, lists) for name, lists in lists_by.items()}
    rows = []
    for name, lists in lists_by.items():
        sc, res = scored[name], results[name]
        mask = res.pop("mask", np.ones(len(df), bool))
        b, o = scored["baseline"], scored["oracle(sim)"]

        def norm(m):
            team, base, orc = sc.p_buy[m].mean(), b.p_buy[m].mean(), o.p_buy[m].mean()
            return 100 * (team - base) / max(orc - base, 1e-12)

        rows.append(dict(policy=name, n=int(mask.sum()), **res,
                         sim_conv=100 * sc.p_buy[mask].mean(), sim_rev=sc.rev[mask].mean(),
                         score=norm(mask), cold_score=norm(mask & cold) if (mask & cold).any() else np.nan,
                         hit_buy10=real_hits(S, df[mask], [lists[i] for i in np.flatnonzero(mask)], "purchased"),
                         hit_click10=real_hits(S, df[mask], [lists[i] for i in np.flatnonzero(mask)], "clicked")))
    return pd.DataFrame(rows).set_index("policy")


def offline(sim: Simulator, n: int = 8000) -> pd.DataFrame:
    S = Store.build("offline")
    _, b = split_users(D.pull("sessions_test"))
    df = b.sample(min(n, len(b)), random_state=0).reset_index(drop=True)
    unav = [S.unavailable_at(None)] * len(df)
    cold = ~df.user_id.isin(S.u2i).to_numpy()
    pols = [Baseline(S), CategoryFirst(S), Ranker.load(S)]
    return run(S, df, unav, sim, pols, cold)


def live(sim: Simulator) -> pd.DataFrame:
    S = Store.build("live")
    df = D.live_feedback()
    ts = pd.to_datetime(df.ts)
    unav = [S.unavailable_at(t) for t in ts]
    newp = set(S.items.product_id[S.items.new])
    cold = (df.is_new_user.astype(bool) | df.recent_views.apply(
        lambda v: any(x.get("product_id") in newp for x in (v or [])))).to_numpy()
    pols = [Baseline(S), CategoryFirst(S), Ranker.load(S)]
    logged = {"LIVE shown: teammate model": (df.served_by == "team").to_numpy(),
              "LIVE shown: fallback": (df.served_by == "fallback").to_numpy()}
    return run(S, df, unav, sim, pols, cold, logged)


def v2_sequence(sim: Simulator) -> pd.DataFrame:
    """V2 plan §8: A0 then one change at a time, on the LAST 40% of the live window.
    The online head learns only from the first 60% (chronological), cold-start imputation only from history
    and descriptions. The simulator always scores with the plain store (no imputed stats)."""
    import dataclasses
    from .config import V2
    from .online_eval import build_slates, replay
    S = Store.build("live")
    Sc = Store.build("live", cold_start=True)
    fb = D.live_feedback()
    cut = int(0.6 * len(fb))
    head, _ = replay(build_slates(S, fb.iloc[:cut].reset_index(drop=True)), dataclasses.replace(V2), cut)
    df = fb.iloc[cut:].reset_index(drop=True)
    unav = [S.unavailable_at(t) for t in pd.to_datetime(df.ts)]
    newp = set(S.items.product_id[S.items.new])
    cold = (df.is_new_user.astype(bool) | df.recent_views.apply(
        lambda v: any(x.get("product_id") in newp for x in (v or [])))).to_numpy()
    pols = [Baseline(S), CategoryFirst(S),
            ("A0 ranker", Ranker.load(S), S),
            ("A0 + cold-start (P3)", Ranker.load(Sc), Sc),
            ("V2.1 = A0 + online head (P2)", Ranker.load(S, head=head), S),
            ("V2.1 + cold-start", Ranker.load(Sc, head=head), Sc)]
    logged = {"LIVE shown: teammate model": (df.served_by == "team").to_numpy(),
              "LIVE shown: fallback": (df.served_by == "fallback").to_numpy()}
    res = run(S, df, unav, sim, pols, cold, logged)
    # how many new products each policy actually shows
    return res


def show(title: str, res: pd.DataFrame) -> None:
    pd.set_option("display.width", 220)
    fmt = res.copy()
    for c in ("valid", "hit_buy10", "hit_click10"):
        fmt[c] = (100 * fmt[c]).round(1)
    print(f"\n=== {title}\n" + fmt.round(3).to_string())


if __name__ == "__main__":
    sim = Simulator.load()
    if "--v2" in sys.argv:
        show("V2 SEQUENCE: last 40% of live window (head trained on first 60%)", v2_sequence(sim))
        sys.exit()
    if "--live" not in sys.argv:
        show("OFFLINE: last 7 days of history, held-out users", offline(sim))
    show("LIVE REPLAY: team_37 feedback window (real outcomes)", live(sim))
