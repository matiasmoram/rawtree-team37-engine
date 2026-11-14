"""Embed every product description (helmcode qwen3-embedding) and find neighbours for new products.

Writes, all under cache/:
  embeddings.npz               pids (str), vecs (float32, L2-normalised)
  embeddings_meta.json         model, dimension, count, created_at
  new_product_neighbors.json   new pid -> [[neighbour_pid, cosine], ...] (top 20, existing products only)

Resumable: pids already present in cache/embeddings.npz are not re-embedded.
Idempotent: a run with nothing left to embed makes no embedding calls and rewrites identical outputs.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.config import CACHE  # noqa: E402  (importing engine.config loads .env into os.environ)
from engine.rt import RawTree  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

API_URL = "https://api.helmcode.com/v1/embeddings"
MODEL = "qwen3-embedding"
BATCH = 32
MIN_INTERVAL = 60.0 / 55  # 60 req/min limit, small safety margin
MAX_RETRIES = 8
CHECKPOINT_EVERY = 10  # batches
NEIGH_K = 20
NEIGH_SHOW = 3
EXAMPLES = 5

EMB_PATH = CACHE / "embeddings.npz"
META_PATH = CACHE / "embeddings_meta.json"
NEIGH_PATH = CACHE / "new_product_neighbors.json"

COLS = (
    "product_id::String AS pid, category::String AS cat, subcategory::String AS sub, "
    "brand::String AS brand, price_eur::Float64 AS price, description::String AS descr"
)
SQL_ALL = (
    f"SELECT {COLS} FROM shop.catalog "
    f"UNION ALL SELECT {COLS} FROM shop.catalog_updates WHERE change::String = 'new_product'"
)
SQL_NEW = "SELECT product_id::String AS pid FROM shop.catalog_updates WHERE change::String = 'new_product'"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_products() -> tuple[list[str], dict[str, dict], set[str]]:
    rt = RawTree()
    rows = rt.query(SQL_ALL, timeout=120)
    products: dict[str, dict] = {}
    for r in rows:  # UNION ALL may repeat a pid; keep first occurrence
        pid = str(r["pid"])
        if pid in products:
            continue
        products[pid] = {
            "cat": str(r.get("cat") or ""),
            "sub": str(r.get("sub") or ""),
            "brand": str(r.get("brand") or ""),
            "descr": str(r.get("descr") or ""),
        }
    new_set = {str(r["pid"]) for r in rt.query(SQL_NEW, timeout=120)} & products.keys()
    return list(products), products, new_set


def embed_text(p: dict) -> str:
    return f"{p['cat']} > {p['sub']}. Brand {p['brand']}. {p['descr']}"


def retry_after(r: requests.Response, default: float) -> float:
    try:
        return max(1.0, float(r.headers.get("Retry-After", default)))
    except ValueError:  # HTTP-date form, fall back to default
        return float(default)


class Embedder:
    def __init__(self, key: str) -> None:
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {key}"
        self._last = 0.0
        self.calls = 0

    def _pace(self) -> None:
        wait = self._last + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def embed(self, texts: list[str]) -> list[list[float]]:
        backoff = 2.0
        for attempt in range(1, MAX_RETRIES + 1):
            self._pace()
            self.calls += 1
            try:
                r = self.session.post(API_URL, json={"model": MODEL, "input": texts}, timeout=120)
            except requests.RequestException as e:
                print(f"  transport error ({type(e).__name__}), retry {attempt}", flush=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if r.status_code == 429:
                wait = retry_after(r, default=60)
                print(f"  429 rate limited, sleeping {wait:.0f}s (attempt {attempt})", flush=True)
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                print(f"  HTTP {r.status_code}, retry {attempt}", flush=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"embeddings HTTP {r.status_code}: {r.text[:300]}")
            items = sorted(r.json()["data"], key=lambda d: d["index"])
            if len(items) != len(texts):
                raise RuntimeError(f"embedding count mismatch: sent {len(texts)}, got {len(items)}")
            return [d["embedding"] for d in items]
        raise RuntimeError(f"embeddings failed after {MAX_RETRIES} attempts")


def load_cache() -> dict[str, np.ndarray]:
    if not EMB_PATH.exists():
        return {}
    with np.load(EMB_PATH) as z:
        pids = [str(p) for p in z["pids"]]
        vecs = z["vecs"]
    return {p: vecs[i] for i, p in enumerate(pids)}


def save_cache(order: list[str], vec_by_pid: dict[str, np.ndarray]) -> tuple[list[str], np.ndarray]:
    pids = [p for p in order if p in vec_by_pid]
    vecs = np.stack([vec_by_pid[p] for p in pids]).astype(np.float32)
    tmp = EMB_PATH.with_name("embeddings.tmp.npz")
    with open(tmp, "wb") as f:  # file object: np.savez would otherwise append .npz
        np.savez(f, pids=np.array(pids, dtype=str), vecs=vecs)
    os.replace(tmp, EMB_PATH)
    return pids, vecs


def write_meta(count: int, dim: int, embedded_now: int) -> None:
    prev = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else None
    if (
        embedded_now == 0
        and prev
        and prev.get("count") == count
        and prev.get("dimension") == dim
        and prev.get("model") == MODEL
    ):
        return  # nothing changed: keep original created_at
    meta = {"model": MODEL, "dimension": dim, "count": count, "created_at": now_iso()}
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def neighbours(order: list[str], vec_by_pid: dict[str, np.ndarray], new_set: set[str]) -> dict[str, list]:
    new_ids = [p for p in order if p in new_set and p in vec_by_pid]
    old_ids = [p for p in order if p not in new_set and p in vec_by_pid]
    if not new_ids or not old_ids:
        return {}
    E = np.stack([vec_by_pid[p] for p in old_ids])
    N = np.stack([vec_by_pid[p] for p in new_ids])
    sims = N @ E.T  # rows already L2-normalised -> cosine
    k = min(NEIGH_K, len(old_ids))
    out: dict[str, list] = {}
    for i, pid in enumerate(new_ids):
        row = sims[i]
        idx = np.argpartition(-row, k - 1)[:k]
        idx = idx[np.argsort(-row[idx])]
        out[pid] = [[old_ids[j], round(float(row[j]), 6)] for j in idx]
    return out


def main() -> None:
    t0 = time.monotonic()
    key = os.environ.get("HELMCODE_API_KEY")
    if not key:
        sys.exit("HELMCODE_API_KEY missing from .env")

    order, products, new_set = load_products()
    print(f"products: {len(order)} unique | new-flagged (catalog_updates): {len(new_set)} | "
          f"load {time.monotonic() - t0:.1f}s", flush=True)

    vec_by_pid = load_cache()
    todo = [p for p in order if p not in vec_by_pid]
    print(f"cache: {len(order) - len(todo)} already embedded, {len(todo)} to embed", flush=True)

    embedded = 0
    dim = int(next(iter(vec_by_pid.values())).shape[0]) if vec_by_pid else 0
    if todo:
        emb = Embedder(key)
        t_emb = time.monotonic()
        n_batches = (len(todo) + BATCH - 1) // BATCH
        for bi, b in enumerate(range(0, len(todo), BATCH), start=1):
            chunk = todo[b:b + BATCH]
            vecs = emb.embed([embed_text(products[p]) for p in chunk])
            dim = len(vecs[0])
            for p, v in zip(chunk, vecs):
                a = np.asarray(v, dtype=np.float32)
                vec_by_pid[p] = a / max(float(np.linalg.norm(a)), 1e-12)
            embedded += len(chunk)
            if bi % CHECKPOINT_EVERY == 0 or bi == n_batches:
                save_cache(order, vec_by_pid)
                rate = embedded / max(time.monotonic() - t_emb, 1e-9)
                print(f"  batch {bi}/{n_batches}: {embedded}/{len(todo)} embedded "
                      f"({rate:.1f} products/s, {emb.calls} API calls)", flush=True)
        print(f"embedding done in {time.monotonic() - t_emb:.1f}s, API calls: {emb.calls}", flush=True)

    pids, vecs = save_cache(order, vec_by_pid)
    write_meta(len(pids), int(vecs.shape[1]), embedded)
    print(f"saved {EMB_PATH.name}: count={len(pids)} dimension={vecs.shape[1]} dtype={vecs.dtype}", flush=True)

    nb = neighbours(order, vec_by_pid, new_set)
    NEIGH_PATH.write_text(json.dumps(nb, ensure_ascii=False), encoding="utf-8")
    print(f"saved {NEIGH_PATH.name}: {len(nb)} new products x top-{NEIGH_K}", flush=True)

    if nb:
        examples = [p for p in order if p in nb][:EXAMPLES]
        for pid in examples:
            p = products[pid]
            print(f"\n=== NEW {pid} | sub={p['sub']!r} | brand={p['brand']!r}")
            print(f"    descr: {p['descr'][:220]}")
            for npid, sim in nb[pid][:NEIGH_SHOW]:
                q = products[npid]
                print(f"  [{sim:.3f}] {npid} | sub={q['sub']!r} | brand={q['brand']!r}")
                print(f"           descr: {q['descr'][:220]}")
        same = sum(1 for pid in nb if products[pid]["sub"] == products[nb[pid][0][0]]["sub"])
        print(f"\ntop-1 neighbour has same subcategory: {same}/{len(nb)} = {same / len(nb):.1%}")

    print(f"\ntotal time {time.monotonic() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
