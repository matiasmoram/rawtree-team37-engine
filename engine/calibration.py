"""Probability calibration on observed exposures, never on heuristic ranking scores.

Group corrections use purchase pseudo-counts, minimum support and bounded ratios.
Callers must fit on earlier data and evaluate on a separate untouched interval.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np


def shift_probability(probabilities, shift: float):
    p = np.asarray(probabilities, dtype=float)
    if not math.isfinite(float(shift)) or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("calibration needs finite probabilities in [0,1] and a finite shift")
    p = np.clip(p, 1e-8, 1 - 1e-8)
    z = np.clip(np.log(p / (1 - p)) + float(shift), -35, 35)
    return 1 / (1 + np.exp(-z))


def group_key(subcategory: str, slot: int) -> str:
    return f"{subcategory}|{min(max(int(slot), 0) // 3, 2)}"


def fit_groups(probabilities, labels, subcategories, slots, min_n=200, prior=5.0):
    probabilities, labels, subcategories, slots = map(list, (probabilities, labels, subcategories, slots))
    if len({len(probabilities), len(labels), len(subcategories), len(slots)}) != 1:
        raise ValueError("calibration vectors must have equal length")
    if min_n < 1 or not math.isfinite(prior) or prior <= 0:
        raise ValueError("positive support and prior required")
    if any(not math.isfinite(float(p)) or not 0 <= float(p) <= 1 for p in probabilities):
        raise ValueError("invalid probability")
    if any(y not in (0, 1) for y in labels):
        raise ValueError("labels must be binary")
    totals = {}
    for p, y, sub, slot in zip(probabilities, labels, subcategories, slots):
        key = group_key(str(sub), slot)
        total = totals.setdefault(key, [0, 0.0, 0])
        total[0] += 1
        total[1] += float(p)
        total[2] += int(y)
    return {k: {"multiplier": min(2.0, max(0.5, (y + prior) / (p + prior))),
                "n": n, "expected": p, "observed": y}
            for k, (n, p, y) in totals.items() if n >= min_n}


def group_multipliers(groups, subcategories, slots):
    subcategories, slots = list(subcategories), list(slots)
    if len(subcategories) != len(slots):
        raise ValueError("group vectors must have equal length")
    if not isinstance(groups, dict):
        raise ValueError("groups must be a mapping")
    if any(not isinstance(v, dict) or not math.isfinite(float(v.get("multiplier", 1))) for v in groups.values()):
        raise ValueError("group corrections must be finite mappings")
    return np.array([min(2.0, max(0.5, float(groups.get(group_key(str(sub), slot), {}).get("multiplier", 1.0))))
                     for sub, slot in zip(subcategories, slots)])


class OnlineCalibration:
    """Immutable snapshot loaded outside request handling, for one model fingerprint."""

    def __init__(self, payload=None):
        self.payload = payload or {}

    @classmethod
    def load(cls, path: Path, model_id: str):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("groups", {}), dict):
                return cls()
            if data.get("model_id") != model_id:
                return cls()
            built = float(data.get("built_at", 0))
            if not math.isfinite(built) or built <= 0 or built > time.time() + 5:
                return cls()
            for row in data.get("groups", {}).values():
                if not isinstance(row, dict) or not math.isfinite(float(row["multiplier"])):
                    return cls()
            return cls(data)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return cls()

    def apply(self, p, subcategories, slots, request_epoch):
        p = shift_probability(p, 0)
        if not math.isfinite(float(request_epoch)):
            raise ValueError("request time must be finite")
        built = float(self.payload.get("built_at", 0))
        # Do not use future corrections during replay or a stale feedback regime.
        if not built or built > request_epoch or request_epoch - built > 7200:
            return np.asarray(p)
        return np.clip(np.asarray(p) * group_multipliers(self.payload.get("groups", {}), subcategories, slots),
                       1e-8, 1 - 1e-8)
