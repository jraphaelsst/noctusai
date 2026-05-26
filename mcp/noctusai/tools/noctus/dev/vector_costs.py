"""OpenAI embedding API cost tracking — durable audit ledger.

Why this exists
    Every `refresh()` call in kb_embeddings (and future code-embedding modules)
    consumes tokens via the OpenAI embedding API. Without instrumentation, cost
    is invisible: no per-namespace breakdown, no trend over time, no budget gate.
    This module is the generic platform tool — cache modules opt in by calling
    `log_refresh_batch(...)` at the end of each refresh run.

Architecture
    - Durable source-of-truth: `project-history/vector-costs.ndjson` (committed,
      sibling of auto-improvement.ndjson + worktree-salvage.ndjson).
    - One NDJSON line per refresh batch.
    - `report()` + `total()` aggregate on-the-fly from the ledger (no secondary
      cache needed — the ledger is small, scans are trivial).

Cost table (source: OpenAI pricing page, accessed 2026-05-26; update on model change)
    text-embedding-3-small : $0.02  / 1M tokens
    text-embedding-3-large : $0.13  / 1M tokens
    text-embedding-ada-002 : $0.10  / 1M tokens

Token estimation
    Preferred: `tiktoken` (if installed in venv — exact, model-specific BPE).
    Fallback: `len(text) // 4` (rough heuristic, accurate to ±20% for English prose).

NDJSON schema (one line per batch):
    {
      "ts":                   ISO-8601 UTC timestamp,
      "namespace":            str ("kb-embeddings" | "code-embeddings" | ...),
      "model":                str ("text-embedding-3-small" | ...),
      "provider":             str ("openai"),
      "doc_count":            int,
      "chunk_count":          int,
      "estimated_tokens":     int,
      "estimated_cost_usd":   float,
      "source_ref":           str | null   (e.g. "session:2026-05-26")
    }

Depth: `KB § PATTERNS/common/vector-cost-tracking.md`.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
LEDGER_PATH = REPO_ROOT / "project-history" / "vector-costs.ndjson"

# ── Cost table ────────────────────────────────────────────────────────────────
# USD per 1 million tokens.
# Source: https://platform.openai.com/docs/models/embeddings (2026-05-26).
# Update here + the KB doc when OpenAI reprices.
COST_PER_MILLION_TOKENS: dict[str, float] = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
    "text-embedding-ada-002": 0.10,
}


# ── Token estimation ──────────────────────────────────────────────────────────
def estimate_tokens(text: str, model: str = "text-embedding-3-small") -> int:
    """Estimate the token count for `text`.

    Uses tiktoken when available (exact, model-specific BPE encoding).
    Falls back to `len(text) // 4` when tiktoken is not installed (rough
    approximation, accurate to ±20% for English prose).

    `model` is accepted for future tiktoken encoding selection but is not
    used in the fallback path.
    """
    try:
        import tiktoken  # type: ignore[import-not-found]
        # text-embedding-3-* uses the cl100k_base encoding (same as GPT-4).
        # text-embedding-ada-002 also uses cl100k_base.
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:  # tiktoken absent or encoding failure — fallback
        return len(text) // 4


# ── Cost estimation ───────────────────────────────────────────────────────────
def estimate_cost(tokens: int, model: str = "text-embedding-3-small") -> float:
    """Compute the USD cost for `tokens` tokens using the known cost table.

    Returns 0.0 for unknown models (caller should surface a warning).
    Formula: cost_per_million * tokens / 1_000_000
    """
    rate = COST_PER_MILLION_TOKENS.get(model, 0.0)
    if rate == 0.0 and model not in COST_PER_MILLION_TOKENS:
        logger.warning("vector_costs: unknown model %r — cost defaulting to 0.0", model)
    return rate * tokens / 1_000_000


# ── Helpers ───────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Public API ────────────────────────────────────────────────────────────────
def log_refresh_batch(
    namespace: str,
    model: str,
    doc_count: int,
    chunk_count: int,
    estimated_tokens: int,
    cost_estimate_usd: float | None = None,
    provider: str = "openai",
    source_ref: str | None = None,
) -> dict:
    """Append one NDJSON row to the vector-costs ledger.

    If `cost_estimate_usd` is None it is derived from `estimated_tokens` and
    the built-in cost table. Returns `{ok, path, row}`.
    """
    if cost_estimate_usd is None:
        cost_estimate_usd = estimate_cost(estimated_tokens, model)

    row: dict = {
        "ts": _now_iso(),
        "namespace": namespace,
        "model": model,
        "provider": provider,
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "estimated_tokens": estimated_tokens,
        "estimated_cost_usd": cost_estimate_usd,
        "source_ref": source_ref,
    }
    try:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        logger.debug(
            "vector_costs: logged batch ns=%s chunks=%d tokens=%d cost=%.6f",
            namespace, chunk_count, estimated_tokens, cost_estimate_usd,
        )
        return {"ok": True, "path": str(LEDGER_PATH), "row": row}
    except OSError as exc:
        logger.error("vector_costs: failed to write ledger: %s", exc)
        return {"ok": False, "error": str(exc), "row": row}


def _read_ledger(namespace: str | None = None, since: str | None = None) -> list[dict]:
    """Read + filter NDJSON rows from the ledger.

    `since` is an ISO date string (YYYY-MM-DD or full ISO-8601); rows whose
    `ts` field is < `since` are excluded.
    """
    if not LEDGER_PATH.exists():
        return []
    rows: list[dict] = []
    with LEDGER_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if namespace is not None and row.get("namespace") != namespace:
                continue
            if since is not None and row.get("ts", "") < since:
                continue
            rows.append(row)
    return rows


def _period_key(ts: str, group_by: str) -> str:
    """Truncate an ISO timestamp to the requested granularity."""
    # ts is ISO-8601; prefix slicing is safe for day/week approximation.
    if group_by == "day":
        return ts[:10]          # YYYY-MM-DD
    if group_by == "week":
        # ISO week — simplification: truncate to Monday of the week.
        try:
            dt = datetime.fromisoformat(ts[:10])
            monday = dt - __import__("datetime").timedelta(days=dt.weekday())
            return monday.strftime("%Y-W%W")
        except ValueError:
            return ts[:10]
    if group_by == "month":
        return ts[:7]           # YYYY-MM
    return ts[:10]              # fallback: day


def report(
    namespace: str | None = None,
    since: str | None = None,
    group_by: str = "day",
) -> list[dict]:
    """Aggregate ledger rows by `group_by` period.

    Returns a list of dicts ordered by period ascending:
      {period, namespace, doc_count, chunk_count, estimated_tokens,
       estimated_cost_usd, batch_count}

    `group_by` accepts "day" | "week" | "month".
    """
    rows = _read_ledger(namespace=namespace, since=since)
    buckets: dict[str, dict] = {}
    for row in rows:
        period = _period_key(row.get("ts", ""), group_by)
        ns = row.get("namespace", "unknown")
        key = f"{period}::{ns}"
        if key not in buckets:
            buckets[key] = {
                "period": period,
                "namespace": ns,
                "doc_count": 0,
                "chunk_count": 0,
                "estimated_tokens": 0,
                "estimated_cost_usd": 0.0,
                "batch_count": 0,
            }
        b = buckets[key]
        b["doc_count"] += int(row.get("doc_count", 0))
        b["chunk_count"] += int(row.get("chunk_count", 0))
        b["estimated_tokens"] += int(row.get("estimated_tokens", 0))
        b["estimated_cost_usd"] += float(row.get("estimated_cost_usd", 0.0))
        b["batch_count"] += 1
    return sorted(buckets.values(), key=lambda x: (x["period"], x["namespace"]))


def total(
    namespace: str | None = None,
    since: str | None = None,
) -> dict:
    """Summarise all ledger rows into one aggregate dict.

    Returns:
      {namespace (None | str), since (None | str), doc_count, chunk_count,
       estimated_tokens, estimated_cost_usd, batch_count, first_ts, last_ts}
    """
    rows = _read_ledger(namespace=namespace, since=since)
    out: dict = {
        "namespace": namespace,
        "since": since,
        "doc_count": 0,
        "chunk_count": 0,
        "estimated_tokens": 0,
        "estimated_cost_usd": 0.0,
        "batch_count": len(rows),
        "first_ts": None,
        "last_ts": None,
    }
    ts_list: list[str] = []
    for row in rows:
        out["doc_count"] += int(row.get("doc_count", 0))
        out["chunk_count"] += int(row.get("chunk_count", 0))
        out["estimated_tokens"] += int(row.get("estimated_tokens", 0))
        out["estimated_cost_usd"] += float(row.get("estimated_cost_usd", 0.0))
        if row.get("ts"):
            ts_list.append(row["ts"])
    if ts_list:
        out["first_ts"] = min(ts_list)
        out["last_ts"] = max(ts_list)
    return out


# ── MCP registration ──────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.vector_costs_log_batch",
        description=(
            "Append a vector embedding cost row to "
            "`project-history/vector-costs.ndjson`. "
            "Called internally by cache modules (kb_embeddings, etc.) at the "
            "end of each refresh run. `cost_estimate_usd` is computed from the "
            "built-in cost table when omitted. "
            "KB § PATTERNS/common/vector-cost-tracking.md."
        ),
    )
    def _log_batch(
        namespace: str,
        model: str,
        doc_count: int,
        chunk_count: int,
        estimated_tokens: int,
        cost_estimate_usd: float | None = None,
        provider: str = "openai",
        source_ref: str | None = None,
    ) -> dict:
        return log_refresh_batch(
            namespace=namespace,
            model=model,
            doc_count=doc_count,
            chunk_count=chunk_count,
            estimated_tokens=estimated_tokens,
            cost_estimate_usd=cost_estimate_usd,
            provider=provider,
            source_ref=source_ref,
        )

    @server.tool(
        name="noctus.dev.vector_costs_report",
        description=(
            "Aggregate the vector embedding cost ledger by day/week/month. "
            "Optional `namespace` filter. Optional `since` ISO date filter "
            "(e.g. '2026-05-01'). `group_by`: 'day' | 'week' | 'month'. "
            "Returns [{period, namespace, doc_count, chunk_count, "
            "estimated_tokens, estimated_cost_usd, batch_count}]. "
            "KB § PATTERNS/common/vector-cost-tracking.md."
        ),
    )
    def _report(
        namespace: str | None = None,
        since: str | None = None,
        group_by: str = "day",
    ) -> list[dict]:
        return report(namespace=namespace, since=since, group_by=group_by)

    @server.tool(
        name="noctus.dev.vector_costs_total",
        description=(
            "Quick aggregate total of the vector embedding cost ledger. "
            "Optional `namespace` + `since` filters. "
            "Returns {namespace, since, doc_count, chunk_count, "
            "estimated_tokens, estimated_cost_usd, batch_count, "
            "first_ts, last_ts}. "
            "KB § PATTERNS/common/vector-cost-tracking.md."
        ),
    )
    def _total(
        namespace: str | None = None,
        since: str | None = None,
    ) -> dict:
        return total(namespace=namespace, since=since)


__all__ = [
    "LEDGER_PATH",
    "COST_PER_MILLION_TOKENS",
    "estimate_tokens",
    "estimate_cost",
    "log_refresh_batch",
    "report",
    "total",
    "register",
]
