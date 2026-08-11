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
      "estimated_tokens":     int,             # len//4 (or tiktoken) heuristic
      "estimated_cost_usd":   float,
      "actual_tokens":        int | null,      # provider ground truth (usage.total_tokens)
      "actual_cost_usd":      float | null,    # real-token-derived cost
      "source_ref":           str | null       (e.g. "session:2026-05-26")
    }

Real vs. estimated
    `actual_*` carry the provider's reported `usage.total_tokens`, captured via
    `_embedding_corpus.capture_embedding_usage()`. They sit ALONGSIDE the
    estimate so `report()`/`total()` expose estimate-vs-actual drift — the
    signal that calibrates future production-cost estimates. Pre-existing rows
    (and the fake provider, which reports no usage) read back as null.

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
#: The DURABLE, git-tracked ledger. Written by EXACTLY ONE thing: `drain_spool()`,
#: called from the pre-commit hook. Never appended to directly by a running tool —
#: see SPOOL_PATH for why.
LEDGER_PATH = REPO_ROOT / "project-history" / "vector-costs.ndjson"

#: The UNTRACKED write-ahead spool (gitignored). Every cost row lands here first.
#:
#: WHY (2026-08-11, replaces the push-time auto-commit): cost rows are appended as
#: a side-effect of work whose timing we do not control — most of all the pre-push
#: embedding refreshes, which run AFTER the last commit and after the push refs are
#: already negotiated. Appending those straight into a TRACKED file left it dirty at
#: a moment when nothing could commit it, so the hook swept it into a follow-up
#: `chore(cost-log)` commit. That commit could not join the push that created it, so
#: it rode the NEXT push — moving the branch tip and CANCELLING the in-flight CI run
#: for the sha that actually mattered (`concurrency: cancel-in-progress`). Five runs
#: died that way in one session; the churn also produced 20+ ledger-only commits.
#:
#: The invariant that fixes it: **the tracked ledger only ever changes inside a real
#: commit.** Writes go to this untracked spool at any time (a dirty untracked file is
#: invisible to `git status --porcelain` on tracked paths, to CI, and to drift scans);
#: pre-commit drains the spool into the ledger and stages it, so the rows ride along
#: with whatever is being committed — folded in, never a commit of their own.
#: Readers concatenate both, so an un-drained row is never missing from a report.
#: KB § PATTERNS/common/vector-cost-tracking.md § Fold-into-commit.
SPOOL_PATH = REPO_ROOT / "project-history" / ".vector-costs-spool.ndjson"

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
    actual_tokens: int | None = None,
    actual_cost_usd: float | None = None,
) -> dict:
    """Append one NDJSON row to the vector-costs ledger.

    If `cost_estimate_usd` is None it is derived from `estimated_tokens` and
    the built-in cost table.

    `actual_tokens` / `actual_cost_usd` carry the GROUND TRUTH from the
    provider's API response (captured via `_embedding_corpus.capture_embedding_usage`).
    When `actual_tokens` is given and `actual_cost_usd` is None, the cost is
    derived from the real token count + the cost table. Both are recorded
    ALONGSIDE the estimate so `report()` can surface estimate-vs-actual drift
    (the signal that calibrates future production estimates). Older rows
    without these fields read back as `None` — fully back-compatible.

    Returns `{ok, path, row}`.
    """
    if cost_estimate_usd is None:
        cost_estimate_usd = estimate_cost(estimated_tokens, model)

    if actual_tokens is not None and actual_cost_usd is None:
        actual_cost_usd = estimate_cost(actual_tokens, model)

    row: dict = {
        "ts": _now_iso(),
        "namespace": namespace,
        "model": model,
        "provider": provider,
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "estimated_tokens": estimated_tokens,
        "estimated_cost_usd": cost_estimate_usd,
        "actual_tokens": actual_tokens,
        "actual_cost_usd": actual_cost_usd,
        "source_ref": source_ref,
    }
    # Always the SPOOL, never the tracked ledger — see SPOOL_PATH. The caller may
    # be running at any point in the git lifecycle (mid-session, or inside pre-push
    # after the refs are negotiated); only pre-commit is allowed to move a row into
    # the tracked file, because only there can it ride inside a real commit.
    try:
        SPOOL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SPOOL_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        logger.debug(
            "vector_costs: spooled batch ns=%s chunks=%d tokens=%d cost=%.6f",
            namespace, chunk_count, estimated_tokens, cost_estimate_usd,
        )
        return {"ok": True, "path": str(SPOOL_PATH), "spooled": True, "row": row}
    except OSError as exc:
        logger.error("vector_costs: failed to write cost spool: %s", exc)
        return {"ok": False, "error": str(exc), "row": row}


