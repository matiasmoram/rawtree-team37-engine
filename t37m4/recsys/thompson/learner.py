"""Initial fit and online learner: mature team_37.feedback rows -> posterior updates every ~2 min.

    python -m recsys.thompson.learner --init     # fit the starting posterior on all feedback so far
"""
from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .features import BUY_FEATURES, CLICK_FEATURES, Req, buy_matrix, click_matrix
from .model import Posterior

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models" / "thompson"

FEEDBACK_SQL = """
SELECT f.request_id request_id, toString(r.ts) ts_s, r.user_id user_id, r.is_new_user is_new_user,
       r.context context, r.recent_views recent_views, f.shown shown, f.clicked clicked, f.purchased purchased,
       f.served_by served_by
FROM (SELECT request_id::String request_id, shown, clicked::String clicked, purchased::String purchased,
             served_by::String served_by FROM {team}.feedback WHERE request_id::String != '__init__') f
INNER JOIN (SELECT request_id::String request_id, ts, user_id::String user_id, is_new_user::Bool is_new_user,
                   context, recent_views FROM shop.requests
            WHERE ts >= toDateTime('{mark19}') AND toString(ts) > '{mark}'
              AND ts <= now64(3) - INTERVAL {mature} SECOND) r
ON r.request_id = f.request_id"""


@dataclass
class Training:
    Xc: np.ndarray
    yc: np.ndarray
    items: np.ndarray
    Xb: np.ndarray
    yb: np.ndarray


def rows_to_training(st, rows: pd.DataFrame) -> Training:
    Xc, yc, it, Xb, yb = [], [], [], [], []
    for r in rows.to_dict("records"):
        shown = r.get("shown")
        if shown is None or len(shown) == 0:
            continue
        try:
            req = Req.from_row(r, st, served_by_fallback=(r.get("served_by") == "fallback"))
        except Exception:
            continue
        ban = st.bought_before(req.user_id, req.ts)
        idx, slots = [], []
        for s, p in enumerate(shown, start=1):
            i = st.pid2i.get(p)
            if i is None or i in ban:
                continue
            idx.append(i); slots.append(s)
        if not idx:
            continue
        idx = np.array(idx); slots = np.array(slots)
        clicked = st.pid2i.get(r.get("clicked") or "", -1)
        purchased = st.pid2i.get(r.get("purchased") or "", -1)
        Xc.append(click_matrix(st, req, idx, slots)); yc.append((idx == clicked).astype(float)); it.append(idx)
        if clicked in idx:
            Xb.append(buy_matrix(st, req, np.array([clicked]))); yb.append([float(purchased == clicked)])
    if not Xc:
        return Training(np.zeros((0, len(CLICK_FEATURES))), np.zeros(0), np.zeros(0, int),
                        np.zeros((0, len(BUY_FEATURES))), np.zeros(0))
    return Training(np.vstack(Xc), np.concatenate(yc), np.concatenate(it),
                    np.vstack(Xb) if Xb else np.zeros((0, len(BUY_FEATURES))),
                    np.concatenate(yb) if yb else np.zeros(0))


def _update(post: Posterior, tr: Training, fresh: bool = False) -> bool:
    ok = True
    if fresh:
        ok &= post.click.fit(tr.Xc, tr.yc)
        ok &= post.items.update(tr.items, tr.Xc @ post.click.m, tr.yc)
        ok &= post.click.fit(tr.Xc, tr.yc, offset=post.items.mean(tr.items))
        ok &= post.buy.fit(tr.Xb, tr.yb)
        return bool(ok)
    ok &= post.click.update(tr.Xc, tr.yc, offset=post.items.mean(tr.items))
    ok &= post.items.update(tr.items, tr.Xc @ post.click.m, tr.yc)
    ok &= post.buy.update(tr.Xb, tr.yb)
    return bool(ok)


def initial_fit(st, rows: pd.DataFrame) -> Posterior:
    post = Posterior.new(len(CLICK_FEATURES), len(BUY_FEATURES))
    tr = rows_to_training(st, rows)
    if not _update(post, tr, fresh=True):
        raise RuntimeError("initial fit produced non-finite weights")
    post.set_anchor()
    post.init_items = dict(post.items.m), dict(post.items.q)
    return post


