"""Configuration: credentials from .env, paths, constants."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
LOGS = ROOT / "logs"
CACHE.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env()
API = os.environ.get("RAWTREE_API_URL", "https://api.rawtree.com")
TEAM = os.environ["TEAM_ID"]
API_KEY = os.environ["RAWTREE_API_KEY"]
