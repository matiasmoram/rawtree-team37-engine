"""Local shopper simulator: a learned stand-in for the organisers' hidden model.

P(purchase of item at slot k) = P(click k | shopper, item, slot) * P(buy | click, shopper, item)

Both parts are LightGBM models trained on carousel impressions from the *test period* (last 7 days of
history, split A by user). Policies are trained only on data before that period, so the simulator is not
the same model the policies optimise (avoids grading our own homework).

Expected purchases of a list = sum_k P(click k) * P(buy | click k)   (a shopper clicks at most once).
Validated on held-out users (split B) and on the live feedback (real outcomes of 9k live requests).
"""
from __future__ import annotations

import pickle
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from . import data as D
from .features import Requests, Store

MODELS = Path(__file__).resolve().parent.parent / "models"
MODELS.mkdir(exist_ok=True)

PARAMS = dict(objective="binary", learning_rate=0.05, num_leaves=63, min_data_in_leaf=100,
              feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1)


def split_users(df: pd.DataFrame, frac_a: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    h = pd.util.hash_pandas_object(df.user_id, index=False).to_numpy() % 100
    return df[h < frac_a * 100].reset_index(drop=True), df[h >= frac_a * 100].reset_index(drop=True)


def impressions(S: Store, df: pd.DataFrame) -> tuple[Requests, np.ndarray, np.ndarray, np.ndarray]:
    """Expand logged sessions into (request, item, slot) rows for the shown items."""
    R = S.requests(df)
    ri = np.repeat(np.arange(len(df)), 10)
    ii = np.array([S.pid2i.get(p, -1) for s in df.shown for p in s])
    slot = np.tile(np.arange(10), len(df))
    ok = ii >= 0
    return R, ri[ok], ii[ok], slot[ok]


class Simulator:
    def __init__(self, click: lgb.Booster, buy: lgb.Booster, features: list[str]):
        self.click, self.buy, self.features = click, buy, features

    # ---------------------------------------------------------------- train
    @classmethod
    def train(cls, S: Store, sessions: pd.DataFrame, rounds: int = 400) -> "Simulator":
        R, ri, ii, slot = impressions(S, sessions)
        X = S.model_X(S.pair_features(R, ri, ii, slot))
        pid = S.items.product_id.to_numpy()[ii]
        clicked = sessions.clicked.fillna("").to_numpy()[ri]
        purchased = sessions.purchased.fillna("").to_numpy()[ri]
        y_click = (pid == clicked).astype(int)
        click = lgb.train(PARAMS, lgb.Dataset(X, y_click, feature_name=S.FEATURES), rounds)
        m = y_click == 1
        y_buy = (pid[m] == purchased[m]).astype(int)
        buy = lgb.train({**PARAMS, "num_leaves": 15, "min_data_in_leaf": 50},
                        lgb.Dataset(X[m], y_buy, feature_name=S.FEATURES), rounds // 2)
        return cls(click, buy, S.FEATURES)

    def save(self, name: str = "simulator") -> None:
        pickle.dump(self, open(MODELS / f"{name}.pkl", "wb"))

    @staticmethod
    def load(name: str = "simulator") -> "Simulator":
        return pickle.load(open(MODELS / f"{name}.pkl", "rb"))

    # ---------------------------------------------------------------- score
    # Live calibration (team_37 feedback): previously bought items got 0 of 4,885 impressions bought and a
    # 14x lower click rate. Applied on top of the history-trained models.
    BOUGHT_CLICK_FACTOR = 0.07
    BOUGHT_BUY_FACTOR = 0.05

    def pair_probs(self, S: Store, R: Requests, ri, ii, slot) -> tuple[np.ndarray, np.ndarray]:
        return self.probs_from_X(S, S.pair_features(R, ri, ii, slot))

    def probs_from_X(self, S: Store, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        bought = X[:, S.FEATURES.index("bought")] > 0
        Xm = S.model_X(X)
        pc, pb = self.click.predict(Xm), self.buy.predict(Xm)
        return np.where(bought, pc * self.BOUGHT_CLICK_FACTOR, pc), np.where(bought, pb * self.BOUGHT_BUY_FACTOR, pb)

    def score_lists(self, S: Store, R: Requests, lists: list[list[int]]) -> pd.DataFrame:
        """Expected purchases and revenue per request for the given lists (item indices, best first)."""
        ri = np.repeat(np.arange(len(lists)), [len(l) for l in lists])
        ii = np.array([i for l in lists for i in l])
        slot = np.concatenate([np.arange(len(l)) for l in lists])
        pc, pb = self.pair_probs(S, R, ri, ii, slot)
        pp = pc * pb
        price = S.items.price.to_numpy()[ii]
        out = pd.DataFrame({"r": ri, "p_click": pc, "p_buy": pp, "rev": pp * price})
        g = out.groupby("r")[["p_click", "p_buy", "rev"]].sum()
        return g.reindex(range(len(lists)), fill_value=0.0)

    def oracle_lists(self, S: Store, R: Requests, candidates: list[np.ndarray]) -> list[list[int]]:
        """The simulator's own best list per request (approximate oracle: top-10 by P(buy) at slot 0)."""
        ri = np.repeat(np.arange(len(candidates)), [len(c) for c in candidates])
        ii = np.concatenate(candidates)
        pc, pb = self.pair_probs(S, R, ri, ii, 0)
        s = pd.DataFrame({"r": ri, "i": ii, "p": pc * pb}).sort_values(["r", "p"], ascending=[True, False])
        top = s.groupby("r").head(10).groupby("r").i.apply(list)
        return [top.get(r, []) for r in range(len(candidates))]


# -------------------------------------------------------------------- validation
def validate(sim: Simulator, S: Store, sessions: pd.DataFrame) -> dict:
    """AUC and calibration on held-out logged sessions."""
    R, ri, ii, slot = impressions(S, sessions)
    pc, pb = sim.pair_probs(S, R, ri, ii, slot)
    pid = S.items.product_id.to_numpy()[ii]
    yc = pid == sessions.clicked.fillna("").to_numpy()[ri]
    yp = pid == sessions.purchased.fillna("").to_numpy()[ri]
    per_req = pd.DataFrame({"r": ri, "pred": pc * pb, "y": yp}).groupby("r").sum()
    return {
        "impressions": len(sessions),
        "auc_click": roc_auc_score(yc, pc),
        "auc_purchase": roc_auc_score(yp, pc * pb),
        "pred_conv_per100": 100 * per_req.pred.mean(),
        "real_conv_per100": 100 * per_req.y.mean(),
    }


def train_and_save() -> Simulator:
    S = Store.build("offline")
    a, b = split_users(D.pull("sessions_test"))
    sim = Simulator.train(S, a)
    sim.save()
    print("held-out users (split B):", {k: round(v, 4) for k, v in validate(sim, S, b).items()})
    return sim


if __name__ == "__main__":
    train_and_save()
