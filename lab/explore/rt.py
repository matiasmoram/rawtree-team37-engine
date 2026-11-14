"""Read-only RawTree helper for exploration. Never writes to team_37.submissions.

    from rt import sql
    df = sql("SELECT count() FROM shop.catalog")

    python explore/rt.py "SELECT ..."     # quick CLI query, prints a table
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
for line in (ROOT / ".env").read_text().splitlines() if (ROOT / ".env").exists() else []:
    key, _, value = line.partition("=")
    if key.strip():
        os.environ.setdefault(key.strip(), value.strip())

API = os.environ.get("RAWTREE_API_URL", "https://api.rawtree.com")
TEAM = os.environ["TEAM_ID"]
_http = requests.Session()
_http.headers["Authorization"] = f"Bearer {os.environ['RAWTREE_API_KEY']}"

_WRITE = re.compile(r"^\s*(INSERT|ALTER|DROP|TRUNCATE|DELETE|CREATE|RENAME|OPTIMIZE)\b", re.I)


def sql(q: str, timeout: int = 120) -> pd.DataFrame:
    """Run a read-only SELECT and return a DataFrame."""
    if _WRITE.match(q):
        raise ValueError("rt.sql is read-only")
    r = _http.post(f"{API}/v1/query", json={"sql": q}, timeout=timeout)
    if not r.ok:
        raise RuntimeError(f"{r.status_code}: {r.text[:500]}")
    return pd.DataFrame(r.json()["data"])


if __name__ == "__main__":
    pd.set_option("display.width", 200, "display.max_columns", 50, "display.max_colwidth", 80)
    print(sql(" ".join(sys.argv[1:])).to_string())
