"""Policies available to the live runner, by name."""
from .base import GlobalBestSellers, LastViewCategoryBestSellers
from .evidence import EvidencePolicy

FACTORIES = {
    "ref-global-bestsellers": GlobalBestSellers,
    "ref-lastview-category": LastViewCategoryBestSellers,
    "ev-v1": lambda: EvidencePolicy("ev-v1"),
    # v2: live attribution showed past purchases convert ~0 (bought items lose appeal); past views convert like session views.
    "ev-v2": lambda: EvidencePolicy("ev-v2", bought_factor=0.02, rel={"user_viewed": 1.5}),
    "ev-v2-uv": lambda: EvidencePolicy("ev-v2-uv", bought_factor=0.02, rel={"user_viewed": 2.5}),
    "ev-v2-cat": lambda: EvidencePolicy("ev-v2-cat", bought_factor=0.02, rel={"user_viewed": 1.5, "same_cat": 0.25, "same_sub": 0.25}),
    "ev-v2-tier": lambda: EvidencePolicy("ev-v2-tier", bought_factor=0.02, rel={"last_view": 12.0, "earlier_view": 9.0, "user_viewed": 1.5}),
    "ev-v2-nocovis": lambda: EvidencePolicy("ev-v2-nocovis", bought_factor=0.02, rel={"user_viewed": 1.5}, covis_gain=0.0),
}


def get_policy(name: str):
    if name not in FACTORIES:
        raise KeyError(f"unknown policy {name}; known: {sorted(FACTORIES)}")
    return FACTORIES[name]()
