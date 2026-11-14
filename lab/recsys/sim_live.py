"""Live-calibrated simulator: the history simulator + a small correction fitted on our live feedback.

Why: the history simulator shares the ranker's blind spots (same training world), and the "real hit rate"
favours whatever the logging policy showed. Live feedback is the only data produced by the organisers'
hidden shopper model, so we use it to correct the history simulator where they disagree.

    logit P(click | shown at slot)  = logit p_click_hist + f_click(z)
    logit P(buy | click)            = logit p_buy_hist   + f_buy(z)

z = compact shared features (online-head phi + slot). f is chosen on chronological validation among:
  none       history simulator as is
  linear     L2 logistic regression with offset (few parameters, extrapolates smoothly)
  trees      LightGBM boosted from the history logits (init_score), small and heavily regularised
Protocol (same as online_eval): fit on 0-40%, choose on 40-60%, report on the untouched last 40%,
then refit the chosen form on 0-60% for policy evaluation on the last 40%.

    python -m recsys.sim_live
"""
from __future__ import annotations

import pickle

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.metrics import roc_auc_score

from . import data as D
from .features import Requests, Store
from .online_head import PHI, phi
from .simulator import MODELS, Simulator, impressions

ZNAMES = PHI + ["slot_log", "slot0", "slot1"]
EPS = 1e-6


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def zfeat(S: Store, X: np.ndarray) -> np.ndarray:
    slot = X[:, S.FEATURES.index("slot")]
    return np.column_stack([phi(S, X), np.log1p(slot), slot == 0, slot == 1]).astype(float)


# ------------------------------------------------------------------ correction models
class Linear:
    def __init__(self, l2: float):
        self.l2 = l2

    def fit(self, Z, off, y):
        self.mu, self.sd = Z.mean(0), Z.std(0) + 1e-9
        Zs = np.column_stack([np.ones(len(Z)), (Z - self.mu) / self.sd])

        def f(w):
            u = off + Zs @ w
            p = sigmoid(u)
            ll = np.sum(np.logaddexp(0, u) - y * u)
            return ll + self.l2 * w[1:] @ w[1:], Zs.T @ (p - y) + 2 * self.l2 * np.r_[0, w[1:]]

        self.w = minimize(f, np.zeros(Zs.shape[1]), jac=True, method="L-BFGS-B").x
        return self

    def __call__(self, Z):
        return np.column_stack([np.ones(len(Z)), (Z - self.mu) / self.sd]) @ self.w


class Trees:
    def __init__(self, rounds: int, leaves: int = 7, min_leaf: int = 300):
        self.rounds, self.leaves, self.min_leaf = rounds, leaves, min_leaf

    def fit(self, Z, off, y):
        params = dict(objective="binary", learning_rate=0.05, num_leaves=self.leaves,
                      min_data_in_leaf=self.min_leaf, lambda_l2=10.0, feature_fraction=0.8, verbose=-1)
        self.m = lgb.train(params, lgb.Dataset(Z, y, init_score=off, feature_name=ZNAMES), self.rounds)
        return self

    def __call__(self, Z):
        return self.m.predict(Z, raw_score=True)


class Zero:
    def fit(self, *a):
        return self

    def __call__(self, Z):
        return np.zeros(len(Z))


CANDIDATES = {
    "none": lambda: (Zero(), Zero()),
    "linear l2=10": lambda: (Linear(10), Linear(10)),
    "linear l2=100": lambda: (Linear(100), Linear(100)),
    "linear l2=1000": lambda: (Linear(1000), Linear(1000)),
    "trees 50": lambda: (Trees(50), Trees(50, leaves=3, min_leaf=60)),
    "trees 150": lambda: (Trees(150), Trees(150, leaves=3, min_leaf=60)),
}


# ------------------------------------------------------------------ the simulator
class LiveSimulator(Simulator):
    def __init__(self, base: Simulator, fc, fb, form: str):
        super().__init__(base.click, base.buy, base.features)
        self.base, self.fc, self.fb, self.form = base, fc, fb, form

    def probs_from_X(self, S: Store, X: np.ndarray):
        pc, pb = self.base.probs_from_X(S, X)
        Z = zfeat(S, X)
        return sigmoid(logit(pc) + self.fc(Z)), sigmoid(logit(pb) + self.fb(Z))

    def save(self, name: str = "simulator_live") -> None:
        pickle.dump(self, open(MODELS / f"{name}.pkl", "wb"))