class Learner:
    def __init__(self, st, post: Posterior, path: Path = MODELS, half_life_h: float = 3.0, every_s: float = 120,
                 mature_s: int = 540, clip_k: float = 4.0):
        self.st, self.path = st, Path(path)
        self._post = post
        self.init = post.copy()
        self.half_life_h, self.every_s, self.mature_s, self.clip_k = half_life_h, every_s, mature_s, clip_k
        self.lock = threading.Lock()
        self.last_step = time.time()
        self.mark = getattr(post, "mark", None) or pd.Timestamp.utcnow().tz_localize(None).strftime("%Y-%m-%d %H:%M:%S.%f")
        self.history: list[dict] = []

    def current(self) -> Posterior:
        return self._post

    def reset_to_anchor(self):
        with self.lock:
            p = self.init.copy()
            p.click, p.buy = p.anchor[0].copy(), p.anchor[1].copy()
            p.items.m, p.items.q = {}, {}
            p.version = self._post.version + 1
            p.mark = self.mark
            self._post = p
            p.save(self.path / "posterior_latest.pkl")
        print("learner: posterior reset to frozen start", flush=True)

    def step(self, rows: pd.DataFrame) -> dict:
        t0 = time.time()
        tr = rows_to_training(self.st, rows)
        with self.lock:
            post = self._post.copy()
            factor = 0.5 ** ((t0 - self.last_step) / 3600 / self.half_life_h)
            post.click.decay(factor); post.buy.decay(factor); post.items.decay(factor)
            ok = _update(post, tr)
            if ok and post.anchor is not None:
                post.click.clip_to(post.anchor[0], self.clip_k)
                post.buy.clip_to(post.anchor[1], self.clip_k)
            out = dict(ok=ok, rows=len(rows), impressions=len(tr.yc), clicks=int(tr.yc.sum()), buys=int(tr.yb.sum()),
                       version=self._post.version, seconds=0.0)
            if ok:
                post.version = self._post.version + 1
                post.mark = self.mark
                self._post = post
                self.last_step = t0
                out["version"] = post.version
                post.save(self.path / "posterior_latest.pkl")
                post.save(self.path / f"posterior_v{post.version:05d}.pkl")
        out["seconds"] = round(time.time() - t0, 2)
        self.history.append(out)
        return out

    def fetch(self) -> pd.DataFrame:
        from .. import data as D
        sql = FEEDBACK_SQL.format(team=D.TEAM, mark=self.mark, mark19=self.mark[:19], mature=self.mature_s)
        return D.sql(sql, timeout=60).rename(columns={"ts_s": "ts"})

    def loop(self, stop: threading.Event):
        while not stop.is_set():
            try:
                rows = self.fetch()
                if len(rows):
                    out = self.step(rows)
                    # advance only after the step ran: a transient exception keeps the rows for the next try;
                    # ok=False means the batch itself is bad (non-finite) and retrying it would loop forever
                    self.mark = max(self.mark, max(rows.ts.astype(str)))
                    print(f"learner: v{out['version']} ok={out['ok']} rows={out['rows']} clicks={out['clicks']} "
                          f"buys={out['buys']} {out['seconds']}s", flush=True)
            except Exception as e:
                print("learner: step failed:", str(e)[:160], flush=True)
            stop.wait(self.every_s)


def named(post: Posterior) -> pd.DataFrame:
    return pd.DataFrame(dict(feature=CLICK_FEATURES, mean=post.click.m, std=post.click.std()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    a = ap.parse_args()
    if not a.init:
        ap.error("use --init")
    from .. import data as D
    from .state import LiveState
    st = LiveState.load()
    t = time.time()
    sql = FEEDBACK_SQL.format(team=D.TEAM, mark="2026-11-14 00:00:00", mark19="2026-11-14 00:00:00", mature=360)
    rows = D.sql(sql, timeout=600).rename(columns={"ts_s": "ts"})
    print(f"feedback rows {len(rows):,} ({time.time() - t:.0f}s)", flush=True)
    post = initial_fit(st, rows)
    post.mark = max(rows.ts.astype(str))
    tr = rows_to_training(st, rows)
    print(f"click rows {len(tr.yc):,}, clicks {int(tr.yc.sum())}, buy rows {len(tr.yb)}, buys {int(tr.yb.sum())}")
    print(named(post).round(3).to_string(index=False))
    print("buy weights:", dict(zip(BUY_FEATURES, post.buy.m.round(3))))
    post.save(MODELS / "posterior_init.pkl")
    post.save(MODELS / "posterior_latest.pkl")
    print("saved", MODELS)


if __name__ == "__main__":
    main()
