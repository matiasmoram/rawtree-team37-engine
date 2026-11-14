"""Feature flags (V2 plan §7). All V2 flags OFF reproduces A exactly (tests/test_a_parity.py)."""
from dataclasses import dataclass


@dataclass
class Config:
    MODEL_VERSION: str = "team37-a"
    USE_ONLINE_CORRECTION: bool = False   # P2
    USE_DRIFT_FEATURES: bool = False      # P3 (not built yet)
    USE_CONTEXTUAL_TS: bool = False       # P4 (not built yet)
    USE_NEW_SLATE_BUILDER: bool = False   # P5 (not built yet)
    MAX_ONLINE_CORRECTION: float = 1.5    # |delta| bound in logit units; tuned by chronological validation
    ONLINE_LEARNING_RATE: float = 0.05
    ONLINE_L2: float = 1e-3               # pull toward theta = 0 (A as prior)
    MIN_FINAL_FEEDBACK: int = 300         # warm-up: no correction applied before this many feedback events
    GRAD_CLIP: float = 5.0


A = Config()
V2 = Config(MODEL_VERSION="team37-v2.1", USE_ONLINE_CORRECTION=True)
