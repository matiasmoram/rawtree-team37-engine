"""Train the ranking model on the 30 most recent days of shop.history_sessions (logged carousel impressions).

Rows = (impression, shown product). Labels = clicked / purchased. The slot is a feature (position bias) and is
fixed to 0 when ranking. User features are hidden for a random 30% of impressions so the model also learns to
rank for shoppers without history (cold start).
    python train.py build | fit
"""
import sys, glob, time, pickle
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score
from features import Store, FEATS, FI, D

KEEP = 0.12  # share of no-click impressions kept (re-weighted by 1/KEEP)

def build():
    st = Store(); rng = np.random.default_rng(0)
    files = sorted(glob.glob(str(D / "se_2026-1[01]-*.parquet")))[-30:]
    X, meta = [], []
    for f in files:
        df = pd.read_parquet(f); t0 = time.time()
        keep = (df.clicked != "") | (rng.random(len(df)) < KEEP)
        df = df[keep]
        for gid, r in enumerate(df.itertuples()):
            c = np.array([st.idx[p] for p in r.shown])
            use_user = rng.random() > 0.3
            req = {"u": r.u, "d": r.d, "r": r.r, "pg": r.pg, "rv": list(r.rv), "t": r.t}
            X.append(st.feats(req, c, slot=np.arange(10), use_user=use_user))
            w = 1.0 if r.clicked else 1 / KEEP
            for k, p in enumerate(r.shown):
                meta.append((f[-13:-8], r.rid, p == r.clicked, p == r.purchased, w, r.propensity[k], r.u in st.uidx and r.purchased != "" ))
        print(f[-18:], len(df), round(time.time() - t0, 1), flush=True)
    X = np.concatenate(X); M = pd.DataFrame(meta, columns=["day", "rid", "click", "buy", "w", "prop", "x"])
    np.save(D / "train_X.npy", X); M.to_parquet(D / "train_M.parquet"); print(X.shape, M.click.sum(), M.buy.sum())

def fit(drop=()):
    X = np.load(D / "train_X.npy"); M = pd.read_parquet(D / "train_M.parquet")
    cols = [i for i, f in enumerate(FEATS) if f not in drop]; names = [FEATS[i] for i in cols]
    va = np.arange(len(M)) >= int(0.87 * len(M)); tr = ~va  # rows are in time order: validate on the last ~4 days
    P = dict(objective="binary", learning_rate=0.05, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8, bagging_fraction=0.8,
             bagging_freq=1, lambda_l2=5.0, verbose=-1, num_threads=8)
    out = {}
    for label in ["click", "buy"]:
        dtr = lgb.Dataset(X[tr][:, cols], M[label].values[tr], weight=M.w.values[tr], feature_name=names)
        dva = lgb.Dataset(X[va][:, cols], M[label].values[va], weight=M.w.values[va], feature_name=names)
        m = lgb.train(P, dtr, 2000, valid_sets=[dva], callbacks=[lgb.early_stopping(50, verbose=False)])
        p = m.predict(X[va][:, cols])
        print(label, "iters", m.best_iteration, "logloss", m.best_score["valid_0"]["binary_logloss"], "AUC", roc_auc_score(M[label].values[va], p, sample_weight=M.w.values[va]))
        imp = pd.Series(m.feature_importance("gain"), names).sort_values(ascending=False); print((imp / imp.sum()).round(3).head(25).to_dict())
        out[label] = m
    # P(buy | click) on clicked rows
    ck = M.click.values
    dtr = lgb.Dataset(X[tr & ck][:, cols], M.buy.values[tr & ck], feature_name=names); dva = lgb.Dataset(X[va & ck][:, cols], M.buy.values[va & ck], feature_name=names)
    m = lgb.train({**P, "min_data_in_leaf": 50, "num_leaves": 15}, dtr, 2000, valid_sets=[dva], callbacks=[lgb.early_stopping(50, verbose=False)])
    print("buy|click iters", m.best_iteration, "AUC", roc_auc_score(M.buy.values[va & ck], m.predict(X[va & ck][:, cols])))
    imp = pd.Series(m.feature_importance("gain"), names).sort_values(ascending=False); print((imp / imp.sum()).round(3).head(15).to_dict())
    out["buy_given_click"] = m
    p2 = out["click"].predict(X[va][:, cols]) * m.predict(X[va][:, cols])
    print("click x buy|click AUC for buy:", roc_auc_score(M.buy.values[va], p2, sample_weight=M.w.values[va]))
    return out, names

if __name__ == "__main__":
    if sys.argv[1] == "build": build()
    else:
        out, names = fit()
        pickle.dump({"models": {k: m.model_to_string() for k, m in out.items()}, "feats": names}, open(D / "model_hist.pkl", "wb"))
