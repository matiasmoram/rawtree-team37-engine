"""Shared data types: requests as the live system and the evaluators see them."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

TS_FMT = "%Y-%m-%d %H:%M:%S.%f"


def parse_ts(value: str | datetime) -> datetime:
    """RawTree returns 'YYYY-MM-DD HH:MM:SS.fffffffff' (UTC, up to 9 decimals) or ISO strings."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    # fromisoformat accepts ClickHouse's nanoseconds (truncated to microseconds),
    # UTC Z and explicit offsets, including whole seconds without a fraction.
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def sql_ts(dt: datetime) -> str:
    """Datetime literal for SQL comparisons against ts::DateTime64(3) (UTC)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


@dataclass
class Request:
    request_id: str
    ts: datetime
    user_id: str
    is_new_user: bool
    page: str
    device: str
    region: str
    recent_views: list[tuple[str, datetime]] = field(default_factory=list)

    @property
    def viewed(self) -> list[str]:
        """Viewed product ids, most recent first, deduplicated."""
        seen: set[str] = set()
        out: list[str] = []
        for pid, _ in sorted(self.recent_views, key=lambda x: x[1], reverse=True):
            if pid not in seen:
                seen.add(pid)
                out.append(pid)
        return out

    @classmethod
    def from_row(cls, row: dict) -> "Request":
        views = row.get("recent_views") or []
        return cls(
            request_id=str(row["request_id"]),
            ts=parse_ts(row["ts"]),
            user_id=str(row.get("user_id") or ""),
            is_new_user=bool(row.get("is_new_user") or False),
            page=str(row.get("page") or row.get("context.page") or ""),
            device=str(row.get("device") or row.get("context.device") or ""),
            region=str(row.get("region") or row.get("context.region") or ""),
            recent_views=[(str(v["product_id"]), parse_ts(v["ts"])) for v in views if v and v.get("product_id")],
        )
