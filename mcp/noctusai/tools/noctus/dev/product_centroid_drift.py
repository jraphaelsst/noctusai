"""product_centroid_drift — per-product centroid vs. seed centroid.

Why this exists
    "Is product X drifting from seed?" — today, no quick answer. We grep
    for replicated functions, or eyeball MASTER-PROMPTs. Neither gives a
    single comparable scalar.

    This module computes:
      - The CENTROID of each product's code (average vector over the
        product's code-embeddings chunks).
      - The CENTROID of seed (`products/seed/` + `seed/lib/` chunks).
      - Cosine distance: per-product → seed.

    Result: one comparable scalar per product. Track over time → drift
    surface. Sort across products → identify which has drifted most.

Status
    Snapshot module. Each run writes a row to
    `project-history/product-drift.ndjson` (committed; small enough +
    historical signal is valuable). Trend analysis is on-demand via
    `history(product?)` reading past snapshots.

KB § CONTEXT/PATTERNS/common/product-centroid-drift.md.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Canonical cosine — single source at _embedding_corpus (N=7 consolidation).
from . import _embedding_corpus as _ec

_cosine = _ec.cosine


_SEED_MARKERS = ("products/seed/", "seed/lib/")
_PRODUCT_PREFIX = "products/"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ledger_path() -> Path:
    from settings import REPO_ROOT
    return REPO_ROOT / "project-history" / "product-drift.ndjson"


def _classify(path: str) -> str:
    """Return 'seed' / 'product:<slug>' / 'shared' (or empty)."""
    if any(m in path for m in _SEED_MARKERS):
        return "seed"
    if _PRODUCT_PREFIX in path:
        parts = path.split("/")
        if "products" in parts:
            idx = parts.index("products")
            if idx + 1 < len(parts):
                return f"product:{parts[idx + 1]}"
    return "shared"


def _centroid(vecs: list[list[float]]) -> list[float] | None:
    """Average vector across a list. None if empty."""
    if not vecs:
        return None
    dim = len(vecs[0])
    out = [0.0] * dim
    for v in vecs:
        for i in range(dim):
            out[i] += v[i]
    n = len(vecs)
    return [x / n for x in out]


def snapshot(record_to_ledger: bool = True) -> dict[str, Any]:
    """Compute centroid-vs-seed distance for every product on disk.

    Args:
      record_to_ledger: when True (default), append a row to
        product-drift.ndjson for trend tracking.

    Returns:
      {
        ok: bool,
        ts: ISO,
        seed_chunks: int,
        products: [{slug, chunk_count, distance_from_seed}],
        most_drifted: str | None,
      }
    """
    try:
        from . import code_embeddings as ce
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"code_embeddings unavailable: {e}"}
    rows = ce._load_all_chunk_vectors()
    if not rows:
        return {
            "ok": True, "ts": _now_iso(),
            "seed_chunks": 0, "products": [], "most_drifted": None,
            "message": "code-embeddings cache empty — refresh first",
        }
    # Group vectors by classification.
    by_class: dict[str, list[list[float]]] = defaultdict(list)
    for path, _idx, _sym, _kind, _txt, vec in rows:
        cls = _classify(path)
        if cls:
            by_class[cls].append(vec)
    seed_vecs = by_class.get("seed", [])
    seed_centroid = _centroid(seed_vecs)
    products: list[dict[str, Any]] = []
    if seed_centroid:
        for cls, vecs in by_class.items():
            if not cls.startswith("product:"):
                continue
            slug = cls[len("product:"):]
            c = _centroid(vecs)
            if c is None:
                continue
            sim = _cosine(seed_centroid, c)
            products.append({
                "slug": slug,
                "chunk_count": len(vecs),
                "similarity_to_seed": sim,
                "distance_from_seed": 1.0 - sim,
            })
    products.sort(key=lambda p: p["distance_from_seed"], reverse=True)
    most_drifted = products[0]["slug"] if products else None

    result: dict[str, Any] = {
        "ok": True, "ts": _now_iso(),
        "seed_chunks": len(seed_vecs),
        "products": products,
        "most_drifted": most_drifted,
    }

    if record_to_ledger and products:
        try:
            ledger = _ledger_path()
            ledger.parent.mkdir(parents=True, exist_ok=True)
            row = {
                "ts": result["ts"],
                "seed_chunks": result["seed_chunks"],
                "products": [
                    {"slug": p["slug"],
                     "chunk_count": p["chunk_count"],
                     "distance_from_seed": round(p["distance_from_seed"], 6)}
                    for p in products
                ],
            }
            with ledger.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass

    return result


def history(product: str | None = None, limit: int = 30) -> dict[str, Any]:
    """Read the drift ledger; return per-product trend.

    Args:
      product: filter to one product slug.
      limit: max snapshots to return.

    Returns: `{ok, history: [{ts, slug, distance_from_seed, chunk_count}]}`.
    """
    path = _ledger_path()
    if not path.exists():
        return {"ok": True, "history": [], "message": "no snapshots yet"}
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = entry.get("ts", "")
        for p in entry.get("products", []):
            if product and p.get("slug") != product:
                continue
            rows.append({
                "ts": ts,
                "slug": p.get("slug"),
                "distance_from_seed": p.get("distance_from_seed"),
                "chunk_count": p.get("chunk_count"),
            })
    rows.sort(key=lambda r: r["ts"], reverse=True)
    return {"ok": True, "history": rows[:limit]}


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.product_centroid_snapshot",
        description=(
            "Compute each product's code centroid vs seed centroid; "
            "returns per-product distance + which product has drifted "
            "most. Appends snapshot to project-history/product-drift.ndjson "
            "for trend tracking. Reads the code-embeddings cache — refresh "
            "first if stale. "
            "KB § CONTEXT/PATTERNS/common/product-centroid-drift.md."
        ),
    )
    def _snap(record_to_ledger: bool = True) -> dict:
        return snapshot(record_to_ledger=record_to_ledger)

    @server.tool(
        name="noctus.dev.product_centroid_history",
        description=(
            "Read past product-drift snapshots; optional `product=<slug>` "
            "filter. Returns trend rows newest-first."
        ),
    )
    def _hist(product: str | None = None, limit: int = 30) -> dict:
        return history(product=product, limit=limit)


__all__ = ["snapshot", "history", "register"]
