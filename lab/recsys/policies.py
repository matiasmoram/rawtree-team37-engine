"""Recommendation policies. Each maps a batch of requests to 10 item indices per request (best first).

    baseline        all-time best sellers in stock (what the organisers score as 0, and the fallback)
    category_first  heuristic: pick categories from session / user history / context, then best items inside
    ranker          LightGBM P(click)*P(buy|click) over candidates from category_first + co-views,
                    trained only on carousel logs BEFORE the offline test period

Rules applied to every list: 10 distinct items, none unavailable (out of stock / inactive),
none the shopper already bought, not the item they are looking at right now.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import data as D
from .features import Requests, Store
from .simulator import PARAMS, impressions

MODELS = Path(__file__).resolve().parent.parent / "models"


def _fill(lst: list[int], fallback: np.ndarray, banned: set[int], k: int = 10) -> list[int]:
    seen = set(lst)
    out = list(lst)
    for i in fallback:
        if len(out) >= k:
            break
        i = int(i)
        if i not in seen and i not in banned:
            out.append(i); seen.add(i)
    return out[:k]


def banned_for(S: Store, R: Requests, r: int, unavailable: set[int]) -> set[int]:
    b = set(unavailable)
    u = int(R.user[r])
    if u >= 0:
        b |= S.bought.get(u, set())
    if R.last_item[r] >= 0:
        b.add(int(R.last_item[r]))
    return b


# ---------------------------------------------------------------------------- baseline
class Baseline:
    name = "baseline"

    def __init__(self, S: Store):
        pid = S.items.product_id.to_numpy()
        order = sorted(range(len(pid)), key=lambda i: (-S.I_p[i], [-ord(c) for c in pid[i]]))
        self.best = np.array([i for i in order if S.I_p[i] > 0])

    def recommend(self, S: Store, R: Requests, unavailable: list[set[int]]) -> list[list[int]]:
        return [_fill([], self.best, unavailable[r]) for r in range(len(R.user))]


# ---------------------------------------------------------------------------- category first
class CategoryFirst:
    name = "category_first"

    def __init__(self, S: Store, w_sess=3.0, w_user=1.0, w_ctx=0.5, decay=0.55, per_cat=80):
        self.S, self.w_sess, self.w_user, self.w_ctx, self.decay = S, w_sess, w_user, w_ctx, decay
        it = S.items
        # item quality inside its category: purchases, smoothed conversion, trend
        self.quality = np.log1p(S.I_p) + 3 * (S.I_p + 1) / (S.I_v + 50) + 0.5 * np.log(S.I_trend)
        self.by_cat = {c: np.array(g.index[np.argsort(-self.quality[g.index.to_numpy()])][:per_cat])
                       for c, g in it.groupby("cat")}
        self.global_best = np.argsort(-self.quality)

    def cat_scores(self, R: Requests) -> np.ndarray:
        S = self.S
        N, C = len(R.user), len(S.cats)
        sess = R.sess_cat / np.maximum(R.sess_cat.sum(1, keepdims=True), 1e-9)
        known = R.user >= 0
        uu = np.where(known, R.user, 0)
        act = S.U_v[uu] + 3 * S.U_c[uu] + 5 * S.U_p[uu]
        user = np.where(known[:, None], act / np.maximum(act.sum(1, keepdims=True), 1e-9), 0)
        ctx = np.array([S.ctx_cat.get((d, g), S.cat_pop) for d, g in zip(R.device, R.region)])
        return self.w_sess * sess + self.w_user * user + self.w_ctx * ctx

    def slot_plan(self, scores: np.ndarray, k: int = 10) -> list[int]:
        """Assign slots to categories greedily; each pick shrinks that category's score (diversity)."""
        s = scores.astype(float).copy()
        plan = []
        for _ in range(k):
            c = int(np.argmax(s)); plan.append(c); s[c] *= self.decay
        return plan

    def item_scores(self, R: Requests, r: int, cand: np.ndarray) -> np.ndarray:
        S = self.S
        co = np.asarray(R.RVCV[r, cand].todense()).ravel() if R.RVCV[r].nnz else 0
        sub = S.items["sub"].to_numpy()[cand]
        last = R.last_item[r]
        same_sub = (sub == S.items["sub"].to_numpy()[last]) if last >= 0 else 0
        usub = np.asarray(S.U_sub[R.user[r], sub].todense()).ravel() if R.user[r] >= 0 else 0
        return self.quality[cand] + 8 * co + 0.8 * same_sub + 0.3 * np.log1p(usub)

    def recommend(self, S: Store, R: Requests, unavailable: list[set[int]]) -> list[list[int]]:
        CS = self.cat_scores(R)
        out = []
        for r in range(len(R.user)):
            banned = banned_for(S, R, r, unavailable[r])
            plan = self.slot_plan(CS[r])
            picks: list[int] = []
            taken = set()
            ranked = {}
            for c in plan:
                if c not in ranked:
                    cand = self.by_cat[c]
                    sc = self.item_scores(R, r, cand)
                    ranked[c] = iter(cand[np.argsort(-sc)])
                for i in ranked[c]:
                    i = int(i)
                    if i not in banned and i not in taken:
                        picks.append(i); taken.add(i); break
            out.append(_fill(picks, self.global_best, banned | taken))
        return out

    def candidates(self, R: Requests, r: int, CS_r: np.ndarray, top_cats=4, per_cat=40, n_co=40) -> np.ndarray:
        cats = np.argsort(-CS_r)[:top_cats]
        parts = [self.by_cat[c][:per_cat] for c in cats]
        row = R.RVCV[r]
        if row.nnz:
            parts.append(row.indices[np.argsort(-row.data)][:n_co])
        return np.unique(np.concatenate(parts))


