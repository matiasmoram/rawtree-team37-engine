"""Ratio metrics, paired Poisson bootstrap and result rows.

Every metric is a ratio estimator ``sum(num) / sum(den)`` over a policy-independent population of cases:

* plain means (hit rates, recall, NDCG-like scores): ``den = 1``;
* SNIPS: ``num = w * r``, ``den = w`` (importance weights, optionally times sampling design weights).

CIs use the Poisson bootstrap: each replicate gives every case an i.i.d. Poisson(1) weight. It approximates the
multinomial bootstrap for large n, handles design weights folded into num/den, and is vectorised (one matrix product
per replicate block). The same replicate weights are applied to every policy, so the CI of the relative lift vs the
baseline is a *paired* CI: it accounts for both policies being scored on the very same cases.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np

BASELINE = "ref-global-bestsellers"


@dataclass
class Metric:
    """``values[policy] = (num, den)`` full-length arrays; ``pop`` selects the cases the metric is defined on."""
    name: str
    pop: np.ndarray
    values: dict[str, tuple[np.ndarray, np.ndarray]]
    main: bool = False
    lift: bool = True  # emit <name>_lift rows vs the baseline (off for diagnostics where a ratio is meaningless)


@dataclass
class Row:
    evaluator: str
    policy: str
    segment: str
    metric: str
    value: float
    ci_low: float | None
    ci_high: float | None
    n: int

    def as_dict(self) -> dict:
        def clean(x):
            if x is None:
                return None
            x = float(x)
            return None if math.isnan(x) or math.isinf(x) else x
        return {"evaluator": self.evaluator, "policy": self.policy, "segment": self.segment, "metric": self.metric,
                "value": clean(self.value), "ci_low": clean(self.ci_low), "ci_high": clean(self.ci_high), "n": int(self.n)}


def _ratio(num: float, den: float) -> float:
    return num / den if den > 0 else float("nan")


def poisson_bootstrap(arrays: Mapping[str, tuple[np.ndarray, np.ndarray]], n_boot: int, rng: np.random.Generator,
                      max_cells: int = 4_000_000) -> dict[str, np.ndarray]:
    """Replicates of sum(W*num)/sum(W*den) per key with shared Poisson(1) weights W (paired across keys)."""
    n = len(next(iter(arrays.values()))[0])
    chunk = max(1, max_cells // max(n, 1))
    reps: dict[str, list[np.ndarray]] = {k: [] for k in arrays}
    done = 0
    while done < n_boot:
        b = min(chunk, n_boot - done)
        W = rng.poisson(1.0, size=(b, n)).astype(np.float64)
        for k, (num, den) in arrays.items():
            with np.errstate(divide="ignore", invalid="ignore"):
                reps[k].append((W @ num) / (W @ den))
        done += b
    return {k: np.concatenate(v) for k, v in reps.items()}


def percentile_ci(reps: np.ndarray | None, level: float = 0.95) -> tuple[float, float]:
    if reps is None:
        return float("nan"), float("nan")
    reps = reps[np.isfinite(reps)]
    if len(reps) < 10:
        return float("nan"), float("nan")
    a = (1 - level) / 2 * 100
    lo, hi = np.percentile(reps, [a, 100 - a])
    return float(lo), float(hi)


def summarize(evaluator: str, metrics: list[Metric], segments: Mapping[str, np.ndarray],
              baseline: str = BASELINE, n_boot: int = 500, seed: int = 0) -> list[Row]:
    """Point estimate, 95% CI and n per (segment, metric, policy), plus ``<metric>_lift`` rows vs ``baseline``.

    Lift = value / baseline_value - 1 on the same cases, with a paired bootstrap CI.
    """
    rng = np.random.default_rng(seed)
    rows: list[Row] = []
    for seg_name, seg in segments.items():
        for m in metrics:
            idx = np.flatnonzero(m.pop & seg)
            n = len(idx)
            sub = {p: (num[idx].astype(np.float64), den[idx].astype(np.float64)) for p, (num, den) in m.values.items()}
            point = {p: _ratio(num.sum(), den.sum()) for p, (num, den) in sub.items()}
            reps = poisson_bootstrap(sub, n_boot, rng) if n > 0 and n_boot > 0 else {}
            for p in m.values:
                lo, hi = percentile_ci(reps.get(p))
                rows.append(Row(evaluator, p, seg_name, m.name, point[p], lo, hi, n))
            if not m.lift or baseline not in m.values:
                continue
            base = point[baseline]
            for p in m.values:
                if p == baseline:
                    continue
                lift = point[p] / base - 1 if base > 0 else float("nan")
                lift_reps = None
                if reps:
                    with np.errstate(divide="ignore", invalid="ignore"):
                        lift_reps = reps[p] / reps[baseline] - 1
                lo, hi = percentile_ci(lift_reps)
                rows.append(Row(evaluator, p, seg_name, f"{m.name}_lift", lift, lo, hi, n))
    return rows
