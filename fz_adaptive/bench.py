"""Internal offline benchmark on the LAST live requests.

Test data = our own most recent logged impressions: the exact features used at serving time + what the shopper
did (click / purchase). A candidate model is trained WITHOUT those rows and scored on them:
  click AUC, buy AUC     - does it separate clicked / bought products from the rest?
  list MRR (click)       - inside each shown list, how high does the model rank the product that was clicked?
  calibration            - predicted / realised purchases
    python bench.py                 # compare training recipes on the newest 30% of live impressions
"""
import sys, json, numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score
from features import FEATS, FI, D
import learn

def load_live():
    X, c, b, t = learn.live(); return X, c, b, t

def score(m, X, c, b, cols=None):
    Xc = X if cols is None else X[:, cols]
    pc = m["click"].predict(Xc); pb = pc * m["buy_given_click"].predict(Xc)
    # within-list reciprocal rank of the clicked item, with the slot effect removed (slot set to 0 for ranking)
    X0 = X.copy(); X0[:, FI["slot"]] = 0; X0 = X0 if cols is None else X0[:, cols]
    s = (m["click"].predict(X0) * m["buy_given_click"].predict(X0)).reshape(-1, 10); C = c.reshape(-1, 10)
    rows = C.any(1); rank = (s[rows] > s[rows][C[rows]][:, None]).sum(1) + 1
    return dict(click_auc=roc_auc_score(c, pc), buy_auc=roc_auc_score(b, pb), mrr_click=float((1 / rank).mean()), calib_buy=float(pb.sum() / max(b.sum(), 1)), n_lists=len(C), clicks=int(c.sum()), buys=int(b.sum()))

def recipes(Xh, ch, bh, wh, Xl, cl, bl, tl, cut):
    out = {}
    def tr(live_w, **kw):
        if live_w == 0: X, c, b, w = Xh, ch, bh, wh
        else:
            wl = np.full(cut, live_w); X, c, b, w = np.vstack([Xh, Xl[:cut]]), np.r_[ch, cl[:cut]], np.r_[bh, bl[:cut]], np.r_[wh, wl]
        P0 = dict(learn.P); P0.update(kw.get("P", {})); old = learn.P; learn.P = P0
        m = learn.fit(X, c, b, w, kw.get("n1", 220), kw.get("n2", 150)); learn.P = old; return m
    out["history only"] = tr(0)
    for w in (0.5, 1, 2, 4, 8): out[f"history + live x{w}"] = tr(w)
    out["history only, smaller trees"] = tr(0, P={"num_leaves": 15, "min_data_in_leaf": 400})
    out["history + live x2, 400 trees"] = tr(2, n1=400, n2=250)
    return out

if __name__ == "__main__":
    Xh, ch, bh, wh = learn.hist(); Xl, cl, bl, tl = load_live()
    cut = int(0.7 * len(Xl)) // 10 * 10
    res = {k: score(m, Xl[cut:], cl[cut:], bl[cut:]) for k, m in recipes(Xh, ch, bh, wh, Xl, cl, bl, tl, cut).items()}
    print(pd.DataFrame(res).T.round(4).to_string())
