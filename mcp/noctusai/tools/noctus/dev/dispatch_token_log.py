"""dispatch_token_log — manual per-dispatch token-budget logging.

Why this exists
    The original diagnostic wanted automatic per-dispatch token tracking:
    "per-dispatch tokens consumed, time-to-completion, did it land?"

    Claude Code's harness does NOT expose dispatch lifecycle hooks we
    can attach to. Automatic logging requires harness-side support we
    don't control.

    This module ships the MANUAL log path: the architect (after each
    dispatch) logs the slug + duration + estimated tokens + outcome.
    Trend analysis is the architect's responsibility for now; when the
    harness exposes hooks, swap the manual call for an automatic one.

What it logs
    Each entry: ts, slug, agent, duration_minutes, estimated_tokens,
    outcome (landed | drift-found | failed | escalated), notes.

Where it lives
    `project-history/dispatch-budget.ndjson` (committed; trend history
    is shared methodology signal).

Status
    Manual-instrument path. The automatic path is a future enhancement
    deferred until harness exposes session lifecycle hooks.

KB § CONTEXT/PATTERNS/common/dispatch-token-log.md.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_OUTCOMES = frozenset({"landed", "drift-found", "failed", "escalated"})


def _ledger_path() -> Path:
    from settings import REPO_ROOT
    return REPO_ROOT / "project-history" / "dispatch-budget.ndjson"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_completion(
    slug: str,
    agent: str,
    duration_minutes: float,
    estimated_tokens: int | None = None,
    outcome: str = "landed",
    notes: str | None = None,
) -> dict[str, Any]:
    """Log a completed dispatch.

    Args:
      slug: worktree slug / branch name.
      agent: specialist name.
      duration_minutes: wall-clock duration in minutes (architect-observed).
      estimated_tokens: optional token estimate (sum of brief + return + any
        intermediate work; architect's best guess).
      outcome: 'landed' | 'drift-found' | 'failed' | 'escalated'.
      notes: optional free-form notes.

    Returns: `{ok, entry, ledger_path}`.
    """
    if outcome not in VALID_OUTCOMES:
        return {
            "ok": False,
            "error": f"outcome must be one of {sorted(VALID_OUTCOMES)}; got {outcome!r}",
        }
    if not slug or not slug.strip():
        return {"ok": False, "error": "slug is required"}
    if duration_minutes < 0:
        return {"ok": False, "error": "duration_minutes must be >= 0"}
    entry = {
        "ts": _now_iso(),
        "slug": slug.strip(),
        "agent": agent,
        "duration_minutes": float(duration_minutes),
        "estimated_tokens": int(estimated_tokens) if estimated_tokens is not None else None,
        "outcome": outcome,
        "notes": notes,
    }
    path = _ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"write failed: {str(e)[:200]}"}
    try:
        from settings import REPO_ROOT
        rel = str(path.relative_to(REPO_ROOT))
    except (ImportError, ValueError):
        rel = str(path)
    return {"ok": True, "entry": entry, "ledger_path": rel}


def summary(
    agent: str | None = None,
    since: str | None = None,
) -> dict[str, Any]:
    """Aggregate dispatch budget rows.

    Args:
      agent: filter to one specialist.
      since: ISO date prefix; rows with ts < since excluded.

    Returns:
      {
        ok: True,
        total_dispatches: int,
        by_outcome: {outcome: count},
        by_agent: {agent: {dispatches, avg_minutes, avg_tokens}},
        total_estimated_tokens: int,
        landed_rate: float,        # landed / total
      }
    """
    path = _ledger_path()
    if not path.exists():
        return {
            "ok": True, "total_dispatches": 0,
            "by_outcome": {}, "by_agent": {},
            "total_estimated_tokens": 0, "landed_rate": 0.0,
            "message": "no dispatches logged yet",
        }
    by_outcome: dict[str, int] = {}
    by_agent_raw: dict[str, list[dict]] = {}
    total_tokens = 0
    total = 0
    landed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = entry.get("ts", "")
        if since and ts < since:
            continue
        a = entry.get("agent", "?")
        if agent and a != agent:
            continue
        oc = entry.get("outcome", "?")
        total += 1
        by_outcome[oc] = by_outcome.get(oc, 0) + 1
        if oc == "landed":
            landed += 1
        tokens = entry.get("estimated_tokens") or 0
        total_tokens += tokens
        by_agent_raw.setdefault(a, []).append(entry)
    by_agent: dict[str, dict[str, Any]] = {}
    for a, entries in by_agent_raw.items():
        n = len(entries)
        durs = [e["duration_minutes"] for e in entries if e.get("duration_minutes") is not None]
        toks = [e["estimated_tokens"] for e in entries if e.get("estimated_tokens") is not None]
        by_agent[a] = {
            "dispatches": n,
            "avg_minutes": round(sum(durs) / len(durs), 2) if durs else None,
            "avg_tokens": int(sum(toks) / len(toks)) if toks else None,
        }
    return {
        "ok": True,
        "total_dispatches": total,
        "by_outcome": by_outcome,
        "by_agent": by_agent,
        "total_estimated_tokens": total_tokens,
        "landed_rate": round(landed / total, 3) if total else 0.0,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.dispatch_log_completion",
        description=(
            "Manually log a completed dispatch: slug + agent + duration "
            "+ estimated tokens + outcome (landed|drift-found|failed|"
            "escalated) + optional notes. Appends to "
            "project-history/dispatch-budget.ndjson. Manual instrumentation "
            "path; automatic harness-hook variant deferred until Claude "
            "Code exposes dispatch lifecycle. "
            "KB § CONTEXT/PATTERNS/common/dispatch-token-log.md."
        ),
    )
    def _log(slug: str, agent: str, duration_minutes: float,
             estimated_tokens: int | None = None,
             outcome: str = "landed",
             notes: str | None = None) -> dict:
        return log_completion(slug, agent, duration_minutes,
                              estimated_tokens=estimated_tokens,
                              outcome=outcome, notes=notes)

    # NOTE (2026-08-31, tool-name-uniqueness triage): this module and
    # `dispatch_budget.py` BOTH declared `name="noctus.dev.dispatch_budget_summary"`.
    # `dispatch_budget.register` runs before `dispatch_token_log.register`
    # in `register_all` (`tools/noctus/dev/__init__.py`), so
    # `dispatch_budget.py`'s (agent, model, window_days) token-sum
    # aggregation — over the {agent, slug, input_tokens, output_tokens,
    # model, source_ref} entry shape written by `dispatch_budget_log` —
    # was the live tool; THIS (agent, since) outcome/duration aggregation
    # — over the DIFFERENT {slug, agent, duration_minutes,
    # estimated_tokens, outcome, notes} entry shape written by
    # `log_completion` above — was silently dead code registered a
    # second time under the same name. Both modules read/write the SAME
    # ledger file (`project-history/dispatch-budget.ndjson`) with two
    # DIFFERENT row schemas — a real, separate drift worth flagging (see
    # the delivery-note drift-found). Not behaviourally equivalent, so
    # renamed rather than deleted per the no-silent-behavior-change rule:
    # the winning name's semantics are untouched; this one keeps its
    # capability under an honest, non-colliding name that pairs with the
    # already-unique `noctus.dev.dispatch_log_completion` tool above.
    @server.tool(
        name="noctus.dev.dispatch_completion_summary",
        description=(
            "Aggregate dispatch-COMPLETION rows logged via "
            "`noctus.dev.dispatch_log_completion` (the {duration_minutes, "
            "estimated_tokens, outcome} manual-log shape — a DIFFERENT "
            "entry schema than `noctus.dev.dispatch_budget_summary`, "
            "though both read the same "
            "`project-history/dispatch-budget.ndjson` file). Returns "
            "total_dispatches, by_outcome counts, by_agent {dispatches, "
            "avg_minutes, avg_tokens}, total_estimated_tokens, "
            "landed_rate. Optional `agent=<name>` + `since=<ISO date>` "
            "filters."
        ),
    )
    def _sum(agent: str | None = None, since: str | None = None) -> dict:
        return summary(agent=agent, since=since)


__all__ = ["log_completion", "summary", "register"]
