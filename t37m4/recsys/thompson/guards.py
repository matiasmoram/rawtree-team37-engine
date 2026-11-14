"""Request ownership (engine contract), double-writer check and the unattended performance guard."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import pandas as pd

STATE_URL = "https://datathon.rawtree.dev/api/state"

# Last 5 min of our team's submissions (request_id, model_version); rows joined to shop.requests for the time bound.
COLLISION_SQL = """
SELECT s.request_id request_id, s.mv mv FROM
 (SELECT request_id::String request_id, model_version::String mv FROM {team}.submissions
  WHERE request_id::String != '__init__') s
INNER JOIN (SELECT request_id::String request_id FROM shop.requests WHERE ts > now64(3) - INTERVAL 5 MINUTE) r
ON r.request_id = s.request_id"""


def owns(request_id: str, shard: int = 1, count: int = 2) -> bool:
    """Same contract as rawtree-team37-engine engine/experiments.py request_bucket()."""
    return int(hashlib.md5(str(request_id).encode()).hexdigest()[:8], 16) % count == shard


def collision_rate(sub_rows: pd.DataFrame, version: str) -> float:
    """Among requests `version` answered, the share that another model_version also answered."""
    if not len(sub_rows):
        return 0.0
    ours = set(sub_rows.request_id[sub_rows.mv == version])
    if not ours:
        return 0.0
    others = set(sub_rows.request_id[(sub_rows.mv != version) & sub_rows.request_id.isin(ours)])
    return len(others) / len(ours)


def foreign_on_our_shard(sub_rows: pd.DataFrame, version: str, shard: int = 1, count: int = 2) -> float:
    """Before we start: share of our-shard requests already answered by another version (teammate not on shard 0)."""
    if not len(sub_rows):
        return 0.0
    mine = sub_rows[[owns(r, shard, count) for r in sub_rows.request_id]]
    if not len(mine):
        return 0.0
    return float((mine.mv != version).groupby(mine.request_id).any().mean())


class PerfGuard:
    """Two consecutive losing windows -> 'reset' (first time) -> two more -> 'stop'."""

    def __init__(self, min_requests: int = 300, margin: float = 0.1):
        self.min_requests, self.margin = min_requests, margin
        self.losses = 0
        self.resets = 0

    def observe(self, ours: float, ctrl: float, n_ours: int) -> str:
        if n_ours < self.min_requests:
            return "ok"
        if ours >= ctrl * (1 - self.margin):     # a loss must be clear, not noise
            self.losses = 0
            return "ok"
        self.losses += 1
        if self.losses < 2:
            return "ok"
        self.losses = 0
        self.resets += 1
        return "reset" if self.resets == 1 else "stop"


@dataclass
class Window:
    ours: float
    ctrl: float
    n_ours: int
    ctrl_version: str
    ours_cold: float | None = None
    on_time: float | None = None


def parse_state(j: dict, version: str, team: str, min_requests: int = 300, control: str | None = None) -> Window | None:
    """control: the engine arm to compare against; None -> best other version (noisier, biased against us)."""
    for t in j.get("teams", []):
        if t.get("team_id") != team:
            continue
        vs = t.get("versions", [])
        mine = [v for v in vs if v.get("model_version") == version]
        others = [v for v in vs if v.get("model_version") != version and v.get("requests", 0) >= min_requests
                  and (control is None or v.get("model_version") == control)]
        if not mine or not others:
            return None
        c = max(others, key=lambda v: v.get("conversion", 0))
        m = mine[0]
        return Window(m["conversion"], c["conversion"], int(m["requests"]), c["model_version"],
                      m.get("cold_conversion"), t.get("on_time"))
    return None


def fetch_state(minutes: int = 30, end: float | None = None) -> dict:
    import requests
    end = int(end or time.time()) // 300 * 300
    r = requests.get(STATE_URL, params={"by": "model", "from": end - 60 * minutes, "to": end}, timeout=20)
    r.raise_for_status()
    return r.json()


def leaderboard_window(version: str, team: str, minutes: int = 30, control: str | None = None) -> Window | None:
    try:
        return parse_state(fetch_state(minutes), version, team, control=control)
    except Exception as e:
        print("guard: leaderboard fetch failed:", str(e)[:120], flush=True)
        return None
