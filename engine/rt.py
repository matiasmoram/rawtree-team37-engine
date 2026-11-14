"""Thin RawTree HTTP client. One instance per thread (requests.Session is not thread-safe)."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .config import API, API_KEY, TEAM

log = logging.getLogger("rt")
Row = dict[str, Any]


class RawTreeError(RuntimeError):
    pass


class RawTree:
    def __init__(self, timeout: float = 30.0) -> None:
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {API_KEY}"
        self.timeout = timeout

    def query(self, sql: str, timeout: float | None = None, retries: int = 2) -> list[Row]:
        """Run SQL and return rows. Retries only transport errors and 429/5xx, never SQL errors."""
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                t = timeout or self.timeout
                r = self.session.post(f"{API}/v1/query", json={"sql": sql}, timeout=(min(1.0, t), t))
            except (requests.ConnectionError, requests.Timeout) as e:
                last = e
                time.sleep(0.2 * (attempt + 1))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                last = RawTreeError(f"HTTP {r.status_code}: {r.text[:300]}")
                time.sleep(float(r.headers.get("retry-after", 0.5 * (attempt + 1))))
                continue
            if r.status_code >= 400:
                raise RawTreeError(f"HTTP {r.status_code}: {r.text[:800]}")
            return r.json()["data"]
        raise RawTreeError(f"query failed after {retries + 1} attempts: {last}")

    def insert(self, table: str, rows: list[Row], database: str = TEAM, timeout: float = 5.0) -> dict:
        r = self.session.post(f"{API}/v1/tables/{table}", params={"database": database}, json=rows, timeout=(min(1.0, timeout), timeout))
        if r.status_code >= 400:
            raise RawTreeError(f"insert HTTP {r.status_code}: {r.text[:500]}")
        return r.json()
