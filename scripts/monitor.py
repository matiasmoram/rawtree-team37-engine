"""Continuously log live leaderboard state and our feedback metrics to CSV.

Run from project root:
    .venv/Scripts/python.exe scripts/monitor.py [--interval 300] [--minutes 60] [--once]
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import LOGS, TEAM  # noqa: E402  (loads .env, creates logs/)
from engine.rt import RawTree  # noqa: E402

STATE_URL = "https://datathon.rawtree.dev/api/state"
LEADERBOARD_CSV = LOGS / "leaderboard.csv"
FEEDBACK_CSV = LOGS / "feedback.csv"
Z95 = 1.959963984540054

LEADERBOARD_FIELDS = [
    "fetched_at", "mode", "updated_at", "window_start", "window_end",
    "team_id", "requests", "conversion", "cold_conversion", "on_time",
    "revenue_per_request", "model_version",
    "baseline_conversion", "baseline_cold_conversion", "baseline_revenue_per_request",
    "reference_conversion", "reference_cold_conversion", "reference_revenue_per_request",
    "rank", "n_teams", "progress_latest",
]

FEEDBACK_FIELDS = [
    "fetched_at", "minutes", "model_version",
    "requests", "served_team", "late", "invalid", "missing", "clicks", "purchases", "revenue",
    "p50_ms", "p95_ms", "conv_per100", "conv_lo", "conv_hi", "ctr_per100",
    "revenue_per_request", "on_time_share",
]

FEEDBACK_SQL = """
SELECT s.mv AS model_version, count() AS requests,
       countIf(f.sb = 'team') AS served_team, countIf(f.fr = 'late') AS late, countIf(f.fr = 'invalid') AS invalid, countIf(f.fr = 'missing') AS missing,
       countIf(f.clk != '') AS clicks, countIf(f.pur != '') AS purchases, sum(f.rev) AS revenue,
       quantile(0.5)(f.lat) AS p50_ms, quantile(0.95)(f.lat) AS p95_ms
FROM (SELECT request_id::String AS rid, served_by::String AS sb, fallback_reason::String AS fr, clicked::String AS clk, purchased::String AS pur,
             revenue_eur::Float64 AS rev, latency_ms::Float64 AS lat FROM {team}.feedback
      WHERE request_id::String != '__init__' AND ts::DateTime64(3) > now() - INTERVAL {minutes} MINUTE) AS f
