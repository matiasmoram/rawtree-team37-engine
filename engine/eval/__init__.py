"""Offline evaluation suite: three evaluators on the challenge data, all scored against a snapshot at cutoff T.

* ``LoggedImpressionEval``: replay of logged carousel impressions (purchase/click hits, SNIPS slot-1 rate).
* ``OrganicNextPurchaseEval``: pseudo-requests before organic purchases (THETA-weighted hit, recall@10).
* ``LiveRequestEval``: real live requests labelled with the user's next purchases/carts (NDCG-like score).

CLI: ``python scripts/run_eval.py --help``. Register new policies in ``engine/eval/registry.py``.
"""
from .common import THETA, Evaluator, Report
from .live_requests import LiveRequestEval
from .logged import LoggedImpressionEval
from .organic import OrganicNextPurchaseEval
from .registry import POLICIES, make_policies

__all__ = ["THETA", "Evaluator", "Report", "LoggedImpressionEval", "OrganicNextPurchaseEval", "LiveRequestEval",
           "POLICIES", "make_policies"]
