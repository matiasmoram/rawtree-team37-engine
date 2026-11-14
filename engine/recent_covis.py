"""Bounded recent session co-visitation, built outside the serving process.

All queries use [as_of-window, as_of), aggregate each session/product before the
join and cap the number of items per session. The information cutoff is explicit;
future-built matrices are rejected by historical consumers.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import CACHE
from .rt import RawTree
from .types import sql_ts


@dataclass(frozen=True)
class RecentCovisIndex:
    built_at: datetime | None = None
    vv: dict[str, tuple[tuple[str, float], ...]] = field(default_factory=dict)
    vb: dict[str, tuple[tuple[str, float], ...]] = field(default_factory=dict)
    max_age_hours: float = 12.0

    @classmethod
    def load(cls, path: str | Path | None = None) -> "RecentCovisIndex":
        path = Path(path) if path is not None else CACHE / "recent_covis.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") != 1:
                return cls()
            cutoff = datetime.fromisoformat(str(data["as_of"]).replace("Z", "+00:00"))
            if cutoff.tzinfo is None:
                return cls()
            cutoff = cutoff.astimezone(timezone.utc)
            def matrix(raw):
                result = {}
                for pid, rows in raw.items():
                    valid = {}
                    for q, weight in rows:
                        weight = float(weight)
                        if isinstance(q, str) and q != pid and math.isfinite(weight) and weight > 0:
                            valid[q] = max(valid.get(q, 0.0), weight)
                    if valid:
                        result[pid] = tuple(sorted(valid.items(), key=lambda x: (-x[1], x[0]))[:40])
                return result
            return cls(cutoff, matrix(data.get("vv", {})), matrix(data.get("vb", {})))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return cls()

    def usable_at(self, ts: datetime) -> bool:
        return bool(self.built_at is not None and
                    0 <= (ts - self.built_at).total_seconds() <= self.max_age_hours * 3600)

    def candidates(self, viewed: list[str], as_of: datetime) -> dict[str, float]:
        if not self.usable_at(as_of):
            return {}
        scores: dict[str, float] = {}
        for rank, pid in enumerate(viewed[:4]):
            for matrix, gain in ((self.vb, 1.0), (self.vv, 0.5)):
                rows = matrix.get(pid, ())[:25]
                denom = rows[0][1] if rows else 1.0
                for q, weight in rows:
                    value = gain * (0.7 ** rank) * min(1.0, weight / denom)
                    scores[q] = max(scores.get(q, 0.0), value)
        return dict(sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:80])


def build_recent_covis(rt: RawTree, as_of: datetime, window_hours: float = 6.0,
                       half_life_hours: float = 6.0, top: int = 40,
                       session_cap: int = 40) -> dict:
    if as_of.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    if not 0 < window_hours <= 24 or not 0 < half_life_hours <= 168:
        raise ValueError("invalid bounded co-visitation window/half-life")
    if not 1 <= top <= 40 or not 2 <= session_cap <= 100:
        raise ValueError("invalid co-visitation top/session cap")
    as_of = as_of.astimezone(timezone.utc)
    start = as_of - timedelta(hours=window_hours)
    def grouped(event):
        return ("(SELECT session_id::String AS sid, product_id::String AS pid, "
                "min(ts::DateTime64(3)) AS first_t, max(ts::DateTime64(3)) AS last_t "
                f"FROM shop.events WHERE event_type::String = '{event}' "
                "AND session_id::String != '' AND product_id::String != '' "
                f"AND ts::DateTime64(3) >= '{sql_ts(start)}' AND ts::DateTime64(3) < '{sql_ts(as_of)}' "
                f"GROUP BY sid, pid ORDER BY sid, last_t DESC, pid LIMIT {session_cap} BY sid)")
    views, purchases = grouped("view"), grouped("purchase")
    out = {}
    for kind, targets in (("vv", views), ("vb", purchases)):
        chronology = "AND a.first_t <= b.first_t" if kind == "vb" else ""
        sql = f"""
        SELECT src_id, dst_id, weight FROM (
          SELECT a.pid AS src_id, b.pid AS dst_id,
                 sum(exp2(-dateDiff('second', greatest(a.last_t, b.last_t),
                                  toDateTime64('{sql_ts(as_of)}', 3)) / {half_life_hours * 3600.0})) AS weight
          FROM {views} AS a INNER JOIN {targets} AS b ON a.sid = b.sid
          WHERE a.pid != b.pid {chronology} GROUP BY src_id, dst_id
        ) ORDER BY src_id, weight DESC, dst_id LIMIT {top} BY src_id
        SETTINGS max_execution_time = 90, max_threads = 2
        """
        rows = rt.query(sql, timeout=100, retries=0)
        matrix: dict[str, list[list]] = {}
        for row in rows:
            matrix.setdefault(row["src_id"], []).append([row["dst_id"], float(row["weight"])])
        out[kind] = matrix
    return {"version": 1, "as_of": as_of.isoformat(), "window_start": start.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_hours": window_hours, "half_life_hours": half_life_hours,
            "top": top, "session_cap": session_cap, **out}


def save_recent_covis(payload: dict, path: str | Path | None = None) -> Path:
    path = Path(path) if path is not None else CACHE / "recent_covis.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    temp.replace(path)
    return path
