"""Content-only neighbours, usable without a network call in the serving path.

The existing embedding artifact contains descriptions, not event labels. A future
artifact is safe for replay only when both endpoint products already exist at the
request time. Behavioural priors are always read from the supplied PIT snapshot.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .config import CACHE
from .snapshot import Snapshot
from .types import Request


@dataclass(frozen=True)
class ContentIndex:
    forward: dict[str, tuple[tuple[str, float], ...]] = field(default_factory=dict)
    reverse: dict[str, tuple[tuple[str, float], ...]] = field(default_factory=dict)
    source: str = "content_only"

    @classmethod
    def load(cls, path: str | Path | None = None, min_similarity: float = 0.80,
             top: int = 20, reverse_top: int = 10) -> "ContentIndex":
        """Validate and bound a local artifact; missing/unreadable files degrade to empty.

        Supported layouts are the original {new_pid: [[old_pid, cosine], ...]}
        and an envelope {source_kind: content_only, neighbors: {...}}. Behavioural
        embedding artifacts must not be passed through this content-only loader.
        """
        path = Path(path) if path is not None else CACHE / "new_product_neighbors.json"
        if top < 1 or reverse_top < 1 or not 0 <= min_similarity <= 1:
            raise ValueError("invalid neighbour bounds")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        if "neighbors" in data:
            if data.get("source_kind", "content_only") != "content_only":
                return cls()
            data = data["neighbors"]
        if not isinstance(data, dict):
            return cls()
        forward: dict[str, tuple[tuple[str, float], ...]] = {}
        reverse: dict[str, dict[str, float]] = {}
        for pid, raw in data.items():
            if not isinstance(pid, str) or not isinstance(raw, list):
                continue
            valid: dict[str, float] = {}
            for pair in raw:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    continue
                q, sim = pair
                try:
                    sim = float(sim)
                except (TypeError, ValueError):
                    continue
                if (not isinstance(q, str) or q == pid or not math.isfinite(sim)
                        or sim < min_similarity or sim > 1.000001):
                    continue
                valid[q] = max(valid.get(q, 0.0), min(1.0, sim))
            rows = tuple(sorted(valid.items(), key=lambda row: (-row[1], row[0]))[:top])
            if rows:
                forward[pid] = rows
                for q, sim in rows:
                    reverse.setdefault(q, {})[pid] = sim
        return cls(forward, {q: tuple(sorted(v.items(), key=lambda row: (-row[1], row[0]))[:reverse_top])
                             for q, v in reverse.items()})


def known_at(pid: str, snap: Snapshot, req: Request, active: bool = True) -> bool:
    p = snap.products.get(pid)
    return bool(p is not None and (not active or p.active)
                and (not p.added_ts or p.added_ts < req.ts))


def content_candidates(req: Request, snap: Snapshot, index: ContentIndex,
                       max_candidates: int = 80) -> dict[str, float]:
    """Forward/reverse similarity and borrowed co-vis candidates, all bounded.

    Candidate support is not a purchase probability. Similarity is confined to
    [0,1], and the separate policy controls its bounded score multiplier.
    """
    out: dict[str, float] = {}
    for rank, pid in enumerate(req.viewed[:4]):
        if not known_at(pid, snap, req, active=False):
            continue
        decay = 0.7 ** rank
        for q, sim in index.forward.get(pid, ()) + index.reverse.get(pid, ()):
            if known_at(q, snap, req):
                out[q] = max(out.get(q, 0.0), decay * sim)
        # A new viewed product can borrow candidates from its established peers.
        for peer, sim in index.forward.get(pid, ())[:5]:
            if not known_at(peer, snap, req, active=False):
                continue
            for table, strength in ((snap.covis_vb, 0.5), (snap.covis_vv, 0.25)):
                rows = table.get(peer, [])[:10]
                denom = max((float(w) for _, w in rows), default=1.0) or 1.0
                for q, w in rows:
                    if known_at(q, snap, req):
                        value = decay * sim * strength * min(1.0, max(0.0, float(w) / denom))
                        out[q] = max(out.get(q, 0.0), value)
    return dict(sorted(out.items(), key=lambda row: (-row[1], row[0]))[:max_candidates])


def borrowed_quality(pid: str, snap: Snapshot, index: ContentIndex,
                     base_quality, strength: float = 30.0) -> float:
    """Borrow bounded peer priors only when a new product has little own evidence.

    base_quality is a callable using only the supplied snapshot, never another
    content-borrowing call, to avoid recursive prior propagation.
    """
    own = float(base_quality(pid))
    p = snap.products.get(pid)
    if p is None or not p.is_new or strength <= 0:
        return own
    views = max(0.0, float(snap.stats.get(pid, {}).get("view_all", 0.0)))
    neighbours = [(q, sim) for q, sim in index.forward.get(pid, ())[:10]
                  if q in snap.products and not snap.products[q].is_new]
    denom = sum(sim for _, sim in neighbours)
    if not denom:
        return own
    peer = sum(sim * min(3.0, max(0.4, float(base_quality(q)))) for q, sim in neighbours) / denom
    weight = strength / (strength + views)
    return min(3.0, max(0.4, (1.0 - weight) * own + weight * peer))
