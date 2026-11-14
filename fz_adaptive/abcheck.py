"""Realised outcomes per model_version from our own logged impressions (noisy; the leaderboard's expected score is the judge)."""
import numpy as np, pandas as pd, json
from features import D, FEATS, FI
nF = len(FEATS); Y = pd.DataFrame([json.loads(l) for l in open(D / f"live_Y{nF}.jsonl")])
X = np.fromfile(D / f"live_X{nF}.f32", dtype=np.float32); n = min(len(Y), len(X) // (10 * nF)); X = X[:n * 10 * nF].reshape(n, 10, nF); Y = Y.iloc[:n].copy()
Y["click"] = Y.c >= 0; Y["buy"] = Y.b >= 0; Y["has_rv"] = X[:, 0, FI["n_rv"]] > 0; Y["incat"] = np.nanmean(X[:, :, FI["same_cat_last"]], 1)
print(Y.groupby("mv").agg(n=("c", "size"), click=("click", "mean"), buy=("buy", "mean"), buys=("buy", "sum"), incat=("incat", "mean")).round(4))
print(Y.groupby("x").agg(n=("c", "size"), click9=("c", lambda s: (s == 9).mean()), buy9=("b", lambda s: (s == 9).mean())).round(4))