LEFT JOIN (SELECT request_id::String AS rid, any(model_version::String) AS mv FROM {team}.submissions GROUP BY rid) AS s ON s.rid = f.rid
GROUP BY model_version ORDER BY requests DESC
"""


def fmt(v, digits=2):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def wilson_95(k: int, n: int) -> tuple[float | None, float | None]:
    """95% Wilson score interval for k successes out of n, returned in per-100 units."""
    if n <= 0:
        return None, None
    p = k / n
    denom = 1 + Z95 * Z95 / n
    center = (p + Z95 * Z95 / (2 * n)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / n + Z95 * Z95 / (4 * n * n)) / denom
    return max(0.0, center - half) * 100, min(1.0, center + half) * 100


def check_header(path: Path, fieldnames: list[str]) -> None:
    with open(path, "r", newline="", encoding="utf-8") as f:
        existing = next(csv.reader(f), None)
    if existing != fieldnames:
        raise RuntimeError(f"{path.name} header differs from expected columns; move the file aside and rerun")


def append_rows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    exists = path.exists() and path.stat().st_size > 0
    if exists:
        check_header(path, fieldnames)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerows(rows)


def last_logged_updated_at(path: Path) -> str | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    last = None
    with open(path, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            last = row.get("updated_at")
    return last


def fetch_state() -> dict:
    r = requests.get(STATE_URL, timeout=30)
    r.raise_for_status()
    return r.json()


def build_leaderboard_row(state: dict, fetched_at: str) -> dict:
    teams = state.get("teams") or []
    ours = next((t for t in teams if str(t.get("team_id")) == TEAM), {})

    ranked = sorted(
        (t for t in teams if t.get("conversion") is not None),
        key=lambda t: float(t["conversion"]),
        reverse=True,
    )
    rank = next((i + 1 for i, t in enumerate(ranked) if str(t.get("team_id")) == TEAM), None)

    window = state.get("window") or [None, None]
    base = state.get("baseline") or {}
    ref = state.get("reference") or {}
    series = (state.get("progress") or {}).get(TEAM) or []
    progress_latest = max(series, key=lambda p: p[0])[1] if series else None

    return {
        "fetched_at": fetched_at,
        "mode": state.get("mode"),
        "updated_at": state.get("updated_at"),
        "window_start": window[0],
        "window_end": window[1],
        "team_id": TEAM,
        "requests": ours.get("requests"),
        "conversion": ours.get("conversion"),
        "cold_conversion": ours.get("cold_conversion"),
        "on_time": ours.get("on_time"),
        "revenue_per_request": ours.get("revenue_per_request"),
        "model_version": ours.get("model_version"),
        "baseline_conversion": base.get("conversion"),
        "baseline_cold_conversion": base.get("cold_conversion"),
        "baseline_revenue_per_request": base.get("revenue_per_request"),
        "reference_conversion": ref.get("conversion"),
        "reference_cold_conversion": ref.get("cold_conversion"),
        "reference_revenue_per_request": ref.get("revenue_per_request"),
        "rank": rank,
        "n_teams": len(teams),
        "progress_latest": progress_latest,
    }


def build_feedback_row(r: dict, fetched_at: str, minutes: int) -> dict:
    req = int(r.get("requests") or 0)
    served = int(r.get("served_team") or 0)
    clicks = int(r.get("clicks") or 0)
    purchases = int(r.get("purchases") or 0)
    revenue = float(r.get("revenue") or 0)
    lo, hi = wilson_95(purchases, req)
    return {
        "fetched_at": fetched_at,
        "minutes": minutes,
        "model_version": r.get("model_version") or "",
        "requests": req,
        "served_team": served,
        "late": r.get("late"),
        "invalid": r.get("invalid"),
        "missing": r.get("missing"),
        "clicks": clicks,
        "purchases": purchases,
        "revenue": revenue,
        "p50_ms": r.get("p50_ms"),
        "p95_ms": r.get("p95_ms"),
        "conv_per100": purchases / req * 100 if req else None,
        "conv_lo": lo,
        "conv_hi": hi,
        "ctr_per100": clicks / req * 100 if req else None,
        "revenue_per_request": revenue / req if req else None,
        "on_time_share": served / req if req else None,
    }


def print_leaderboard(row: dict, appended: bool) -> None:
    now = datetime.now().strftime("%H:%M:%S")
    print(
        f"[{now}] LEADERBOARD mode={fmt(row['mode'])} updated={fmt(row['updated_at'])} "
        f"| ours conv={fmt(row['conversion'], 4)} cold={fmt(row['cold_conversion'], 4)} "
        f"| baseline conv={fmt(row['baseline_conversion'], 4)} "
        f"| reference conv={fmt(row['reference_conversion'], 4)} "
        f"| rank {fmt(row['rank'])}/{fmt(row['n_teams'])} "
        f"| on_time={fmt(row['on_time'], 4)} "
        f"| progress={fmt(row['progress_latest'], 4)} "
        f"| {'appended' if appended else 'unchanged, not logged'}"
    )


def print_feedback(rows: list[dict]) -> None:
    if not rows:
        print("  (no feedback rows in window)")
        return
    for r in rows:
        mv = r["model_version"] or "(no-submission)"
        print(
            f"  mv={mv} req={r['requests']} conv/100={fmt(r['conv_per100'])} "
            f"[{fmt(r['conv_lo'])},{fmt(r['conv_hi'])}] ctr/100={fmt(r['ctr_per100'])} "
            f"rev/req={fmt(r['revenue_per_request'], 4)} on_time={fmt(r['on_time_share'], 3)} "
            f"late={r['late']} invalid={r['invalid']} missing={r['missing']} "
            f"p95_ms={fmt(r['p95_ms'], 1)}"
        )


def run_leaderboard(fetched_at: str) -> None:
    try:
        state = fetch_state()
        row = build_leaderboard_row(state, fetched_at)
        last = last_logged_updated_at(LEADERBOARD_CSV)
        appended = str(row["updated_at"]) != str(last)
        if appended:
            append_rows(LEADERBOARD_CSV, LEADERBOARD_FIELDS, [row])
        print_leaderboard(row, appended)
    except Exception as e:  # keep the loop alive
        print(f"[leaderboard] ERROR: {type(e).__name__}: {e}", file=sys.stderr)


def run_feedback(client: RawTree, fetched_at: str, minutes: int) -> None:
    try:
        sql = FEEDBACK_SQL.format(team=TEAM, minutes=minutes)
        rows = [build_feedback_row(r, fetched_at, minutes) for r in client.query(sql)]
        append_rows(FEEDBACK_CSV, FEEDBACK_FIELDS, rows)
        print_feedback(rows)
    except Exception as e:  # keep the loop alive
        print(f"[feedback] ERROR: {type(e).__name__}: {e}", file=sys.stderr)


def iteration(client: RawTree, minutes: int) -> None:
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_leaderboard(fetched_at)
    run_feedback(client, fetched_at, minutes)


def main() -> int:
    ap = argparse.ArgumentParser(description="Log leaderboard + feedback metrics to CSV.")
    ap.add_argument("--interval", type=float, default=300.0, help="seconds between iterations (default 300)")
    ap.add_argument("--minutes", type=int, default=60, help="feedback look-back window in minutes (default 60)")
    ap.add_argument("--once", action="store_true", help="run a single iteration and exit")
    args = ap.parse_args()
    if args.interval <= 0 or args.minutes <= 0:
        ap.error("--interval and --minutes must be positive")

    client = RawTree()
    try:
        while True:
            iteration(client, args.minutes)
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
