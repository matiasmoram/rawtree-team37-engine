"""Policies available to the live runner, by name."""
from .base import GlobalBestSellers, LastViewCategoryBestSellers
from .evidence import EvidencePolicy
from .lgbm import LgbmPolicy
from .content import ContentPolicy, RecentCovisPolicy
from .explore import TailExplorePolicy
from .cartfirst import CartFirstPolicy
from .variants import VARIANTS
from .money import MoneyPolicy
from .skibidy import SkibidyPolicy

FACTORIES = {
    "ev-content": ContentPolicy,
    "ev-recent-covis": RecentCovisPolicy,
    "lgbm-recent": lambda: LgbmPolicy("lgbm-recent", "models/lgbm_recent_20261114T1523.txt", num_threads=2,
                                    bought_penalty=1.0, use_content=True),
    "ev-content-tail": lambda: TailExplorePolicy(ContentPolicy(), name="ev-content-tail", epsilon=0.05),
    "cf-v1": lambda: CartFirstPolicy("cf-v1"),
    "cf-v1-cap3": lambda: CartFirstPolicy("cf-v1-cap3", cart_cap=3),
    "cf-v1-cap10": lambda: CartFirstPolicy("cf-v1-cap10", cart_cap=10),
    "money-v1": lambda: MoneyPolicy("money-v1", alpha=0.5),
    "money-v1-a03": lambda: MoneyPolicy("money-v1-a03", alpha=0.3),
    "money-v1-a08": lambda: MoneyPolicy("money-v1-a08", alpha=0.8),
    "skibidy-v1": lambda: SkibidyPolicy("skibidy-v1"),
    "skibidy-v1g": lambda: SkibidyPolicy("skibidy-v1g", explore_frac=0.0),
    "ref-global-bestsellers": GlobalBestSellers,
    "ref-lastview-category": LastViewCategoryBestSellers,
    "ev-v1": lambda: EvidencePolicy("ev-v1"),
    # v2: live attribution showed past purchases convert ~0 (bought items lose appeal); past views convert like session views.
    "ev-v2": lambda: EvidencePolicy("ev-v2", bought_factor=0.02, rel={"user_viewed": 1.5}),
    "ev-v2-uv": lambda: EvidencePolicy("ev-v2-uv", bought_factor=0.02, rel={"user_viewed": 2.5}),
    "ev-v2-cat": lambda: EvidencePolicy("ev-v2-cat", bought_factor=0.02, rel={"user_viewed": 1.5, "same_cat": 0.25, "same_sub": 0.25}),
    "ev-v2-tier": lambda: EvidencePolicy("ev-v2-tier", bought_factor=0.02, rel={"last_view": 12.0, "earlier_view": 9.0, "user_viewed": 1.5}),
    # v3 (15:45): combine the v2 winners (past views high, no co-visitation boost, same_cat == same_sub)
    "ev-v3": lambda: EvidencePolicy("ev-v3", bought_factor=0.02, covis_gain=0.0, rel={"user_viewed": 2.5, "same_cat": 0.25, "same_sub": 0.25}),
    "ev-v3-uv4": lambda: EvidencePolicy("ev-v3-uv4", bought_factor=0.02, covis_gain=0.0, rel={"user_viewed": 4.0, "same_cat": 0.25, "same_sub": 0.25}),
    "ev-v3-lowsess": lambda: EvidencePolicy("ev-v3-lowsess", bought_factor=0.02, covis_gain=0.0, rel={"user_viewed": 2.5, "last_view": 1.2, "earlier_view": 0.9, "same_cat": 0.25, "same_sub": 0.25}),
    # learned on live feedback 12:10-14:25 (pre-v2 exposure); exploratory, use only as a small arm
    "lgbm-live": lambda: LgbmPolicy("lgbm-live", "cache/lgbm_live_20261114T1425.txt"),
    # v3-aff: user category affinity drives discovery items (top feature of the live ranker)
    "ev-v3-aff": lambda: EvidencePolicy("ev-v3-aff", bought_factor=0.02, covis_gain=0.0, affinity_gain=4.0, rel={"user_viewed": 2.5, "same_cat": 0.25, "same_sub": 0.25}),
}
FACTORIES.update(VARIANTS)


def get_policy(name: str):
    if name not in FACTORIES:
        raise KeyError(f"unknown policy {name}; known: {sorted(FACTORIES)}")
    return FACTORIES[name]()
