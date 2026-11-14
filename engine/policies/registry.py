"""Policies available to the live runner, by name."""
from .base import GlobalBestSellers, LastViewCategoryBestSellers
from .evidence import EvidencePolicy

FACTORIES = {
    "ref-global-bestsellers": GlobalBestSellers,
    "ref-lastview-category": LastViewCategoryBestSellers,
    "ev-v1": lambda: EvidencePolicy("ev-v1"),
}


def get_policy(name: str):
    if name not in FACTORIES:
        raise KeyError(f"unknown policy {name}; known: {sorted(FACTORIES)}")
    return FACTORIES[name]()
