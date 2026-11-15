"""Feature ablation judged on the internal benchmark (all live impressions; models trained on history only)."""
import numpy as np, pandas as pd, lightgbm as lgb, learn
from sklearn.metrics import roc_auc_score
from features import FEATS, FI
learn.P["num_threads"] = 3
Xh, ch, bh, wh = learn.hist(); Xl, cl, bl, tl = learn.live()
G = {"none": [], "cart": ["u_cart", "u_cart_age"], "user counts": ["u_ln", "u_lb"], "user price": ["dprice_u", "zprice_u", "dprice_ub"],
     "user attr": ["u_attr_v", "u_attr_b"], "user brand": ["u_brand_v", "u_brand_b"], "user sub/cat": ["u_sub_v", "u_sub_b", "u_cat_v", "u_cat_b"],
     "session attr": ["attr_last", "attr_rv"], "ctx": ["ctx_lift", "device", "page"], "pop": ["pop_conv", "pop_lv", "pop_lb", "pop_cart", "pop_lb_rel_sub"],
     "cat match": ["same_cat_last", "frac_cat_rv"], "sub/brand match": ["same_sub_last", "same_brand_last", "frac_sub_rv", "frac_brand_rv"], "in_rv": ["in_rv_w", "is_last"], "price vs session": ["dprice_last", "dprice_rv"], "price": ["lprice", "lprice_rel_sub"], "live zeros": ["tr_item", "tr_sub", "live_conv_d", "is_new", "ldisc"]}
rows = {}
for name, drop in G.items():
    cols = [i for i, f in enumerate(FEATS) if f not in drop]; names = [FEATS[i] for i in cols]
    m1 = lgb.train(learn.P, lgb.Dataset(Xh[:, cols], ch, weight=wh, feature_name=names), 220)
    m2 = lgb.train({**learn.P, "min_data_in_leaf": 50, "num_leaves": 15}, lgb.Dataset(Xh[ch][:, cols], bh[ch], feature_name=names), 150)
    pc = m1.predict(Xl[:, cols]); pb = pc * m2.predict(Xl[:, cols])
    X0 = Xl.copy(); X0[:, FI["slot"]] = 0; X0 = X0[:, cols]
    s0 = (m1.predict(X0) * m2.predict(X0)).reshape(-1, 10)
    def mrr(lab):
        C = lab.reshape(-1, 10); r = C.any(1); return float((1 / ((s0[r] > s0[r][C[r]][:, None]).sum(1) + 1)).mean())
    rows[name] = dict(click_auc=round(roc_auc_score(cl, pc), 4), buy_auc=round(roc_auc_score(bl, pb), 4), mrr_click=round(mrr(cl), 4), mrr_buy=round(mrr(bl), 4))
    print(name, rows[name], flush=True)
