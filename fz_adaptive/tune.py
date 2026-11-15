"""Model-capacity variants trained on history only, judged on the internal benchmark (all live impressions)."""
import numpy as np, lightgbm as lgb, learn
from sklearn.metrics import roc_auc_score
from features import FEATS, FI
learn.P["num_threads"] = 3
Xh, ch, bh, wh = learn.hist(); Xl, cl, bl, tl = learn.live()
X0 = Xl.copy(); X0[:, FI["slot"]] = 0
def ev(m1, m2, name):
    s0 = (m1.predict(X0) * m2.predict(X0)).reshape(-1, 10); pb = m1.predict(Xl) * m2.predict(Xl)
    def mrr(lab):
        C = lab.reshape(-1, 10); r = C.any(1); return float((1 / ((s0[r] > s0[r][C[r]][:, None]).sum(1) + 1)).mean())
    print(f"{name:34s} buy_auc={roc_auc_score(bl, pb):.4f} mrr_click={mrr(cl):.4f} mrr_buy={mrr(bl):.4f}", flush=True)
V = {"current (lr .1, 220/150 trees)": ({}, 220, {}, 150), "lr .05, 450/300 trees": ({"learning_rate": .05}, 450, {"learning_rate": .05}, 300),
     "63 leaves": ({"num_leaves": 63}, 220, {}, 150), "110/75 trees": ({}, 110, {}, 75), "min leaf 1000 (smoother)": ({"min_data_in_leaf": 1000}, 220, {"min_data_in_leaf": 200}, 150)}
for name, (p1, n1, p2, n2) in V.items():
    m1 = lgb.train({**learn.P, **p1}, lgb.Dataset(Xh, ch, weight=wh, feature_name=FEATS), n1)
    m2 = lgb.train({**learn.P, "min_data_in_leaf": 50, "num_leaves": 15, **p2}, lgb.Dataset(Xh[ch], bh[ch], weight=wh[ch], feature_name=FEATS), n2)
    ev(m1, m2, name)