# ------------------------------------------------------------------ data
def live_impressions(S: Store, base: Simulator, fb: pd.DataFrame) -> pd.DataFrame:
    R, ri, ii, slot = impressions(S, fb)
    X = S.pair_features(R, ri, ii, slot)
    pc, pb = base.probs_from_X(S, X)
    pid = S.items.product_id.to_numpy()[ii]
    return dict(r=ri, Z=zfeat(S, X), pc=pc, pb=pb, X=X,
                yc=(pid == fb.clicked.to_numpy()[ri]).astype(float),
                yb=(pid == fb.purchased.to_numpy()[ri]).astype(float))


def take(d, m):
    return {k: v[m] for k, v in d.items()}


def fit(d, make):
    fc, fbm = make()
    fc.fit(d["Z"], logit(d["pc"]), d["yc"])
    m = d["yc"] == 1
    fbm.fit(d["Z"][m], logit(d["pb"][m]), d["yb"][m])
    return fc, fbm


def metrics(d, fc, fbm) -> dict:
    pc = sigmoid(logit(d["pc"]) + fc(d["Z"]))
    pb = sigmoid(logit(d["pb"]) + fbm(d["Z"]))
    pp = pc * pb
    yc, yb = d["yc"], d["yb"]
    m = yc == 1
    ll = lambda y, p: -np.mean(y * np.log(np.clip(p, EPS, 1)) + (1 - y) * np.log(np.clip(1 - p, EPS, 1)))
    return dict(ll_click=ll(yc, pc), ll_buy_given_click=ll(yb[m], pb[m]), ll_purchase=ll(yb, pp),
                auc_click=roc_auc_score(yc, pc), auc_purchase=roc_auc_score(yb, pp),
                pred_clicks=pc.sum(), real_clicks=yc.sum(), pred_buys=pp.sum(), real_buys=yb.sum())


def segments(d, fc, fbm, S: Store, served: np.ndarray) -> pd.DataFrame:
    """Calibration (predicted vs real purchases) by segment, history sim vs live-calibrated."""
    pp_h = d["pc"] * d["pb"]
    pp_l = sigmoid(logit(d["pc"]) + fc(d["Z"])) * sigmoid(logit(d["pb"]) + fbm(d["Z"]))
    X, F = d["X"], S.FEATURES
    seg = {
        "logged by teammate model": served[d["r"]] == "team",
        "logged by fallback": served[d["r"]] == "fallback",
        "same category as last view": X[:, F.index("last_cat")] > 0,
        "other category": X[:, F.index("last_cat")] == 0,
        "new product": X[:, F.index("new_item")] > 0,
        "slots 1-3": X[:, F.index("slot")] < 3,
        "slots 4-10": X[:, F.index("slot")] >= 3,
        "known user": X[:, F.index("known_user")] > 0,
        "new user": X[:, F.index("known_user")] == 0,
    }
    rows = [dict(segment=k, impressions=int(m.sum()), real=d["yb"][m].sum(),
                 hist_sim=pp_h[m].sum(), live_sim=pp_l[m].sum()) for k, m in seg.items()]
    return pd.DataFrame(rows).set_index("segment").round(1)


def build(fb: pd.DataFrame | None = None, verbose: bool = True):
    S = Store.build("live")
    base = Simulator.load()
    fb = D.live_feedback() if fb is None else fb
    n = len(fb)
    d = live_impressions(S, base, fb)
    q = d["r"] / n          # chronological position of each impression's request
    tr, va, tr2, te = q < 0.4, (q >= 0.4) & (q < 0.6), q < 0.6, q >= 0.6

    res = {}
    for name, make in CANDIDATES.items():
        fc, fbm = fit(take(d, tr), make)
        res[name] = metrics(take(d, va), fc, fbm)
    val = pd.DataFrame(res).T
    best = val.ll_purchase.idxmin()

    tests = {}
    for name in ("none", best):
        fc, fbm = fit(take(d, tr2), CANDIDATES[name])
        tests[name] = metrics(take(d, te), fc, fbm)
    sim = LiveSimulator(base, fc, fbm, best)          # fitted on 0-60% only
    seg = segments(take(d, te), fc, fbm, S, fb.served_by.to_numpy())

    if verbose:
        pd.set_option("display.width", 220)
        print(f"{n} live requests, {int(d['yc'].sum())} clicks, {int(d['yb'].sum())} purchases on shown items")
        print("\nVALIDATION (fit 0-40%, score 40-60%):\n" + val.round(5).to_string())
        print(f"\nchosen: {best}")
        print("\nTEST (fit 0-60%, untouched last 40%):\n" + pd.DataFrame(tests).T.round(5).to_string())
        print("\nTEST calibration by segment (purchases):\n" + seg.to_string())
    sim.save("simulator_live_0to60")
    full = LiveSimulator(base, *fit(d, CANDIDATES[best]), best)   # all feedback, for later use
    full.save("simulator_live")
    return sim, full, val, tests, seg


if __name__ == "__main__":
    build()
