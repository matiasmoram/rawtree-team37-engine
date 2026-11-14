"""Local judge validated against the leaderboard (known answers).

The leaderboard reports, per model_version, the organisers' expected purchases per 100 requests. Our team ran
~12 versions live; team_37.feedback holds every list that was shown and team_37.submissions tells us which
version sent it. A judge is trustworthy if, scoring each version's shown lists, it reproduces the
leaderboard's conversions (rank correlation and level).

Judges compared
  hist_sim     history-trained simulator (recsys/simulator.py)
  live_sim     history sim + small live correction (recsys/sim_live.py)
  live_gbm     LightGBM trained directly on live impressions: P(click at slot) * P(buy | click),
               5-fold cross-fitted by request so a request is never scored by a model that saw it
  realized     observed purchases per 100 (unbiased, very noisy)

    python -m recsys.judge
"""
from __future__ import annotations

import pickle

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from . import data as D
from .features import Store
from .simulator import MODELS, Simulator, impressions

CLICK = dict(objective="binary", learning_rate=0.03, num_leaves=15, min_data_in_leaf=200, lambda_l2=10.0,
             feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, verbose=-1)
BUY = dict(objective="binary", learning_rate=0.03, num_leaves=4, min_data_in_leaf=40, lambda_l2=10.0, verbose=-1)
# buy | click: few, robust features (300 purchases)
BUY_FEATS = ["slot", "in_views", "is_last", "last_cat", "u_cat_share", "s_cat_share", "i_logp", "i_conv",
             "logprice", "price_vs_user", "new_item", "bought", "known_user", "page"]


class LiveJudge:
    def __init__(self, S: Store, click_rounds=300, buy_rounds=150):
        self.S, self.cr, self.br = S, click_rounds, buy_rounds
        self.bi = [S.FEATURES.index(f) for f in BUY_FEATS]

    def fit(self, X, yc, yb):
        self.click = lgb.train(CLICK, lgb.Dataset(X, yc, feature_name=self.S.FEATURES), self.cr)
        m = yc == 1
        self.buy = lgb.train(BUY, lgb.Dataset(X[m][:, self.bi], yb[m], feature_name=BUY_FEATS), self.br)
        return self

    def probs_from_X(self, S, X):
        return self.click.predict(X), self.buy.predict(X[:, self.bi])

    # same interface as Simulator for scoring arbitrary lists
    pair_probs = Simulator.pair_probs
    score_lists = Simulator.score_lists
    oracle_lists = Simulator.oracle_lists


def load_impressions(S: Store):
    fb = D.live_feedback()
    sv = pd.read_pickle(D.DATA / "shown_version.pkl")
    fb = fb.merge(sv, on="request_id", how="left")
    R, ri, ii, slot = impressions(S, fb)
    X = S.pair_features(R, ri, ii, slot)
    pid = S.items.product_id.to_numpy()[ii]
    yc = (pid == fb.clicked.to_numpy()[ri]).astype(int)
    yb = (pid == fb.purchased.to_numpy()[ri]).astype(int)
    return fb, R, ri, ii, X, yc, yb


def crossfit(S, X, yc, yb, ri, k=5, **kw):
    fold = pd.util.hash_array(ri.astype(np.int64)) % k
    pc, pb = np.zeros(len(X)), np.zeros(len(X))
    for f in range(k):
        tr, te = fold != f, fold == f
        J = LiveJudge(S, **kw).fit(X[tr], yc[tr], yb[tr])
        pc[te], pb[te] = J.probs_from_X(S, X[te])
    return pc, pb


def per_version(fb, ri, pp: dict[str, np.ndarray], yb) -> pd.DataFrame:
    n = len(fb)
    out = {}
    for name, p in pp.items():
        out[name] = 100 * np.bincount(ri, weights=p, minlength=n)
    out["realized"] = 100 * np.bincount(ri, weights=yb, minlength=n)
    df = pd.DataFrame(out)
    df["v"] = fb.v.fillna("?").to_numpy()
    return df.groupby("v").agg(["mean"]).droplevel(1, axis=1).join(df.groupby("v").size().rename("n"))


def main():
    S = Store.build("live")
    fb, R, ri, ii, X, yc, yb = load_impressions(S)
    print(f"{len(fb)} requests, {yc.sum()} clicks, {yb.sum()} purchases on shown items")
    hist = Simulator.load()
    live = Simulator.load("simulator_live")
    pp = {}
    c, b = hist.probs_from_X(S, X); pp["hist_sim"] = c * b
    c, b = live.probs_from_X(S, X); pp["live_sim"] = c * b
    c, b = crossfit(S, X, yc, yb, ri); pp["live_gbm"] = c * b
    pv = per_version(fb, ri, pp, yb)
    lb = pd.read_pickle(D.DATA / "lb_versions.pkl").rename(index={"BASELINE": "FALLBACK"})
    t = pv.join(lb[["conv"]].rename(columns={"conv": "LEADERBOARD"}), how="inner")
    t = t[t.n >= 300].sort_values("LEADERBOARD", ascending=False)
    pd.set_option("display.width", 200)
    print("\nper version: expected purchases per 100 requests (judges scored on the lists each version showed)")
    print(t.round(3).to_string())
    print("\nagreement with the leaderboard across versions:")
    for j in list(pp) + ["realized"]:
        print(f"  {j:9s} spearman {spearmanr(t[j], t.LEADERBOARD)[0]:+.2f}  pearson {pearsonr(t[j], t.LEADERBOARD)[0]:+.2f}"
              f"  level ratio {t[j].mean() / t.LEADERBOARD.mean():.2f}")
    full = LiveJudge(S).fit(X, yc, yb)
    pickle.dump(full, open(MODELS / "judge_live.pkl", "wb"))
    print("\nsaved models/judge_live.pkl (fit on all live impressions)")


if __name__ == "__main__":
    main()
