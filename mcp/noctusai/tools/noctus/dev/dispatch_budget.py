"""Per-dispatch token-budget telemetry — durable audit ledger.

Why this exists
    Every engineer dispatch consumes tokens (input prompt + output). Without
    instrumentation, cost is invisible: no per-agent breakdown, no trend over
    time, no budget gate. This module is the manual-log path for F11 of the
    automation-orchestration-followup roadmap. Auto-capture is deferred until
    the harness exposes dispatch lifecycle hooks.

Architecture
    - Durable source-of-truth: `project-history/dispatch-budget.ndjson` (committed,
      sibling of auto-improvement.ndjson + vector-costs.ndjson).
    - One NDJSON line per engineer dispatch.
    - `report()` + `summary()` aggregate on-the-fly from the ledger (no secondary
      cache — the ledger is small, scans are trivial).

Usage (manual log path — orchestrator calls after each engineer dispatch)
    from tools.noctus.dev.dispatch_budget import log_dispatch
    log_dispatch(
        agent="backend-engineer",
        slug="feat/r1-f11-dispatch-budget-telemetry",
        input_tokens=12345,
        output_tokens=3456,
        model="claude-sonnet-4-6",
        source_ref="session:2026-05-28",
    )

Auto-capture deferred
    The harness does not yet expose pre/post-dispatch lifecycle hooks for
    automatic token accounting. Until those hooks land (roadmap F11 open
    question), the orchestrator MANUALLY calls `log_dispatch` after each
    engineer dispatch, reading token counts from the agent's task JSONL
    (or from the `usage` block in the engineer's first-message response).

NDJSON schema (one line per dispatch):
    {
      "ts":             ISO-8601 UTC timestamp,
      "agent":          str ("backend-engineer" | "frontend-engineer" | ...),
      "slug":           str (branch / task slug, e.g. "feat/r1-f11-..."),
      "input_tokens":   int,
      "output_tokens":  int,
      "total_tokens":   int   (input + output, derived),
      "model":          str ("claude-sonnet-4-6" | "claude-opus-4-7" | ...),
      "source_ref":     str | null  (e.g. "session:2026-05-28")
    }

Depth: `KB § PATTERNS/common/dispatch-budget-telemetry.md`.
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
LEDGER_PATH = REPO_ROOT / "project-history" / "dispatch-budget.ndjson"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _window_since(window_days: int) -> str:
    """Return ISO-8601 string for `now - window_days`."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    return cutoff.isoformat()


# ── Public API ────────────────────────────────────────────────────────────────
def log_dispatch(
    agent: str,
    slug: str,
    input_tokens: int,
    output_tokens: int,
    model: str,
    source_ref: str | None = None,
) -> dict:
    """Append one NDJSON row to the dispatch-budget ledger.

    `total_tokens` is derived as input + output. Returns `{ok, path, row}`.
    """
    row: dict = {
        "ts": _now_iso(),
        "agent": agent,
        "slug": slug,
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "total_tokens": int(input_tokens) + int(output_tokens),
        "model": model,
        "source_ref": source_ref,
    }
    try:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        logger.debug(
            "dispatch_budget: logged dispatch agent=%s slug=%s tokens=%d",
            agent, slug, row["total_tokens"],
        )
        return {"ok": True, "path": str(LEDGER_PATH), "row": row}
    except OSError as exc:
        logger.error("dispatch_budget: failed to write ledger: %s", exc)
        return {"ok": False, "error": str(exc), "row": row}


