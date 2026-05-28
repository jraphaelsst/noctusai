"""cache_telemetry — log cache hit/miss + query frequency per keeper-mirror cache.

Why this exists
    We have 5 keeper-mirror caches. We don't actually know if agents
    USE them. The N=5 caches were sized for theoretical demand; this
    module records the EMPIRICAL demand so future cost / sizing
    decisions are evidence-driven.

What it logs
    For each cache query: timestamp, cache name, operation
    (search / refresh / list / etc.), result count, latency-ms (when
    available). Appended to `project-history/cache-telemetry.ndjson`
    (gitignored — it's high-volume + per-user noise).

How it composes
    Caches call `cache_telemetry.record(cache, op, result_count, latency_ms?)`
    after the operation. No-op if the ledger dir doesn't exist (graceful
    degrade — never block the cache on telemetry).

Status: opt-in. Caches that want telemetry coverage call `record()`;
caches that don't can ignore. Adding to existing caches is a one-line
addition after the operation; no contract change.

KB § CONTEXT/PATTERNS/common/cache-telemetry.md.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _ledger_path() -> Path:
    """Return the telemetry ledger path. Lazy import to avoid REPO_ROOT
    surfacing in test fixtures that monkeypatch REPO_ROOT after import."""
    from .cache_backend import cache_dir
    return cache_dir() / "cache-telemetry.ndjson"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(
    cache: str,
    operation: str,
    result_count: int | None = None,
    latency_ms: float | None = None,
    meta: dict | None = None,
) -> None:
    """Append a telemetry row. Silent on failure (advisory layer).

    Args:
      cache: cache name (e.g. "kb-embeddings").
      operation: short verb (e.g. "search", "refresh", "list").
      result_count: optional row count returned (for searches).
      latency_ms: optional millisecond wall-clock.
      meta: optional dict of extra context (query hash, top_k, etc.).
    """
    try:
        path = _ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": _now_iso(),
            "cache": cache,
            "operation": operation,
            "result_count": result_count,
            "latency_ms": latency_ms,
            "meta": meta or {},
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — never propagate telemetry failures
        pass


def summary(
    since: str | None = None,
    cache: str | None = None,
) -> dict[str, Any]:
    """Read the telemetry ledger; return per-cache + per-operation counts.

    Args:
      since: ISO date prefix; only rows with ts >= since.
      cache: filter to one cache name.

    Returns:
      {
        ok: bool,
        total: int,
        by_cache: {cache_name: count, ...},
        by_operation: {op: count, ...},
        by_cache_operation: {f"{cache}::{op}": count, ...},
        latest_per_cache: {cache_name: latest_ts, ...},
      }
    """
    path = _ledger_path()
    if not path.exists():
        return {
            "ok": True, "total": 0,
            "by_cache": {}, "by_operation": {},
            "by_cache_operation": {}, "latest_per_cache": {},
            "message": "no telemetry recorded yet",
        }
    by_cache: dict[str, int] = {}
    by_op: dict[str, int] = {}
    by_co: dict[str, int] = {}
    latest: dict[str, str] = {}
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = entry.get("ts", "")
        c = entry.get("cache", "?")
        op = entry.get("operation", "?")
        if since and ts < since:
            continue
        if cache and c != cache:
            continue
        total += 1
        by_cache[c] = by_cache.get(c, 0) + 1
        by_op[op] = by_op.get(op, 0) + 1
        co_key = f"{c}::{op}"
        by_co[co_key] = by_co.get(co_key, 0) + 1
        if ts and (c not in latest or ts > latest[c]):
            latest[c] = ts
    return {
        "ok": True,
        "total": total,
        "by_cache": by_cache,
        "by_operation": by_op,
        "by_cache_operation": by_co,
        "latest_per_cache": latest,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.cache_telemetry_summary",
        description=(
            "Read the cache-telemetry.ndjson ledger; return per-cache and "
            "per-operation hit counts. Optional `since` (ISO date prefix) "
            "and `cache` (name filter). Surfaces 'are agents actually "
            "using the 5 keeper-mirror caches?' empirically. "
            "KB § CONTEXT/PATTERNS/common/cache-telemetry.md."
        ),
    )
    def _summary(since: str | None = None, cache: str | None = None) -> dict:
        return summary(since=since, cache=cache)


__all__ = ["record", "summary", "register"]
