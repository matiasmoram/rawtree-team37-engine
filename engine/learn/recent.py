"""Recent-feedback diagnostics and training with an untouched chronological test set.

These are observed-list diagnostics, NOT estimates of the hidden simulator's
expected conversion for arbitrary new recommendation lists.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import log_loss, roc_auc_score

from ..features import FEATURES, FIDX
from ..calibration import (fit_groups as _fit_groups, group_multipliers,
                           shift_probability)
from .dataset import relation

CLIP = 1e-7


def probability_metrics(y, p) -> dict:
    y, p = np.asarray(y, dtype=float), np.clip(np.asarray(p, dtype=float), CLIP, 1 - CLIP)
    return {"rows": int(len(y)), "positives": int(y.sum()),
            "logloss": float(log_loss(y, p, labels=[0, 1])) if len(y) else None,
            "brier": float(np.mean((y - p) ** 2)) if len(y) else None,
            "observed_rate": float(y.mean()) if len(y) else None,
            "predicted_rate": float(p.mean()) if len(y) else None,
            "auc": float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None}


def temporal_split(df: pd.DataFrame, fractions=(0.55, 0.15, 0.15, 0.15)) -> tuple[dict, dict]:
    """Split at distinct request times, never splitting a request or a time tie."""
    if len(fractions) != 4 or any(f <= 0 for f in fractions) or not math.isclose(sum(fractions), 1):
        raise ValueError("four positive fractions must sum to one")
    if df.groupby("request_id")["ts"].nunique().max() != 1:
        raise ValueError("a request has inconsistent timestamps")
    times = df.groupby("request_id")["ts"].first().sort_values(kind="stable")
    if len(times) < 20:
        raise ValueError("at least 20 requests are needed for four partitions")
    cuts = [times.iloc[min(len(times) - 1, max(1, int(len(times) * f)))]
            for f in np.cumsum(fractions)[:-1]]
    if not cuts[0] < cuts[1] < cuts[2]:
        raise ValueError("not enough distinct timestamps for four strict partitions")
    ts = df["ts"]
    masks = {"train": (ts < cuts[0]).to_numpy(),
             "tune": ((ts >= cuts[0]) & (ts < cuts[1])).to_numpy(),
             "calibration": ((ts >= cuts[1]) & (ts < cuts[2])).to_numpy(),
             "test": (ts >= cuts[2]).to_numpy()}
    if any(not m.any() for m in masks.values()):
        raise ValueError("empty chronological partition")
    info = {name: {"requests": int(df.loc[m, "request_id"].nunique()), "rows": int(m.sum()),
                   "purchases": int(df.loc[m, "purchase"].sum()),
                   "clicks": int(df.loc[m, "click"].sum()),
                   "start": str(df.loc[m, "ts"].min()), "end": str(df.loc[m, "ts"].max())}
            for name, m in masks.items()}
    return masks, info


def apply_shift(p, shift: float):
    return shift_probability(p, shift)


def fit_shift(y, p, strength: float = 50.0) -> dict:
    """A shrunk calibration intercept, fitted on a separate partition only.

    A Beta-like prior centred on the base expected rate prevents a calibration
    slice with very few purchases from forcing all probabilities toward zero.
    """
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    if not len(y):
        return {"kind": "logit_shift", "shift": 0.0, "rows": 0, "positives": 0}
    target = (y.sum() + strength * p.mean()) / (len(y) + strength)
    lo, hi = -3.0, 3.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if apply_shift(p, mid).mean() < target:
            lo = mid
        else:
            hi = mid
    return {"kind": "logit_shift", "shift": float((lo + hi) / 2),
            "rows": int(len(y)), "positives": int(y.sum()), "prior_exposures": strength}


def fit_groups(frame: pd.DataFrame, y, p, min_rows: int = 200, prior_expected: float = 5.0) -> dict:
    """Bounded observed/expected residuals by subcategory and position band.

    Expected purchases are probabilities from the already globally calibrated
    model, never uncalibrated heuristic ranking scores. Group support is recorded.
    """
    if "subcategory" not in frame:
        return {}
    return _fit_groups(p, y, frame["subcategory"].astype(str).to_numpy(),
                       frame["slot"].to_numpy(dtype=int), min_n=min_rows, prior=prior_expected)


def apply_calibration(p, calibration: dict, frame: pd.DataFrame | None = None):
    out = apply_shift(p, calibration.get("shift", 0.0))
    groups = calibration.get("groups", {})
    if groups and frame is not None and "subcategory" in frame:
        multipliers = group_multipliers(groups, frame["subcategory"].astype(str), frame["slot"].to_numpy(dtype=int))
        out = np.clip(out * multipliers, CLIP, 1 - CLIP)
    return out


def positive_ranking(frame: pd.DataFrame, scores, label="purchase") -> pd.DataFrame:
    """Ranks of observed positives inside their logged ten-item candidate lists."""
    temp = frame[["request_id", "user_id", "slot", label]].copy()
    temp["score"] = np.asarray(scores)
    temp = temp.sort_values(["request_id", "score", "slot"], ascending=[True, False, True], kind="stable")
    temp["rank"] = temp.groupby("request_id").cumcount() + 1
    pos = temp[temp[label] > 0].copy()
    pos["ndcg"] = 1 / np.log2(pos["rank"] + 1)
    pos["top3"] = (pos["rank"] <= 3).astype(float)
    return pos[["request_id", "user_id", "rank", "ndcg", "top3"]].set_index("request_id").sort_index()


def paired_cluster_interval(values, clusters, n_boot=500, seed=37) -> dict:
    """User-cluster percentile bootstrap for a paired per-request difference."""
    values, clusters = np.asarray(values, dtype=float), np.asarray(clusters)
    if not len(values):
        return {"mean": None, "ci95": [None, None], "requests": 0, "users": 0}
    ids, codes = np.unique(clusters.astype(str), return_inverse=True)
    sums = np.bincount(codes, weights=values)
    sizes = np.bincount(codes)
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n_boot):
        chosen = rng.integers(0, len(ids), size=len(ids))
        samples.append(sums[chosen].sum() / sizes[chosen].sum())
    bounds = np.quantile(samples, [.025, .975]).tolist() if samples else [None, None]
    return {"mean": float(values.mean()), "ci95": bounds,
            "requests": int(len(values)), "users": int(len(ids))}


def slices(frame: pd.DataFrame):
    cold = frame.groupby("request_id")["is_new_item"].transform("max") > 0
    cold = cold | (frame["is_new_user"] > 0)
    if "cold_request" in frame:
        cold = frame["cold_request"].astype(bool)
    bought = (frame["user_bought_n"] > 0) | (frame["bought_in_event"] > 0)
    return {"all": np.ones(len(frame), dtype=bool), "cold_request": np.asarray(cold),
            "new_user": (frame["is_new_user"] > 0).to_numpy(),
            "new_shown_item": (frame["is_new_item"] > 0).to_numpy(),
            "home_page": (frame["page_home"] > 0).to_numpy(),
            "no_session_views": (frame["n_session_views"] == 0).to_numpy(),
            "bought_item": bought.to_numpy(), "not_bought_item": (~bought).to_numpy()}


def _train_models(X, click, purchase, masks):
    params = {"objective": "binary", "metric": "binary_logloss", "learning_rate": .04,
              "feature_fraction": .85, "bagging_fraction": .85, "bagging_freq": 1,
              "lambda_l2": 20., "verbose": -1, "seed": 37, "deterministic": True,
              "force_col_wise": True, "num_threads": 2,
              "monotone_constraints": [-1 if f == "slot" else 0 for f in FEATURES]}
    trained, search = {}, {}
    tr, va = masks["train"], masks["tune"]
    for label, y in (("click", click), ("purchase", purchase)):
        if y[tr].sum() < 10 or y[va].sum() < 3:
            raise ValueError(f"insufficient {label} support in train/tune; do not fit or promote")
        candidates = []
        for leaves, minimum in ((7, 300), (15, 500), (7, 800)):
            cfg = {**params, "num_leaves": leaves, "min_data_in_leaf": minimum}
            model = lgb.train(cfg, lgb.Dataset(X[tr], label=y[tr], feature_name=FEATURES),
                              num_boost_round=600,
                              valid_sets=[lgb.Dataset(X[va], label=y[va], feature_name=FEATURES)],
                              callbacks=[lgb.early_stopping(40, verbose=False)])
            pred = model.predict(X[va], num_threads=2)
            metric = probability_metrics(y[va], pred)
            candidates.append((metric["logloss"], model, {"leaves": leaves, "min_leaf": minimum,
                                                        "iterations": int(model.best_iteration), **metric}))
        candidates.sort(key=lambda x: x[0])
        trained[label] = candidates[0][1]
        search[label] = [x[2] for x in candidates]
    return trained, search


def evaluate_and_train(frame: pd.DataFrame, meta: dict, model_path: Path, report_path: Path,
                       n_boot=500, min_segment_positives=10) -> dict:
    """Fit/select on train+tune only; calibrate on calibration; evaluate test once."""
    started = time.perf_counter()
    frame = frame.sort_values(["ts", "request_id", "slot"], kind="stable").reset_index(drop=True)
    if frame.duplicated(["request_id", "pid"]).any():
        raise ValueError("duplicate request-item rows: attribution join or dataset is invalid")
    if not np.isfinite(frame[FEATURES].to_numpy()).all():
        raise ValueError("non-finite features")
    masks, split_info = temporal_split(frame)
    X = frame[FEATURES].to_numpy(dtype=np.float32)
    yc, yp = frame["click"].to_numpy(), frame["purchase"].to_numpy()
    trained, search = _train_models(X, yc, yp, masks)
    tr, tune, cal, test = (masks[k] for k in ("train", "tune", "calibration", "test"))
    pc = float((yp[tr & (yc == 1)].sum() + 1) / (yc[tr].sum() + 2))
    tune_p = trained["purchase"].predict(X[tune], num_threads=2)
    tune_f = trained["click"].predict(X[tune], num_threads=2) * pc
    # Predeclared choice is likelihood on tuning only, not AUC or test ranking.
    chosen = "purchase" if probability_metrics(yp[tune], tune_p)["logloss"] <= probability_metrics(yp[tune], tune_f)["logloss"] else "factored"
    booster = trained["purchase" if chosen == "purchase" else "click"]
    factor = 1.0 if chosen == "purchase" else pc
    raw_cal = booster.predict(X[cal], num_threads=2) * factor
    calibration = fit_shift(yp[cal], raw_cal)
    calibration["groups"] = fit_groups(frame.loc[cal], yp[cal], apply_shift(raw_cal, calibration["shift"]))
    calibration["fit_start"] = split_info["calibration"]["start"]
    calibration["fit_end"] = split_info["calibration"]["end"]
    calibration["group_key"] = "subcategory|slot_band_0_2_3_5_6_9"
    # All choices are locked before calculating anything on test.
    held = frame.loc[test].copy()
    raw = booster.predict(X[test], num_threads=2) * factor
    p = apply_calibration(raw, calibration, held)
    X0 = X[test].copy()
    X0[:, FIDX["slot"]] = 0
    rank_frame = held.copy()
    rank_frame["slot"] = 0
    scores = apply_calibration(booster.predict(X0, num_threads=2) * factor, calibration, rank_frame)
    rel = relation(X)
    train_rates = pd.DataFrame({"relation": rel[tr], "slot": frame.loc[tr, "slot"].to_numpy(), "y": yp[tr]})
    grouped = train_rates.groupby(["relation", "slot"])["y"].agg(["sum", "count"])
    global_rate = float((yp[tr].sum() + 1) / (tr.sum() + 2))
    grouped["rate"] = (grouped["sum"] + 100 * global_rate) / (grouped["count"] + 100)
    rates = grouped["rate"].to_dict()
    baseline_p = np.array([rates.get((r, s), global_rate) for r, s in zip(rel[test], held["slot"])])
    baseline_s = np.array([rates.get((r, 0.), global_rate) for r in rel[test]])
    segments = {}
    for name, mask in slices(held).items():
        count = int(mask.sum())
        positives = int(yp[test][mask].sum())
        segments[name] = {"requests": int(held.loc[mask, "request_id"].nunique()),
                          "status": "supported" if positives >= min_segment_positives else "insufficient_positives",
                          "calibrated": probability_metrics(yp[test][mask], p[mask]),
                          "raw": probability_metrics(yp[test][mask], raw[mask]),
                          "relation_slot_baseline": probability_metrics(yp[test][mask], baseline_p[mask])} if count else {"status": "empty", "requests": 0}
    ranking, paired = {}, {}
    for label in ("click", "purchase"):
        outputs = {"logged_order": positive_ranking(held, -held["slot"].to_numpy(), label),
                   "relation_baseline": positive_ranking(held, baseline_s, label),
                   "trained": positive_ranking(held, scores, label)}
        ranking[label] = {name: {"positive_requests": int(len(result)),
                                 "ndcg": float(result.ndcg.mean()) if len(result) else None,
                                 "top3": float(result.top3.mean()) if len(result) else None}
                          for name, result in outputs.items()}
        for baseline in ("logged_order", "relation_baseline"):
            joined = outputs["trained"].join(outputs[baseline], lsuffix="_trained", rsuffix="_baseline", how="inner")
            for metric in ("ndcg", "top3"):
                paired[f"{label}_{metric}_vs_{baseline}"] = paired_cluster_interval(
                    joined[f"{metric}_trained"] - joined[f"{metric}_baseline"],
                    joined["user_id_trained"], n_boot=n_boot)
    # This is eligibility for a bounded online trial, not automatic deployment.
    delta = paired["purchase_ndcg_vs_logged_order"]
    enough = delta["requests"] >= 30
    calibration_ok = probability_metrics(yp[test], p)["logloss"] <= probability_metrics(yp[test], baseline_p)["logloss"]
    trial_eligible = bool(enough and calibration_ok and delta["ci95"][0] is not None and delta["ci95"][0] > 0)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(model_path))
    serving = {"kind": chosen, "bought_penalty": 1.0}
    if chosen == "factored":
        serving["pc"] = {"kind": "rate", "p": pc}
    report = {"evaluation_version": "recent_v1", "dataset": meta, "features": list(FEATURES),
              "partitions": split_info, "selection": {"criterion": "tuning purchase logloss", "kind": chosen, "search": search},
              "serving": serving, "calibration": calibration, "test_segments": segments,
              "test_ranking": ranking, "paired_user_bootstrap": paired,
              "online_trial_eligible": trial_eligible,
              "deployment": "not deployed; eligibility requires separate live ownership, latency and validity checks",
              "limitations": ["Observed-list outcomes are selected by the logging policy; ranking positives is position-biased.",
                              "No propensities exist for historical deterministic lists; no IPS/off-policy value is claimed.",
                              "No held-out outcome can score products that were never shown.",
                              "This is NOT hidden-simulator expected conversion and cannot alone prove an online winner.",
                              "User/item counters remain frozen at interval start; catalogue and recent buys are replayed point-in-time.",
                              "Only fulfilled/mature feedback appears; see coverage audit for missing requests.",
                              "The holdout is used once in this report; repeated development on it invalidates an untouched-test claim."],
              "secs": round(time.perf_counter() - started, 2)}
    sidecar = model_path.with_suffix(".json")
    sidecar.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


def benchmark_serving(model_path: str, n_requests=100, wait_seconds=45) -> dict:
    """Prospective, read-only serving benchmark; requests must postdate the snapshot.

    No feedback outcomes are read and no recommendations are submitted. This
    checks execution/validity, never conversion uplift.
    """
    from datetime import datetime, timezone
    from ..calibration import group_multipliers
    from ..live import POLL_SQL
    from ..policies.lgbm import LgbmPolicy
    from ..policies.prepare import prepare_snapshot
    from ..rt import RawTree
    from ..snapshot import apply_delta, build_snapshot, latest_cached
    from ..types import Request, sql_ts
    from .dataset import CatalogReplay, UPDATES_SQL

    rt = RawTree(timeout=90)
    snap = latest_cached()
    if snap is None:
        snap = build_snapshot(rt)
    else:
        apply_delta(rt, snap)
    asof = snap.T
    prepare_snapshot(snap)
    policy = LgbmPolicy("recent-benchmark", model_path, bought_penalty=1., num_threads=2, use_content=True)
    deadline = time.monotonic() + wait_seconds
    gathered = {}
    while len(gathered) < n_requests and time.monotonic() < deadline:
        for row in rt.query(POLL_SQL.format(since=sql_ts(asof)), timeout=10):
            req = Request.from_row(row)
            if req.ts > asof:
                gathered[req.request_id] = req
        if len(gathered) < n_requests:
            time.sleep(1)
    requests = sorted(gathered.values(), key=lambda r: (r.ts, r.request_id))[:n_requests]
    if not requests:
        raise ValueError("no fresh requests after snapshot cutoff; no prospective benchmark available")
    updates = rt.query(UPDATES_SQL.format(lo=sql_ts(asof), hi=sql_ts(requests[-1].ts)), timeout=30)
    replay = CatalogReplay(snap, updates)
    snap.products = replay.products
    total_ms, recommend_ms, candidates, invalid = [], [], [], []
    parity_max = 0.
    policy.recommend(requests[0], snap)  # warm up native inference outside timing
    from ..features import build_context, featurize
    for req in requests:
        replay.advance(req.ts)
        started = time.perf_counter()
        items = policy.recommend(req, snap)
        rank_finished = time.perf_counter()
        metadata = policy.exposure_metadata(req, snap, items)
        finished = time.perf_counter()
        recommend_ms.append(1000 * (rank_finished - started))
        total_ms.append(1000 * (finished - started))
        if len(items) != 10 or len(set(items)) != 10 or not all(snap.is_valid(pid) for pid in items):
            invalid.append(req.request_id)
        X = featurize(build_context(req, snap), snap, items, slots=list(range(len(items))))
        expected = np.clip(policy.model.score(X) * group_multipliers(
            policy.model.meta.get("calibration", {}).get("groups", {}),
            [snap.products[pid].sub for pid in items], list(range(len(items)))), 1e-8, 1 - 1e-8)
        parity_max = max(parity_max, float(np.max(np.abs(expected - metadata["base_probabilities"]))))
        candidates.append(len(policy.score_candidates(req, snap)[0]))
    report = {"snapshot_cutoff": asof.isoformat(), "request_start": requests[0].ts.isoformat(),
              "request_end": requests[-1].ts.isoformat(), "requests": len(requests), "target_requests": n_requests,
              "all_requests_strictly_after_snapshot": all(req.ts > asof for req in requests),
              "invalid_requests": invalid,
              "ranking_ms": {"p50": float(np.percentile(recommend_ms, 50)), "p95": float(np.percentile(recommend_ms, 95)), "max": max(recommend_ms)},
              "rank_and_metadata_ms": {"p50": float(np.percentile(total_ms, 50)), "p95": float(np.percentile(total_ms, 95)), "max": max(total_ms)},
              "candidates": {"p50": float(np.median(candidates)), "max": max(candidates)},
              "base_probability_serving_parity_max_abs_error": parity_max,
              "bounded_trial_execution_ready": bool(not invalid and parity_max < 1e-12 and np.percentile(total_ms, 95) < 100),
              "limitations": "Local rank/metadata latency excludes network polling/submission and is not an outcome or reliability score; catalog replay is point-in-time; no new model-quality evidence."}
    return report
