"""LightGBM rankers trained on live feedback, with a time-based validation report.

Models (all keep ``slot`` as a feature so position bias is absorbed; serving scores every candidate at slot=0):
  (a) click model      P(click | x, slot)                   binary LightGBM on every shown item
  (b) purchase model   P(purchase | x, slot)                binary LightGBM on every shown item
  (c) factored         P(click | x, slot) * P(purchase | click, x), where the second factor is a smoothed constant
                       rate or a strongly L2-regularised logistic regression fitted on clicked items only.

Validation: requests are ordered by ts; the earlier ``1 - valid_frac`` share trains, the rest validates (time-strict:
train ts < cutoff <= valid ts). Early stopping and the small hyperparameter search use the validation slice only.
Reported validation numbers are therefore slightly optimistic (selection and evaluation share the slice).
The served models are refitted on all rows with the selected parameters and ``best_iter * n_all / n_train`` rounds.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score

from ..features import FEATURES, FIDX
from .dataset import relation
from .scoring import pc_predict

log = logging.getLogger("learn.train")

SLOT = FIDX["slot"]
BASE_PARAMS = {
    "objective": "binary", "metric": "binary_logloss", "learning_rate": 0.03,
    "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "min_sum_hessian_in_leaf": 1e-3,
    "verbose": -1, "seed": 37, "deterministic": True, "force_row_wise": True, "num_threads": 4,
    # Examination can only fall with position: forbid the trees from learning slot-specific bumps (e.g. a fixed
    # fallback list that always puts the same item in slot 9), so the position effect stays a clean nuisance term.
    "monotone_constraints": [-1 if f == "slot" else 0 for f in FEATURES],
}
# 12 conservative configurations (the same grid is searched for the click and for the purchase model).
GRID = [{"num_leaves": nl, "min_data_in_leaf": md, "lambda_l2": l2}
        for nl in (7, 15, 31) for md in (200, 800) for l2 in (1.0, 20.0)]
MAX_ROUNDS = 3000
EARLY_STOP = 100
PC_CS = (0.01, 0.1)          # inverse L2 strength of the P(purchase | click) logistic candidates
PC_CLIP = 5.0
RATE_PRIOR = 50.0            # pseudo-count for the smoothed slot / relation baselines
PREFER_FACTORED_MARGIN = 0.01  # the purchase model is served only if its validation purchase AUC is this much higher
N_BOOT = 2000


# ---- helpers -----------------------------------------------------------------------------------------------------

def auc(y: np.ndarray, p: np.ndarray) -> float:
    return float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else float("nan")


def logloss(y: np.ndarray, p: np.ndarray) -> float:
    return float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6), labels=[0, 1]))


def at_slot0(X: np.ndarray) -> np.ndarray:
    X0 = X.copy()
    X0[:, SLOT] = 0.0
    return X0


@dataclass
class Split:
    tr: np.ndarray       # row mask
    va: np.ndarray       # row mask
    cutoff: pd.Timestamp
    n_req_tr: int
    n_req_va: int


def time_split(df: pd.DataFrame, valid_frac: float) -> Split:
    """Train on requests with ts < cutoff, validate on ts >= cutoff; cutoff = ts quantile of distinct requests."""
    first = df.groupby("request_id", sort=False)["ts"].first().sort_values(kind="stable")
    cutoff = first.iloc[int(round(len(first) * (1 - valid_frac)))]
    tr = (df["ts"] < cutoff).to_numpy()
    va = ~tr
    return Split(tr, va, cutoff, int((first < cutoff).sum()), int((first >= cutoff).sum()))


def train_booster(params: dict, Xtr, ytr, Xva=None, yva=None, rounds: int | None = None) -> lgb.Booster:
    p = {**BASE_PARAMS, **params}
    dtr = lgb.Dataset(Xtr, label=ytr, feature_name=FEATURES, free_raw_data=False)
    if Xva is None:
        return lgb.train(p, dtr, num_boost_round=rounds)
    dva = lgb.Dataset(Xva, label=yva, reference=dtr, free_raw_data=False)
    return lgb.train(p, dtr, num_boost_round=MAX_ROUNDS, valid_sets=[dva], valid_names=["valid"],
                     callbacks=[lgb.early_stopping(EARLY_STOP, first_metric_only=True, verbose=False)])


def search(Xtr, ytr, Xva, yva, label: str) -> tuple[dict, lgb.Booster, list[dict]]:
    """Fit every GRID config with early stopping on the validation slice; select by validation log loss."""
    results, boosters = [], []
    for params in GRID:
        t0 = time.time()
        b = train_booster(params, Xtr, ytr, Xva, yva)
        it = int(b.best_iteration or b.current_iteration())
        p = b.predict(Xva, num_iteration=it)
        results.append({"params": params, "best_iter": it, "val_logloss": logloss(yva, p), "val_auc": auc(yva, p),
                        "secs": round(time.time() - t0, 1)})
        boosters.append(b)
        log.info("%s %s iter=%d ll=%.5f auc=%.4f", label, params, it, results[-1]["val_logloss"], results[-1]["val_auc"])
    k = int(np.argmin([r["val_logloss"] for r in results]))
    return results[k], boosters[k], results


def fit_pc(Xtr, ytr, Xva, yva) -> tuple[dict, list[dict]]:
    """P(purchase | click): smoothed constant rate vs strongly regularised logistic regressions (clicked rows only)."""
    cands: list[dict] = [{"kind": "rate", "p": float((ytr.sum() + 1) / (len(ytr) + 2))}]
    mu = Xtr.mean(axis=0).astype(np.float64)
    sd = Xtr.std(axis=0).astype(np.float64)
    sd[sd < 1e-6] = 1.0
    Z = np.clip((Xtr - mu) / sd, -PC_CLIP, PC_CLIP)
    for C in PC_CS:
        lr = LogisticRegression(C=C, max_iter=5000)
        lr.fit(Z, ytr)
        cands.append({"kind": "logreg", "C": C, "mu": mu.tolist(), "sd": sd.tolist(), "w": lr.coef_[0].tolist(),
                      "b": float(lr.intercept_[0]), "clip": PC_CLIP})
    table = []
    for c in cands:
        p = pc_predict(c, Xva)
        table.append({"model": c["kind"] + (f"(C={c['C']})" if c["kind"] == "logreg" else ""),
                      "val_logloss": logloss(yva, p), "val_auc": auc(yva, p)})
    k = int(np.argmin([t["val_logloss"] for t in table]))
    return cands[k], table


def refit_pc(choice: dict, X, y) -> dict:
    if choice["kind"] == "rate":
        return {"kind": "rate", "p": float((y.sum() + 1) / (len(y) + 2))}
    mu = X.mean(axis=0).astype(np.float64)
    sd = X.std(axis=0).astype(np.float64)
    sd[sd < 1e-6] = 1.0
    lr = LogisticRegression(C=choice["C"], max_iter=5000).fit(np.clip((X - mu) / sd, -PC_CLIP, PC_CLIP), y)
    return {"kind": "logreg", "C": choice["C"], "mu": mu.tolist(), "sd": sd.tolist(), "w": lr.coef_[0].tolist(),
            "b": float(lr.intercept_[0]), "clip": PC_CLIP}


def group_rates(keys_tr, y_tr, keys_va) -> np.ndarray:
    """Smoothed per-group rate learned on train, applied to validation keys."""
    g = float(y_tr.mean())
    s = pd.DataFrame({"k": keys_tr, "y": y_tr}).groupby("k")["y"].agg(["sum", "count"])
    rate = (s["sum"] + RATE_PRIOR * g) / (s["count"] + RATE_PRIOR)
    return pd.Series(keys_va).map(rate).fillna(g).to_numpy(dtype=np.float64)


# ---- ranking metrics on the shown 10 -----------------------------------------------------------------------------

def positive_ranks(req: np.ndarray, slot: np.ndarray, score: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """1-based rank of each positive item when its request's shown items are sorted by (-score, logged slot).
    Returns (request code, rank) sorted by request code, so arrays from different scores align."""
    order = np.lexsort((slot, -score, req))
    rs = req[order]
    starts = np.r_[0, np.flatnonzero(np.diff(rs)) + 1]
    sizes = np.diff(np.r_[starts, len(rs)])
    pos = np.arange(len(rs)) - np.repeat(starts, sizes)
    m = y[order] == 1
    return rs[m], pos[m] + 1


def rank_metrics(ranks: np.ndarray) -> dict[str, np.ndarray]:
    return {"ndcg": 1.0 / np.log2(ranks + 1.0), "top3": (ranks <= 3).astype(float), "mrr": 1.0 / ranks}


def boot_ci(diff: np.ndarray, seed: int = 37) -> tuple[float, float]:
    if len(diff) == 0:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = diff[rng.integers(0, len(diff), size=(N_BOOT, len(diff)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


# ---- sanity checks -----------------------------------------------------------------------------------------------

SHAP_CHECKS = [
    # name, condition on X (slot 0), feature group whose SHAP is summed, expected sign of (mean on cond - mean off cond)
    ("user bought before", lambda X: X[:, FIDX["user_bought_n"]] > 0, ["user_bought_n", "user_days_since_buy"], -1),
    ("bought during event", lambda X: X[:, FIDX["bought_in_event"]] > 0, ["bought_in_event"], -1),
    ("last viewed item", lambda X: X[:, FIDX["is_last_view"]] > 0,
     ["is_last_view", "view_rank", "n_item_views", "mins_since_item_view"], +1),
    ("viewed earlier in session", lambda X: (X[:, FIDX["view_rank"]] >= 1) & (X[:, FIDX["view_rank"]] < 9),
     ["is_last_view", "view_rank", "n_item_views", "mins_since_item_view"], +1),
    ("user viewed before (history)", lambda X: X[:, FIDX["user_viewed_n"]] > 0, ["user_viewed_n", "user_days_since_view"], +1),
    ("same subcategory as last view", lambda X: X[:, FIDX["same_sub_last"]] > 0, ["same_sub_last", "sess_sub_share"], +1),
]


def shap_checks(booster: lgb.Booster, X: np.ndarray) -> list[dict]:
    """Directional checks on SHAP contributions (log-odds) at slot 0, plus the position curve at logged slots."""
    X0 = at_slot0(X)
    C = booster.predict(X0, pred_contrib=True)
    out = []
    for name, cond, group, sign in SHAP_CHECKS:
        m = cond(X0)
        contrib = C[:, [FIDX[g] for g in group]].sum(axis=1)
        if m.sum() == 0 or (~m).sum() == 0 or not np.any(contrib):
            # no rows on one side, or the model never splits on these features (no learned effect at all)
            out.append({"check": name, "n": int(m.sum()), "effect": None, "expected": sign, "ok": None,
                        "note": "feature unused by the model" if m.sum() and not np.any(contrib) else "no rows"})
            continue
        effect = float(contrib[m].mean() - contrib[~m].mean())
        out.append({"check": name, "n": int(m.sum()), "effect": effect, "expected": sign, "ok": bool(np.sign(effect) == sign)})
    # Position curve: the same rows evaluated at every slot (counterfactual), mean prediction relative to slot 1.
    rng = np.random.default_rng(37)
    Xs = X[rng.choice(len(X), size=min(len(X), 20000), replace=False)].copy()
    means = []
    for s in range(10):
        Xs[:, SLOT] = s
        means.append(float(booster.predict(Xs).mean()))
    curve = [m / means[0] for m in means]
    dec = all(curve[i] >= curve[i + 1] - 1e-12 for i in range(9))
    out.append({"check": "position curve non-increasing (slot 1..10)", "n": int(len(Xs)), "effect": curve[0] - curve[-1],
                "expected": +1, "ok": bool(dec), "curve": curve})
    return out


# ---- main entry --------------------------------------------------------------------------------------------------

def _fmt(x, nd=4) -> str:
    return "   n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{nd}f}"


def run(df: pd.DataFrame, meta: dict, out_path: Path, valid_frac: float = 0.25) -> dict:
    t_start = time.time()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    X = df[FEATURES].to_numpy(dtype=np.float32)
    yc = df["click"].to_numpy(dtype=np.int32)
    yp = df["purchase"].to_numpy(dtype=np.int32)
    req = pd.factorize(df["request_id"])[0]
    slot = X[:, SLOT]
    rel = relation(X)
    sp = time_split(df, valid_frac)
    tr, va = sp.tr, sp.va
    Xtr, Xva = X[tr], X[va]
    Xva0 = at_slot0(Xva)

    print("=" * 100)
    print(f"DATASET  {meta['since']} -> {meta['until']}  snapshot T0={meta['snapshot_T0']}")
    print(f"  requests={meta['requests']} rows={meta['rows']} clicks={meta['clicks']} purchases={meta['purchases']} "
          f"(team rows={meta['rows_team']}, fallback rows={meta['rows_fallback']}, "
          f"unknown items dropped={meta['unknown_items_dropped']})")
    print(f"SPLIT    cutoff={sp.cutoff}  train: {sp.n_req_tr} req / {tr.sum()} rows / {yc[tr].sum()} clicks / "
          f"{yp[tr].sum()} buys   valid: {sp.n_req_va} req / {va.sum()} rows / {yc[va].sum()} clicks / {yp[va].sum()} buys")
    ctr_slot = [float(yc[tr][slot[tr] == s].mean()) for s in range(10)]
    print("  train CTR by slot (%):", " ".join(f"{100 * c:.2f}" for c in ctr_slot))

    # ---- (a) click and (b) purchase models: small grid, early stopping on the validation slice ------------------
    best_c, bc, grid_c = search(Xtr, yc[tr], Xva, yc[va], "click")
    best_p, bp, grid_p = search(Xtr, yp[tr], Xva, yp[va], "purchase")
    print("\nHYPERPARAMETER SEARCH (selected by validation log loss)")
    print(f"  {'num_leaves':>10s} {'min_leaf':>8s} {'l2':>5s} | {'click it':>8s} {'click ll':>9s} {'click auc':>9s} | "
          f"{'buy it':>6s} {'buy ll':>9s} {'buy auc':>8s}")
    for rc, rp in zip(grid_c, grid_p):
        q = rc["params"]
        print(f"  {q['num_leaves']:>10d} {q['min_data_in_leaf']:>8d} {q['lambda_l2']:>5.0f} | {rc['best_iter']:>8d} "
              f"{rc['val_logloss']:>9.5f} {rc['val_auc']:>9.4f} | {rp['best_iter']:>6d} {rp['val_logloss']:>9.5f} {rp['val_auc']:>8.4f}")
    print(f"  chosen click: {best_c['params']} iter={best_c['best_iter']}   chosen purchase: {best_p['params']} iter={best_p['best_iter']}")

    # ---- (c) P(purchase | click) on clicked rows -------------------------------------------------------------------
    ctr_m, cva_m = yc[tr] == 1, yc[va] == 1
    pc_choice, pc_table = fit_pc(Xtr[ctr_m], yp[tr][ctr_m], Xva[cva_m], yp[va][cva_m])
    print("\nP(purchase | click) candidates (validation clicked rows, n=%d, buys=%d)" % (cva_m.sum(), yp[va][cva_m].sum()))
    for t in pc_table:
        print(f"  {t['model']:<16s} logloss={t['val_logloss']:.4f} auc={_fmt(t['val_auc'])}")
    print(f"  chosen: {pc_choice['kind']}" + (f" C={pc_choice['C']}" if pc_choice["kind"] == "logreg" else f" p={pc_choice['p']:.3f}"))

    # ---- validation table ------------------------------------------------------------------------------------------
    ic, ip = best_c["best_iter"], best_p["best_iter"]
    pc_va, pc_va0 = pc_predict(pc_choice, Xva), pc_predict(pc_choice, Xva0)
    p_click, p_click0 = bc.predict(Xva, num_iteration=ic), bc.predict(Xva0, num_iteration=ic)
    p_buy, p_buy0 = bp.predict(Xva, num_iteration=ip), bp.predict(Xva0, num_iteration=ip)
    slot_c = group_rates(slot[tr].astype(int), yc[tr], slot[va].astype(int))
    slot_p = group_rates(slot[tr].astype(int), yp[tr], slot[va].astype(int))
    rel_c = group_rates(rel[tr], yc[tr], rel[va])
    rel_p = group_rates(rel[tr], yp[tr], rel[va])
    models = {
        # name: (calibrated click prob or None, calibrated purchase prob or None, score for AUC, ranking score)
        "logged order": (None, None, None, -slot[va]),
        "slot-only (train rates)": (slot_c, slot_p, slot_c, slot_c),
        "relation rates (train)": (rel_c, rel_p, rel_p, rel_p),
        "click lgbm": (p_click, None, p_click, p_click0),
        "purchase lgbm": (None, p_buy, p_buy, p_buy0),
        "factored click*pc": (p_click, p_click * pc_va, p_click * pc_va, p_click0 * pc_va0),
    }
    req_va, slot_va, yc_va, yp_va = req[va], slot[va], yc[va], yp[va]
    rows, per_req = [], {}
    for name, (pcal, pbuy, s_auc, s_rank) in models.items():
        _, rk_c = positive_ranks(req_va, slot_va, s_rank, yc_va)
        _, rk_p = positive_ranks(req_va, slot_va, s_rank, yp_va)
        mc, mp = rank_metrics(rk_c), rank_metrics(rk_p)
        per_req[name] = (mc, mp)
        rows.append({
            "model": name,
            "click_auc": auc(yc_va, s_auc) if s_auc is not None else None,
            "click_logloss": logloss(yc_va, pcal) if pcal is not None else None,
            "purchase_auc": auc(yp_va, s_auc) if s_auc is not None else None,
            "purchase_logloss": logloss(yp_va, pbuy) if pbuy is not None else None,
            "click_ndcg": float(mc["ndcg"].mean()), "click_top3": float(mc["top3"].mean()),
            "purchase_ndcg": float(mp["ndcg"].mean()), "purchase_top3": float(mp["top3"].mean()),
        })
    n_rc, n_rp = len(per_req["logged order"][0]["ndcg"]), len(per_req["logged order"][1]["ndcg"])
    print(f"\nVALIDATION ({sp.n_req_va} requests; ranking metrics re-rank each request's shown items at slot=0, "
          f"over {n_rc} requests with a click / {n_rp} with a purchase)")
    hdr = (f"  {'model':<26s} {'clk AUC':>7s} {'clk LL':>7s} {'buy AUC':>7s} {'buy LL':>7s} | {'clk NDCG':>8s} "
           f"{'clk top3':>8s} {'buy NDCG':>8s} {'buy top3':>8s}")
    print(hdr)
    for r in rows:
        print(f"  {r['model']:<26s} {_fmt(r['click_auc']):>7s} {_fmt(r['click_logloss'], 5):>7s} {_fmt(r['purchase_auc']):>7s} "
              f"{_fmt(r['purchase_logloss'], 5):>7s} | {_fmt(r['click_ndcg']):>8s} {_fmt(r['click_top3']):>8s} "
              f"{_fmt(r['purchase_ndcg']):>8s} {_fmt(r['purchase_top3']):>8s}")
    print("  (random order: top3 = 0.30, NDCG ~ 0.39)")

    # ---- serving choice (pre-declared rule) ------------------------------------------------------------------------
    by_name = {r["model"]: r for r in rows}
    auc_f, auc_p = by_name["factored click*pc"]["purchase_auc"], by_name["purchase lgbm"]["purchase_auc"]
    kind = "purchase" if (auc_p - auc_f) > PREFER_FACTORED_MARGIN else "factored"
    chosen_row = "purchase lgbm" if kind == "purchase" else "factored click*pc"
    print(f"\nSERVING CHOICE: {kind} (validation purchase AUC factored={auc_f:.4f} purchase={auc_p:.4f}; "
          f"purchase model served only if better by > {PREFER_FACTORED_MARGIN})")
    deltas = {}
    for base in ("logged order", "relation rates (train)"):
        for lab, k in (("click", 0), ("purchase", 1)):
            for met in ("ndcg", "top3"):
                d = per_req[chosen_row][k][met] - per_req[base][k][met]
                lo, hi = boot_ci(d)
                deltas[f"{lab}_{met}_vs_{base}"] = {"diff": float(d.mean()), "ci95": [lo, hi], "n": int(len(d))}
                print(f"  {chosen_row} - {base:<22s} {lab:>8s} {met:<4s}: {d.mean():+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]  n={len(d)}")

    # ---- relation table on validation (out of sample) --------------------------------------------------------------
    pf, pf0 = p_click * pc_va, p_click0 * pc_va0
    print("\nBY RELATION (validation; observed vs factored model; pred@slot0 is what the policy ranks by)")
    print(f"  {'relation':<16s} {'n':>7s} {'ctr%':>6s} {'buy%':>6s} {'pred buy%':>9s} {'pred@slot0%':>11s}")
    rel_va = rel[va]
    rel_rows = []
    for name in ["viewed_last", "viewed_earlier", "user_viewed", "user_bought", "same_sub", "same_cat", "other", "other_home"]:
        m = rel_va == name
        if not m.any():
            continue
        rr = {"relation": name, "n": int(m.sum()), "ctr": float(yc_va[m].mean()), "buy": float(yp_va[m].mean()),
              "pred_buy": float(pf[m].mean()), "pred_buy_slot0": float(pf0[m].mean())}
        rel_rows.append(rr)
        print(f"  {name:<16s} {rr['n']:>7d} {100 * rr['ctr']:>6.2f} {100 * rr['buy']:>6.3f} {100 * rr['pred_buy']:>9.3f} "
              f"{100 * rr['pred_buy_slot0']:>11.3f}")

    # ---- final refit on all rows -----------------------------------------------------------------------------------
    scale = len(X) / max(1, tr.sum())
    rounds_c = max(1, int(round(ic * scale)))
    rounds_p = max(1, int(round(ip * scale)))
    fc = train_booster(best_c["params"], X, yc, rounds=rounds_c)
    fp = train_booster(best_p["params"], X, yp, rounds=rounds_p)
    cm = yc == 1
    pc_final = refit_pc(pc_choice, X[cm], yp[cm])
    print(f"\nFINAL REFIT on all {len(X)} rows: click rounds={rounds_c}, purchase rounds={rounds_p}, pc={pc_final['kind']}")
    X0 = at_slot0(X)
    served0 = fc.predict(X0) * pc_predict(pc_final, X0) if kind == "factored" else fp.predict(X0)
    print("BY RELATION (all rows; final served score at slot 0 vs observed; slot1 = share of exposures in slot 1)")
    print(f"  {'relation':<16s} {'n':>7s} {'slot1':>6s} {'clicks':>6s} {'buys':>5s} {'buy%':>6s} {'score@slot0%':>12s}")
    rel_final = []
    for name in ["viewed_last", "viewed_earlier", "user_viewed", "user_bought", "same_sub", "same_cat", "other", "other_home"]:
        m = rel == name
        if not m.any():
            continue
        rr = {"relation": name, "n": int(m.sum()), "slot1_share": float((slot[m] == 0).mean()), "clicks": int(yc[m].sum()),
              "buys": int(yp[m].sum()), "score_slot0": float(served0[m].mean())}
        rel_final.append(rr)
        print(f"  {name:<16s} {rr['n']:>7d} {rr['slot1_share']:>6.3f} {rr['clicks']:>6d} {rr['buys']:>5d} "
              f"{100 * rr['buys'] / rr['n']:>6.3f} {100 * rr['score_slot0']:>12.3f}")

    # ---- feature importance and sanity checks (served models) ------------------------------------------------------
    imp = {}
    for lab, b in (("click", fc), ("purchase", fp)):
        g = b.feature_importance(importance_type="gain")
        tot = g.sum() or 1.0
        imp[lab] = sorted(((FEATURES[i], float(100 * g[i] / tot)) for i in range(len(FEATURES))), key=lambda x: -x[1])
    print("\nFEATURE IMPORTANCE (gain %, final models)")
    print(f"  {'click model':<34s} {'purchase model':<34s}")
    for i in range(15):
        (fa, ga), (fb, gb) = imp["click"][i], imp["purchase"][i]
        print(f"  {fa:<24s} {ga:>6.2f}    {fb:<24s} {gb:>6.2f}")

    sanity = {"click": shap_checks(fc, X), "purchase": shap_checks(fp, X)}
    print("\nSANITY CHECKS (mean SHAP log-odds on rows with the property minus rows without, at slot 0; final models;\n"
          "position curve = same rows scored at every slot)")
    for lab in ("click", "purchase"):
        for c in sanity[lab]:
            exp = "+" if c["expected"] > 0 else "-"
            status = f"n/a ({c.get('note', '')})" if c["ok"] is None else ("OK" if c["ok"] else "UNEXPECTED")
            print(f"  [{lab:<8s}] {c['check']:<42s} n={c['n']:>7d} effect={_fmt(c['effect'], 3):>7s} expected {exp}  {status}")
        curve = next(c for c in sanity[lab] if "curve" in c)["curve"]
        print(f"  [{lab:<8s}] position curve P(slot k)/P(slot 1): " + " ".join(f"{v:.2f}" for v in curve))
    print("  observed train CTR by slot / slot 1:            " + " ".join(f"{c / ctr_slot[0]:.2f}" for c in ctr_slot))
    if pc_final["kind"] == "logreg":
        w = np.asarray(pc_final["w"])
        top = np.argsort(-np.abs(w))[:8]
        print("  P(purchase|click) logreg top coefficients (per sd): " + ", ".join(f"{FEATURES[i]}={w[i]:+.3f}" for i in top))
        sanity["pc_top_coefs"] = {FEATURES[i]: float(w[i]) for i in top}

    # ---- save ------------------------------------------------------------------------------------------------------
    stem = out_path.with_suffix("")
    click_file, buy_file = Path(f"{stem}_click.txt"), Path(f"{stem}_purchase.txt")
    fc.save_model(str(click_file))
    fp.save_model(str(buy_file))
    (fc if kind == "factored" else fp).save_model(str(out_path))
    report = {
        "created": datetime.now(timezone.utc).isoformat(), "features": FEATURES,
        "serving": {"kind": kind, "booster": out_path.name, "pc": pc_final if kind == "factored" else None,
                    "slot_at_serving": 0},
        "files": {"serving": out_path.name, "click": click_file.name, "purchase": buy_file.name},
        "dataset": meta,
        "split": {"valid_frac": valid_frac, "cutoff": str(sp.cutoff), "train_requests": sp.n_req_tr,
                  "valid_requests": sp.n_req_va, "train_rows": int(tr.sum()), "valid_rows": int(va.sum()),
                  "train_clicks": int(yc[tr].sum()), "valid_clicks": int(yc[va].sum()),
                  "train_purchases": int(yp[tr].sum()), "valid_purchases": int(yp[va].sum())},
        "base_params": BASE_PARAMS,
        "click": {"chosen": best_c, "grid": grid_c, "final_rounds": rounds_c},
        "purchase": {"chosen": best_p, "grid": grid_p, "final_rounds": rounds_p},
        "pc": {"chosen_on_valid": {k: v for k, v in pc_choice.items() if k in ("kind", "C", "p")}, "table": pc_table},
        "validation": rows, "deltas": deltas, "by_relation": rel_rows, "by_relation_final": rel_final,
        "train_ctr_by_slot": ctr_slot,
        "importance_gain_pct": {k: v[:20] for k, v in imp.items()}, "sanity": sanity,
        "secs": round(time.time() - t_start, 1),
    }
    out_path.with_suffix(".json").write_text(json.dumps(report, indent=2, default=float), encoding="utf-8")
    print(f"\nSAVED serving model {out_path} (+ {click_file.name}, {buy_file.name}, {out_path.with_suffix('.json').name})")
    return report
