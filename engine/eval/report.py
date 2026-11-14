"""Console tables and JSON-lines output for evaluator reports."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .common import SEGMENTS, Report
from .stats import BASELINE, Row


def _fmt(x: float | None, pct: bool = False) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "nan"
    return f"{x * 100:+.0f}%" if pct else f"{x:.4f}"


def format_report(rep: Report) -> str:
    """One block per (evaluator, metric): rows = segments, columns = policy value [95% CI] and lift vs baseline."""
    lines = [f"== {rep.evaluator}  load {rep.secs.get('load')}s  score {rep.secs.get('score')}s",
             "   info: " + ", ".join(f"{k}={v}" for k, v in rep.info.items())]
    for p, r in rep.policy_runs.items():
        lines.append(f"   policy {p}: {r['ms_per_call']} ms/call, invalid answers {r['invalid']}")
    by_key: dict[tuple[str, str], dict[str, dict[str, Row]]] = defaultdict(lambda: defaultdict(dict))
    for row in rep.rows:
        if row.metric.endswith("_lift"):
            by_key[(row.evaluator, row.metric[:-5])][row.segment][row.policy + "|lift"] = row
        else:
            by_key[(row.evaluator, row.metric)][row.segment][row.policy] = row
    for (ev, metric), segs in by_key.items():
        policies = []
        for seg_rows in segs.values():
            for k in seg_rows:
                if "|" not in k and k not in policies:
                    policies.append(k)
        policies.sort(key=lambda p: (p != BASELINE, p))
        lines.append(f"-- {ev} / {metric}")
        lines.append(f"   {'segment':<14}{'n':>8}  " + "".join(f"{p[:34]:<46}" for p in policies))
        for seg in SEGMENTS:
            if seg not in segs:
                continue
            seg_rows = segs[seg]
            n = next(iter(seg_rows.values())).n
            cells = []
            for p in policies:
                r = seg_rows.get(p)
                if r is None:
                    cells.append(f"{'':<46}")
                    continue
                cell = _fmt(r.value) if r.ci_low is None else f"{_fmt(r.value)} [{_fmt(r.ci_low)},{_fmt(r.ci_high)}]"
                lift = seg_rows.get(p + "|lift")
                if lift is not None:
                    cell += f" {_fmt(lift.value, True)} [{_fmt(lift.ci_low, True)},{_fmt(lift.ci_high, True)}]"
                cells.append(f"{cell:<46}")
            lines.append(f"   {seg:<14}{n:>8}  " + "".join(cells))
    return "\n".join(lines)


def append_jsonl(path: Path, reports: list[Report], T: datetime, window_hours: float) -> int:
    """Append one JSON line per result row: timestamp, T, window, evaluator, policy, segment, metric, value, CI, n."""
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    with path.open("a", encoding="utf-8") as f:
        for rep in reports:
            for row in rep.rows:
                rec = {"timestamp": stamp, "T": T.isoformat(), "window": window_hours, **row.as_dict()}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1
    return n
