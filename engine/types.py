"""Shared data types: requests as the live system and the evaluators see them."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

TS_FMT = "%Y-%m-%d %H:%M:%S.%f"


def parse_ts(value: str | datetime) -> datetime:
    """RawTree returns 'YYYY-MM-DD HH:MM:SS.fffffffff' (UTC, up to 9 decimals) or ISO strings."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).replace("T", " ").rstrip("Z")
    if "." in s:
        head, frac = s.split(".", 1)
        s = f"{head}.{frac[:6]}"
    else:
        s = f"{s}.000000"
    return datetime.strptime(s, TS_FMT).replace(tzinfo=timezone.utc)


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
