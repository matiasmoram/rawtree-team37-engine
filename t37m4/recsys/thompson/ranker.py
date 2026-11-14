"""Candidates -> bans -> greedy slot-by-slot fill on P(buy at slot), near-ties broken by P(buy)*price^0.1."""
from __future__ import annotations

import numpy as np

from .features import Req, buy_matrix, click_matrix
from .model import Draw, p_buy

ALPHA = 0.1
NEAR_TIE = 0.95


def candidates(st, req: Req, cap: int = 200) -> np.ndarray:
    out: dict[int, None] = {}

    def add(xs, k=None):
        for i in (xs if k is None else xs[:k]):
            if len(out) >= cap:
                return
            out.setdefault(int(i), None)

    it = st.items
    add(reversed(req.views))
    subs = it["sub"].to_numpy()
    cats = it.cat.to_numpy()
    for s in dict.fromkeys(int(subs[v]) for v in reversed(req.views)):
        add(st.sub_best.get(s, []), 40)
    for v in reversed(req.views):
        add(st.cov.get(v, []), 30)
    for c in dict.fromkeys(int(cats[v]) for v in reversed(req.views)):
        add(st.cat_best.get(c, []), 40)
    u = st.ucat.get(req.user_id)
    if u is not None:
        for c in np.argsort(-u)[:3]:
            add(st.cat_best.get(int(c), []), 30)
    if len(out) < 60:
        lists = [st.cat_best[c] for c in sorted(st.cat_best)]
        for k in range(max((len(x) for x in lists), default=0)):
            add([x[k] for x in lists if k < len(x)])
            if len(out) >= 60:
                break
    return np.fromiter(out, dtype=int, count=len(out))


def banned(st, req: Req) -> set[int]:
    return set(st.bought.get(req.user_id, ())) | set(st.oos)


def fill(st, chosen: list[int], ban: set[int], k: int = 10) -> list[int]:
    used = set(chosen) | ban
    lists = [st.cat_best[c] for c in sorted(st.cat_best)]
    depth = 0
    while len(chosen) < k and any(depth < len(x) for x in lists):
        for x in lists:
            if depth < len(x) and x[depth] not in used and len(chosen) < k:
                chosen.append(int(x[depth])); used.add(x[depth])
        depth += 1
    return chosen


def score(st, req: Req, cand: np.ndarray, draw: Draw) -> np.ndarray:
    """P(buy) per candidate per slot, shape (n, 10)."""
    n = len(cand)
    items = np.repeat(cand, 10)
    slots = np.tile(np.arange(1, 11), n)
    Xc = click_matrix(st, req, items, slots)
    Xb = buy_matrix(st, req, items)
    return p_buy(draw, Xc, Xb, items).reshape(n, 10)


def rank(st, req: Req, draw: Draw, k: int = 10) -> list[int]:
    ban = banned(st, req)
    cand = np.array([i for i in candidates(st, req) if i not in ban], dtype=int)
    chosen: list[int] = []
    if len(cand):
        P = score(st, req, cand, draw)
        rev = P * (np.maximum(st.items.price.to_numpy().astype(float)[cand], .01) ** ALPHA)[:, None]
        free = np.ones(len(cand), bool)
        for s in range(min(k, len(cand))):
            col = np.where(free, P[:, s], -1.0)
            best = col.max()
            near = free & (col >= NEAR_TIE * best)
            j = int(np.argmax(np.where(near, rev[:, s], -1.0)))
            chosen.append(int(cand[j])); free[j] = False
    return fill(st, chosen, ban, k)
