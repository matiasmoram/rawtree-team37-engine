"""V2 plan P0/P2 acceptance: V2 flags off (or theta = 0) must reproduce A exactly on a frozen snapshot."""
import dataclasses

import numpy as np

from recsys import data as D
from recsys.config import A, V2
from recsys.features import Store
from recsys.online_head import PHI, OnlineHead
from recsys.policies import Ranker


def test_parity():
    S = Store.build("live")
    df = D.live_feedback().head(400)
    R = S.requests(df)
    unav = [S.unavailable_at(t) for t in df.ts.pipe(lambda x: __import__("pandas").to_datetime(x))]
    a = Ranker.load(S).recommend(S, R, unav)
    # 1) flags off, with a head object attached
    off = Ranker.load(S, head=OnlineHead(A)).recommend(S, R, unav)
    # 2) flag on but theta = 0 and warm-up satisfied
    h0 = OnlineHead(dataclasses.replace(V2, MIN_FINAL_FEEDBACK=0))
    zero = Ranker.load(S, head=h0).recommend(S, R, unav)
    # 3) flag on, non-zero theta: must differ (the head actually does something)
    h1 = OnlineHead(dataclasses.replace(V2, MIN_FINAL_FEEDBACK=0), theta=np.eye(len(PHI))[PHI.index("logprice")] * 1.0)
    moved = Ranker.load(S, head=h1).recommend(S, R, unav)
    assert off == a, "flags off != A"
    assert zero == a, "theta=0 != A"
    assert moved != a, "non-zero theta changed nothing"
    print("parity OK: flags-off == A, theta=0 == A, theta!=0 changes", sum(x != y for x, y in zip(moved, a)), "of", len(a))


if __name__ == "__main__":
    test_parity()
