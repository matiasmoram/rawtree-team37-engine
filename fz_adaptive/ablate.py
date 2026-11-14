"""Feature ablation judged on the internal benchmark (all live impressions; models trained on history only)."""
import numpy as np, pandas as pd, lightgbm as lgb, learn
from sklearn.metrics import roc_auc_score
from features import FEATS, FI
learn.P["num_threads"] = 3
Xh, ch, bh, wh = learn.hist(); Xl, cl, bl, tl = learn.live()
G = {"none": [], "cart": ["u_cart", "u_cart_age"], "user counts": ["u_ln", "u_lb"], "user price": ["dprice_u", "zprice_u", "dprice_ub"],
     "user attr": ["u_attr_v", "u_attr_b"], "user brand": ["u_brand_v", "u_brand_b"], "user sub/cat": ["u_sub_v", "u_sub_b", "u_cat_v", "u_cat_b"],
     "session attr": ["attr_last", "attr_rv"], "ctx": ["ctx_lift", "device", "page"], "pop": ["pop_conv", "pop_lv", "pop_lb", "pop_cart", "pop_lb_rel_sub"],
     "cat match": ["same_cat_last", "frac_cat_rv"], "live zeros": ["tr_item", "tr_sub", "live_conv_d", "is_new", "ldisc"]}
rows = {}
for name, drop in G.items():
    cols = [i for i, f in enumerate(FEATS) if f not in drop]; names = [FEATS[i] for i in cols]
    m1 = lgb.train(learn.P, lgb.Dataset(Xh[:, cols], ch, weight=wh, feature_name=names), 220)
    m2 = lgb.train({**learn.P, "min_data_in_leaf": 50, "num_leaves": 15}, lgb.Dataset(Xh[ch][:, cols], bh[ch], feature_name=names), 150)
    pc = m1.predict(Xl[:, cols]); pb = pc * m2.predict(Xl[:, cols])
    rows[name] = dict(click_auc=roc_auc_score(cl, pc), buy_auc=roc_auc_score(bl, pb), calib=pb.sum() / bl.sum())
    print(name, rows[name], flush=True)