# ---------------------------------------------------------------------------- learned ranker
class Ranker:
    name = "ranker"

    def __init__(self, S: Store, click: lgb.Booster, buy: lgb.Booster, max_per_cat: int = 6, head=None):
        self.S, self.click, self.buy, self.max_per_cat = S, click, buy, max_per_cat
        self.cf = CategoryFirst(S)
        self.head = head          # V2 P2: OnlineHead or None (None / flag off / theta=0 -> exactly A)
        if head is not None and head.cfg.USE_ONLINE_CORRECTION:
            self.name = head.cfg.MODEL_VERSION

    def base_probs(self, S: Store, R: Requests, ri, ii, slot):
        """A's frozen P(click at slot) * P(buy | click), plus the raw feature matrix."""
        X = S.pair_features(R, ri, ii, slot)
        Xm = S.model_X(X)
        return self.click.predict(Xm) * self.buy.predict(Xm), X

    @classmethod
    def train(cls, S: Store, sessions: pd.DataFrame, rounds: int = 400) -> tuple[lgb.Booster, lgb.Booster]:
        R, ri, ii, slot = impressions(S, sessions)
        X = S.model_X(S.pair_features(R, ri, ii, slot))
        pid = S.items.product_id.to_numpy()[ii]
        yc = (pid == sessions.clicked.fillna("").to_numpy()[ri]).astype(int)
        click = lgb.train(PARAMS, lgb.Dataset(X, yc, feature_name=S.FEATURES), rounds)
        m = yc == 1
        yb = (pid[m] == sessions.purchased.fillna("").to_numpy()[ri][m]).astype(int)
        buy = lgb.train({**PARAMS, "num_leaves": 15, "min_data_in_leaf": 50},
                        lgb.Dataset(X[m], yb, feature_name=S.FEATURES), rounds // 2)
        pickle.dump((click, buy), open(MODELS / "ranker.pkl", "wb"))
        return click, buy

    @classmethod
    def load(cls, S: Store, path: Path = MODELS / "A" / "ranker.pkl", **kw) -> "Ranker":
        click, buy = pickle.load(open(path, "rb"))
        return cls(S, click, buy, **kw)

    def recommend(self, S: Store, R: Requests, unavailable: list[set[int]]) -> list[list[int]]:
        self.cf.S = S
        CS = self.cf.cat_scores(R)
        cands = [self.cf.candidates(R, r, CS[r]) for r in range(len(R.user))]
        ri = np.repeat(np.arange(len(cands)), [len(c) for c in cands])
        ii = np.concatenate(cands)
        p, X = self.base_probs(S, R, ri, ii, 0)
        if self.head is not None and self.head.cfg.USE_ONLINE_CORRECTION:
            from .online_head import phi
            p = np.log(np.maximum(p, 1e-12)) + self.head.delta(phi(S, X))   # rank by bounded corrected logit
        df = pd.DataFrame({"r": ri, "i": ii, "p": p, "c": S.items.cat.to_numpy()[ii]})
        df = df.sort_values(["r", "p"], ascending=[True, False])
        out = []
        for r, g in df.groupby("r", sort=True):
            banned = banned_for(S, R, r, unavailable[r])
            picks, per = [], {}
            for i, c in zip(g.i.to_numpy(), g.c.to_numpy()):
                if i in banned or per.get(c, 0) >= self.max_per_cat:
                    continue
                picks.append(int(i)); per[c] = per.get(c, 0) + 1
                if len(picks) == 10:
                    break
            out.append(_fill(picks, self.cf.global_best, banned))
        return out


def train_ranker() -> None:
    S = Store.build("offline")
    Ranker.train(S, D.pull("sessions_train"))
    print("ranker saved")


if __name__ == "__main__":
    train_ranker()


# ---------------------------------------------------------------------------- blend (m2)
class Blend(Ranker):
    """Rank fusion of the learned ranker (with any online head) and category_first.

    score(i) = w / (k + rank_cf(i)) + (1 - w) / (k + rank_ranker(i)); items outside the category_first list
    get rank_cf = 10 + their category_first-pool position, so category_first can only promote its own
    picks while the ranker still orders the rest. Same bans, same per-category cap.
    """
    name = "blend"

    def __init__(self, *a, w: float = 0.5, k: float = 5.0, **kw):
        super().__init__(*a, **kw)
        self.w, self.k = w, k
        self.name = "blend"

    def recommend(self, S: Store, R: Requests, unavailable: list[set[int]]) -> list[list[int]]:
        self.cf.S = S
        cf_lists = self.cf.recommend(S, R, unavailable)
        CS = self.cf.cat_scores(R)
        cands = [np.unique(np.r_[self.cf.candidates(R, r, CS[r]), cf_lists[r]]).astype(int)
                 for r in range(len(R.user))]
        ri = np.repeat(np.arange(len(cands)), [len(c) for c in cands])
        ii = np.concatenate(cands)
        p, X = self.base_probs(S, R, ri, ii, 0)
        p = np.log(np.maximum(p, 1e-12))
        if self.head is not None and self.head.cfg.USE_ONLINE_CORRECTION:
            from .online_head import phi
            p = p + self.head.delta(phi(S, X))
        cat = S.items.cat.to_numpy()
        starts = np.r_[0, np.cumsum([len(c) for c in cands])]
        out = []
        for r in range(len(cands)):
            items, sc = ii[starts[r]:starts[r + 1]], p[starts[r]:starts[r + 1]]
            rk = np.empty(len(items)); rk[np.argsort(-sc)] = np.arange(len(items))
            pos = {i: n for n, i in enumerate(cf_lists[r])}
            rc = np.array([pos.get(int(i), 10 + rk[n]) for n, i in enumerate(items)])
            fused = self.w / (self.k + rc) + (1 - self.w) / (self.k + rk)
            banned = banned_for(S, R, r, unavailable[r])
            picks, per = [], {}
            for j in np.argsort(-fused):
                i, c = int(items[j]), cat[items[j]]
                if i in banned or per.get(c, 0) >= self.max_per_cat:
                    continue
                picks.append(i); per[c] = per.get(c, 0) + 1
                if len(picks) == 10:
                    break
            out.append(_fill(picks, self.cf.global_best, banned))
        return out


# ---------------------------------------------------------------------------- viewed-first (m3)
class ViewedFirst:
    """Put the shopper's own recently viewed products in the top slots, then the base policy's list.

    Live feedback (32k requests): a product the shopper viewed in this session, shown in slot 1, is bought
    11-12 times per 1,000 impressions vs 3.3 for other products in slot 1 (2.4x within the same category);
    slots 2-3: 3.4-6.2 vs 1.1; no gain below slot 3. So: newest viewed product -> slot 1, next -> slot 2.
    Bought / unavailable products are still excluded.
    """

    def __init__(self, base, n_top: int = 2):
        self.base, self.n_top = base, n_top
        self.name = f"viewed_first({base.name})"

    def recommend(self, S: Store, R: Requests, unavailable: list[set[int]]) -> list[list[int]]:
        lists = self.base.recommend(S, R, unavailable)
        out = []
        for r, lst in enumerate(lists):
            u = int(R.user[r])
            ban = set(unavailable[r]) | (S.bought.get(u, set()) if u >= 0 else set())
            top = []
            for i in reversed(R.views[r]):            # newest first
                if i not in ban and i not in top:
                    top.append(int(i))
                if len(top) == self.n_top:
                    break
            rest = [i for i in lst if i not in top]
            out.append((top + rest)[:10])
        return out