def _read_ledger(
    agent: str | None = None,
    model: str | None = None,
    since: str | None = None,
) -> list[dict]:
    """Read + filter NDJSON rows from the ledger.

    `since` is an ISO date string (YYYY-MM-DD or full ISO-8601); rows whose
    `ts` field is < `since` are excluded. Malformed lines are silently skipped.
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
                logger.debug("dispatch_budget: skipping malformed line: %.80s", line)
                continue
            if agent is not None and row.get("agent") != agent:
                continue
            if model is not None and row.get("model") != model:
                continue
            if since is not None and row.get("ts", "") < since:
                continue
            rows.append(row)
    return rows


def report(
    agent: str | None = None,
    model: str | None = None,
    window_days: int = 7,
) -> list[dict]:
    """Aggregate ledger rows by (agent, model) within the window.

    Returns a list of dicts, one per (agent, model) pair, with:
      {agent, model, dispatch_count, input_tokens_sum, output_tokens_sum,
       total_tokens_sum, total_tokens_avg, total_tokens_p95, first_ts, last_ts}

    `window_days=0` means no window filter (all time).
    """
    since = _window_since(window_days) if window_days > 0 else None
    rows = _read_ledger(agent=agent, model=model, since=since)

    buckets: dict[str, dict] = {}
    for row in rows:
        a = row.get("agent", "unknown")
        m = row.get("model", "unknown")
        key = f"{a}::{m}"
        if key not in buckets:
            buckets[key] = {
                "agent": a,
                "model": m,
                "dispatch_count": 0,
                "input_tokens_sum": 0,
                "output_tokens_sum": 0,
                "total_tokens_sum": 0,
                "_total_list": [],
                "first_ts": None,
                "last_ts": None,
            }
        b = buckets[key]
        b["dispatch_count"] += 1
        b["input_tokens_sum"] += int(row.get("input_tokens", 0))
        b["output_tokens_sum"] += int(row.get("output_tokens", 0))
        total = int(row.get("total_tokens", 0)) or (
            int(row.get("input_tokens", 0)) + int(row.get("output_tokens", 0))
        )
        b["total_tokens_sum"] += total
        b["_total_list"].append(total)
        ts = row.get("ts")
        if ts:
            if b["first_ts"] is None or ts < b["first_ts"]:
                b["first_ts"] = ts
            if b["last_ts"] is None or ts > b["last_ts"]:
                b["last_ts"] = ts

    result = []
    for b in sorted(buckets.values(), key=lambda x: (x["agent"], x["model"])):
        totals = b.pop("_total_list")
        count = b["dispatch_count"]
        b["total_tokens_avg"] = round(b["total_tokens_sum"] / count, 1) if count else 0.0
        if totals:
            sorted_totals = sorted(totals)
            idx = int(0.95 * len(sorted_totals))
            b["total_tokens_p95"] = sorted_totals[min(idx, len(sorted_totals) - 1)]
        else:
            b["total_tokens_p95"] = 0
        result.append(b)
    return result


def summary(
    agent: str | None = None,
    model: str | None = None,
    window_days: int = 0,
) -> dict:
    """One-shot aggregate of all ledger rows.

    Returns:
      {agent (None | str), model (None | str), window_days,
       dispatch_count, input_tokens_sum, output_tokens_sum, total_tokens_sum,
       total_tokens_avg, total_tokens_p95, first_ts, last_ts}

    `window_days=0` means all-time (no cutoff).
    """
    since = _window_since(window_days) if window_days > 0 else None
    rows = _read_ledger(agent=agent, model=model, since=since)

    out: dict = {
        "agent": agent,
        "model": model,
        "window_days": window_days,
        "dispatch_count": len(rows),
        "input_tokens_sum": 0,
        "output_tokens_sum": 0,
        "total_tokens_sum": 0,
        "total_tokens_avg": 0.0,
        "total_tokens_p95": 0,
        "first_ts": None,
        "last_ts": None,
    }
    total_list: list[int] = []
    for row in rows:
        out["input_tokens_sum"] += int(row.get("input_tokens", 0))
        out["output_tokens_sum"] += int(row.get("output_tokens", 0))
        total = int(row.get("total_tokens", 0)) or (
            int(row.get("input_tokens", 0)) + int(row.get("output_tokens", 0))
        )
        out["total_tokens_sum"] += total
        total_list.append(total)
        ts = row.get("ts")
        if ts:
            if out["first_ts"] is None or ts < out["first_ts"]:
                out["first_ts"] = ts
            if out["last_ts"] is None or ts > out["last_ts"]:
                out["last_ts"] = ts

    if total_list:
        out["total_tokens_avg"] = round(out["total_tokens_sum"] / len(total_list), 1)
        sorted_totals = sorted(total_list)
        idx = int(0.95 * len(sorted_totals))
        out["total_tokens_p95"] = sorted_totals[min(idx, len(sorted_totals) - 1)]

    return out


# ── MCP registration ──────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.dispatch_budget_log",
        description=(
            "Append one dispatch token-budget row to "
            "`project-history/dispatch-budget.ndjson`. "
            "Called MANUALLY by the orchestrator after each engineer dispatch "
            "(auto-capture deferred until harness lifecycle hooks land). "
            "Required: agent, slug, input_tokens, output_tokens, model. "
            "Optional: source_ref (e.g. 'session:2026-05-28'). "
            "KB § PATTERNS/common/dispatch-budget-telemetry.md."
        ),
    )
    def _log(
        agent: str,
        slug: str,
        input_tokens: int,
        output_tokens: int,
        model: str,
        source_ref: str | None = None,
    ) -> dict:
        return log_dispatch(
            agent=agent,
            slug=slug,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            source_ref=source_ref,
        )

    @server.tool(
        name="noctus.dev.dispatch_budget_report",
        description=(
            "Aggregate the dispatch-budget ledger by (agent, model) within a "
            "rolling window. `window_days` defaults to 7; set to 0 for all-time. "
            "Optional `agent` and `model` filters. "
            "Returns [{agent, model, dispatch_count, input_tokens_sum, "
            "output_tokens_sum, total_tokens_sum, total_tokens_avg, "
            "total_tokens_p95, first_ts, last_ts}]. "
            "KB § PATTERNS/common/dispatch-budget-telemetry.md."
        ),
    )
    def _report(
        agent: str | None = None,
        model: str | None = None,
        window_days: int = 7,
    ) -> list[dict]:
        return report(agent=agent, model=model, window_days=window_days)

    @server.tool(
        name="noctus.dev.dispatch_budget_summary",
        description=(
            "One-shot aggregate of the dispatch-budget ledger. "
            "`window_days=0` means all-time (no cutoff). "
            "Optional `agent` and `model` filters. "
            "Returns {agent, model, window_days, dispatch_count, "
            "input_tokens_sum, output_tokens_sum, total_tokens_sum, "
            "total_tokens_avg, total_tokens_p95, first_ts, last_ts}. "
            "KB § PATTERNS/common/dispatch-budget-telemetry.md."
        ),
    )
    def _summary(
        agent: str | None = None,
        model: str | None = None,
        window_days: int = 0,
    ) -> dict:
        return summary(agent=agent, model=model, window_days=window_days)


__all__ = [
    "LEDGER_PATH",
    "log_dispatch",
    "report",
    "summary",
    "register",
]