def drain_spool() -> dict:
    """Fold every spooled cost row into the tracked ledger; empty the spool.

    The ONLY writer of `LEDGER_PATH`. Called from the pre-commit hook (which then
    `git add`s the ledger), so spooled rows land inside a real commit instead of
    forcing a ledger-only commit of their own. Idempotent and safe to call when the
    spool is absent or empty — that is the common case.

    Ordering: rows are appended in spool order, which is write order. The ledger is
    an append-only time series; `report()` sorts by `ts`, so a drain that interleaves
    with an older ledger tail is still read correctly.

    Crash-safety: the ledger append is flushed BEFORE the spool is truncated, so an
    interruption can at worst duplicate a row (harmless for cost telemetry) and can
    never lose one.

    Returns `{ok, drained, ledger, spool}`; `drained` is the row count folded in.
    """
    if not SPOOL_PATH.exists():
        return {"ok": True, "drained": 0, "ledger": str(LEDGER_PATH), "spool": str(SPOOL_PATH)}
    try:
        spooled = [ln for ln in SPOOL_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not spooled:
            SPOOL_PATH.unlink(missing_ok=True)
            return {"ok": True, "drained": 0, "ledger": str(LEDGER_PATH), "spool": str(SPOOL_PATH)}
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER_PATH.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(spooled) + "\n")
            fh.flush()
        SPOOL_PATH.unlink(missing_ok=True)
        logger.debug("vector_costs: drained %d spooled row(s) into the ledger", len(spooled))
        return {
            "ok": True,
            "drained": len(spooled),
            "ledger": str(LEDGER_PATH),
            "spool": str(SPOOL_PATH),
        }
    except OSError as exc:
        # Never fatal: this runs inside pre-commit and must not block a commit.
        logger.error("vector_costs: failed to drain cost spool: %s", exc)
        return {"ok": False, "error": str(exc), "drained": 0}


def _read_ledger(namespace: str | None = None, since: str | None = None) -> list[dict]:
    """Read + filter NDJSON rows from the ledger AND the not-yet-drained spool.

    Both are read so a report is never missing the rows that have been written but
    not yet folded into a commit (i.e. everything since the last commit). Without
    this, deferring the ledger write to commit-time would silently under-report
    recent cost — trading one problem for a quieter one.

    `since` is an ISO date string (YYYY-MM-DD or full ISO-8601); rows whose
    `ts` field is < `since` are excluded.
    """
    rows: list[dict] = []
    for path in (LEDGER_PATH, SPOOL_PATH):
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as fh:
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
       estimated_cost_usd, actual_tokens, actual_cost_usd,
       actual_batch_count, batch_count}

    `actual_*` sum only rows that carry provider ground-truth (newer rows);
    `actual_batch_count` is how many of the period's batches reported it, so a
    consumer can tell partial-coverage periods from fully-instrumented ones.

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
                "actual_tokens": 0,
                "actual_cost_usd": 0.0,
                "actual_batch_count": 0,
                "batch_count": 0,
            }
        b = buckets[key]
        b["doc_count"] += int(row.get("doc_count", 0))
        b["chunk_count"] += int(row.get("chunk_count", 0))
        b["estimated_tokens"] += int(row.get("estimated_tokens", 0))
        b["estimated_cost_usd"] += float(row.get("estimated_cost_usd", 0.0))
        if row.get("actual_tokens") is not None:
            b["actual_tokens"] += int(row.get("actual_tokens") or 0)
            b["actual_cost_usd"] += float(row.get("actual_cost_usd") or 0.0)
            b["actual_batch_count"] += 1
        b["batch_count"] += 1
    return sorted(buckets.values(), key=lambda x: (x["period"], x["namespace"]))


def total(
    namespace: str | None = None,
    since: str | None = None,
) -> dict:
    """Summarise all ledger rows into one aggregate dict.

    Returns:
      {namespace (None | str), since (None | str), doc_count, chunk_count,
       estimated_tokens, estimated_cost_usd, actual_tokens, actual_cost_usd,
       actual_batch_count, batch_count, first_ts, last_ts}

    `actual_*` sum only rows carrying provider ground truth; `actual_batch_count`
    reports how many batches were instrumented (vs the `batch_count` total).
    """
    rows = _read_ledger(namespace=namespace, since=since)
    out: dict = {
        "namespace": namespace,
        "since": since,
        "doc_count": 0,
        "chunk_count": 0,
        "estimated_tokens": 0,
        "estimated_cost_usd": 0.0,
        "actual_tokens": 0,
        "actual_cost_usd": 0.0,
        "actual_batch_count": 0,
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
        if row.get("actual_tokens") is not None:
            out["actual_tokens"] += int(row.get("actual_tokens") or 0)
            out["actual_cost_usd"] += float(row.get("actual_cost_usd") or 0.0)
            out["actual_batch_count"] += 1
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
            "Append a vector embedding cost row to the untracked write-ahead spool "
            "`project-history/.vector-costs-spool.ndjson`; the pre-commit hook folds "
            "spooled rows into the tracked `project-history/vector-costs.ndjson` "
            "ledger so they ride inside a real commit. "
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
        name="noctus.dev.vector_costs_drain_spool",
        description=(
            "Fold every row from the untracked cost spool "
            "`project-history/.vector-costs-spool.ndjson` into the tracked ledger "
            "`project-history/vector-costs.ndjson`, then empty the spool. "
            "Normally you do NOT call this by hand — the pre-commit hook runs it and "
            "stages the ledger, so cost rows ride inside a real commit instead of "
            "forcing a ledger-only `chore(cost-log)` commit (which moved the branch "
            "tip and cancelled in-flight CI). Idempotent; a no-op when the spool is "
            "empty. Returns {ok, drained, ledger, spool}. "
            "KB § PATTERNS/common/vector-cost-tracking.md § Fold-into-commit."
        ),
    )
    def _drain_spool() -> dict:
        return drain_spool()

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
    "SPOOL_PATH",
    "COST_PER_MILLION_TOKENS",
    "estimate_tokens",
    "estimate_cost",
    "log_refresh_batch",
    "drain_spool",
    "report",
    "total",
    "register",
]
