"""Continuous learning: every few minutes retrain the model on the historical log + our own live feedback.

Live rows are the exact feature vectors used at serving time (logged by the ranker) with the realised click /
purchase, so the model learns what the history cannot show: price changes, trends, new products, products
outside the browsed category. Live rows are up-weighted and recent ones count more (the market moves).
    python learn.py            # loop
    python learn.py once
"""
import sys, time, json, pickle
import numpy as np, pandas as pd, lightgbm as lgb
from sklearn.metrics import roc_auc_score
from features import FEATS, D

VERSION = "fz-v2-adaptive"
LIVE_W, RECENCY_H, EVERY = 0.5, 6.0, 600
P = dict(objective="binary", learning_rate=0.1, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8, bagging_fraction=0.8,
         bagging_freq=1, lambda_l2=5.0, verbose=-1, num_threads=6)
nF = len(FEATS)

def hist():
    X = np.load(D / "train_X.npy"); M = pd.read_parquet(D / "train_M.parquet")
    if X.shape[1] < nF: X = np.hstack([X, np.zeros((len(X), nF - X.shape[1]), np.float32)])   # live-only features are 0 in the history
    return X, M.click.values, M.buy.values, M.w.values

def live():
    f = D / f"live_Y{nF}.jsonl"
    if not f.exists(): return None
    Y = pd.DataFrame([json.loads(l) for l in open(f)])
    X = np.fromfile(D / f"live_X{nF}.f32", dtype=np.float32)
    n = min(len(Y), len(X) // (10 * nF)); Y = Y.iloc[:n]; X = X[:n * 10 * nF].reshape(n * 10, nF)
    slot = np.tile(np.arange(10), n)
    return X, slot == np.repeat(Y.c.values, 10), slot == np.repeat(Y.b.values, 10), np.repeat(Y.t.values, 10) / 1000

def fit(X, click, buy, w, n_click, n_bgc):
    m1 = lgb.train(P, lgb.Dataset(X, click, weight=w, feature_name=FEATS), n_click)
    m2 = lgb.train({**P, "min_data_in_leaf": 50, "num_leaves": 15}, lgb.Dataset(X[click], buy[click], weight=w[click], feature_name=FEATS), n_bgc)
    return {"click": m1, "buy_given_click": m2}

def cycle(Xh, ch, bh, wh, cfg):
    L = live(); n_click, n_bgc = 220, 150
    if L is None or len(L[0]) < 8000:
        X, c, b, w = Xh, ch, bh, wh; note = "history only"
    else:
        Xl, cl, bl, tl = L
        wl = LIVE_W * 0.5 ** ((tl.max() - tl) / (RECENCY_H * 3600))
        # honest check: train without the newest 20% of live rows, score them, compare with a history-only model
        cut = int(0.8 * len(Xl)) // 10 * 10
        if cl[cut:].sum() > 30:
            a = fit(np.vstack([Xh, Xl[:cut]]), np.r_[ch, cl[:cut]], np.r_[bh, bl[:cut]], np.r_[wh, wl[:cut]], n_click, n_bgc)
            h = fit(Xh, ch, bh, wh, n_click, n_bgc)
            pa = a["click"].predict(Xl[cut:]); ph = h["click"].predict(Xl[cut:])
            note = f"live rows={len(Xl)//10} clicks={int(cl.sum())} buys={int(bl.sum())} | newest-20% click AUC: history-only={roc_auc_score(cl[cut:], ph):.4f} history+live={roc_auc_score(cl[cut:], pa):.4f}"
            use_live = roc_auc_score(cl[cut:], pa) > roc_auc_score(cl[cut:], ph)   # gate: live rows go in only if they help on unseen live data
            note += f" -> {'USING' if use_live else 'NOT using'} live rows"
        else: note = f"live rows={len(Xl)//10}"; use_live = False
        if use_live: X, c, b, w = np.vstack([Xh, Xl]), np.r_[ch, cl], np.r_[bh, bl], np.r_[wh, wl]
        else: X, c, b, w = Xh, ch, bh, wh
    m = fit(X, c, b, w, n_click, n_bgc)
    tmp = D / "model.tmp"
    cfg = json.load(open(D / "cfg.json")) if (D / "cfg.json").exists() else cfg   # re-read: the config may have changed while training
    pickle.dump({"models": {k: v.model_to_string() for k, v in m.items()}, "feats": FEATS, "version": cfg.get("version", VERSION), "cfg": cfg}, open(tmp, "wb"))
    tmp.replace(D / "model.pkl")
    imp = pd.Series(m["click"].feature_importance("gain"), FEATS); imp = (imp / imp.sum()).sort_values(ascending=False)
    print(time.strftime("%H:%M:%S"), "model written.", note, "| top feats:", imp.head(8).round(3).to_dict(), flush=True)

if __name__ == "__main__":
    Xh, ch, bh, wh = hist()
    cfg = json.load(open(D / "cfg.json")) if (D / "cfg.json").exists() else {}
    while True:
        t = time.time()
        try: cycle(Xh, ch, bh, wh, json.load(open(D / "cfg.json")) if (D / "cfg.json").exists() else {})
        except Exception as e: print("learn error", repr(e)[:300], flush=True)
        if len(sys.argv) > 1: break
        time.sleep(max(30, EVERY - (time.time() - t)))
