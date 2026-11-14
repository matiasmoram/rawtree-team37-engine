"""Change the live config / version without retraining: python setcfg.py version key=value ...  (server hot-reloads in <20 s)"""
import sys, json, pickle
from features import D
f = D / "cfg.json"; cfg = json.load(open(f)) if f.exists() else {}
cfg["version"] = sys.argv[1]
for kv in sys.argv[2:]:
    k, v = kv.split("="); cfg[k] = json.loads(v)
json.dump(cfg, open(f, "w"))
m = pickle.load(open(D / "model.pkl", "rb")); m["cfg"] = cfg; m["version"] = cfg["version"]
pickle.dump(m, open(D / "model.tmp", "wb")); (D / "model.tmp").replace(D / "model.pkl"); print(cfg)
