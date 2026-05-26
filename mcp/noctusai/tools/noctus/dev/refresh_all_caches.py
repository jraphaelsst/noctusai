"""refresh_all_caches — single orchestrator for the 5 keeper-mirror caches.

Why this exists
    Each cache has its own refresh tool. Calling them one at a time is
    error-prone (forget one, get partial freshness). This module fans
    out to all 5 in sequence + reports per-cache outcome.

What it refreshes (in order)
    1. keeper-patterns       (mirrors compliance.py)
    2. agent-context         (mirrors .claude/agents/<name>.md ∪ owned_kb)
    3. auto-improvement      (mirrors project-history/auto-improvement.ndjson)
    4. kb-embeddings         (vector cache over KNOWLEDGE-BASE/**/*.md)
    5. code-embeddings       (vector cache over code corpus)

Per-cache outcomes
    Each cache returns its own result dict. Combined:
      {
        ok: bool,                      # True iff every cache succeeded
        refreshed: {cache_name: result_dict},
        failures: [cache_name, ...],
        total_rows_written: int,
        warnings: [str, ...],          # graceful-degrade per cache
      }

When to use
    - After `git pull` (post-merge hook calls this).
    - After `git checkout <branch>` (post-checkout hook calls this).
    - Manually via `/refresh-caches` slash command or
      `noctus.dev.refresh_all_caches` MCP tool.
    - At the start of a long session to warm everything fresh.

What it does NOT do
    - It does NOT promote warnings to errors. Vector caches are advisory.
    - It does NOT purge orphan rows beyond what each refresh does
      internally (most do an all-or-nothing per doc).
    - It does NOT call live OpenAI when no provider is configured —
      embeddings caches degrade silently.

KB § CONTEXT/PATTERNS/common/cache-auto-freshness.md.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _refresh_one(name: str, refresh_call: Callable[[], dict]) -> tuple[dict, str | None]:
    """Run one cache's refresh. Returns (result_dict, error_str_or_None)."""
    try:
        result = refresh_call()
        if not isinstance(result, dict):
            return ({"ok": False, "raw": str(result)}, f"{name}: non-dict return")
        return (result, None)
    except Exception as e:  # noqa: BLE001
        return ({"ok": False, "error": str(e)[:200]}, f"{name}: {str(e)[:120]}")


def refresh_all(force: bool = False, skip: list[str] | None = None) -> dict[str, Any]:
    """Refresh every keeper-mirror cache.

    Args:
      force: pass `force=True` to each cache's refresh (rebuild even if
        source_sha matches).
      skip: optional list of cache names to skip (e.g.
        `["code-embeddings"]` when offline).

    Returns: orchestration summary.
    """
    skip_set = set(skip or [])
    refreshed: dict[str, dict] = {}
    failures: list[str] = []
    warnings: list[str] = []
    total_rows = 0

    # 1. keeper-pattern cache
    if "keeper-patterns" not in skip_set:
        try:
            from . import keeper_pattern_cache as kpc
            result, err = _refresh_one("keeper-patterns",
                                       lambda: kpc.refresh(force=force))
            refreshed["keeper-patterns"] = result
            if err:
                failures.append("keeper-patterns")
                warnings.append(err)
        except Exception as e:  # noqa: BLE001
            failures.append("keeper-patterns")
            warnings.append(f"keeper-patterns import: {str(e)[:120]}")

    # 2. agent-context cache
    if "agent-context" not in skip_set:
        try:
            from . import agent_context_cache as acc
            result, err = _refresh_one("agent-context",
                                       lambda: acc.refresh(force=force))
            refreshed["agent-context"] = result
            if err:
                failures.append("agent-context")
                warnings.append(err)
        except Exception as e:  # noqa: BLE001
            failures.append("agent-context")
            warnings.append(f"agent-context import: {str(e)[:120]}")

    # 3. auto-improvement cache
    if "auto-improvement" not in skip_set:
        try:
            from . import auto_improvement as ai
            result, err = _refresh_one("auto-improvement",
                                       lambda: ai.refresh(force=force))
            refreshed["auto-improvement"] = result
            if err:
                failures.append("auto-improvement")
                warnings.append(err)
        except Exception as e:  # noqa: BLE001
            failures.append("auto-improvement")
            warnings.append(f"auto-improvement import: {str(e)[:120]}")

    # 4. kb-embeddings cache
    if "kb-embeddings" not in skip_set:
        try:
            from . import kb_embeddings as kbe
            result, err = _refresh_one("kb-embeddings",
                                       lambda: kbe.refresh(force=force))
            refreshed["kb-embeddings"] = result
            if err:
                failures.append("kb-embeddings")
                warnings.append(err)
            else:
                total_rows += result.get("rows_written", 0)
        except Exception as e:  # noqa: BLE001
            failures.append("kb-embeddings")
            warnings.append(f"kb-embeddings import: {str(e)[:120]}")

    # 5. code-embeddings cache
    if "code-embeddings" not in skip_set:
        try:
            from . import code_embeddings as ce
            result, err = _refresh_one("code-embeddings",
                                       lambda: ce.refresh(force=force))
            refreshed["code-embeddings"] = result
            if err:
                failures.append("code-embeddings")
                warnings.append(err)
            else:
                total_rows += result.get("rows_written", 0)
        except Exception as e:  # noqa: BLE001
            failures.append("code-embeddings")
            warnings.append(f"code-embeddings import: {str(e)[:120]}")

    return {
        "ok": not failures,
        "ts": _now_iso(),
        "refreshed": refreshed,
        "failures": failures,
        "total_rows_written": total_rows,
        "warnings": warnings,
        "skipped": sorted(skip_set),
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.refresh_all_caches",
        description=(
            "Refresh all 5 keeper-mirror caches in sequence (keeper-patterns, "
            "agent-context, auto-improvement, kb-embeddings, code-embeddings). "
            "Optional `force=True` to rebuild even when source_sha matches. "
            "Optional `skip=[...]` to omit specific caches. Returns per-cache "
            "outcome + failures list + total_rows_written. Called by the "
            "post-merge / post-checkout git hooks for automatic freshness; "
            "also user-invocable via /refresh-caches. "
            "KB § CONTEXT/PATTERNS/common/cache-auto-freshness.md."
        ),
    )
    def _refresh(force: bool = False, skip: list[str] | None = None) -> dict:
        return refresh_all(force=force, skip=skip)


__all__ = ["refresh_all", "register"]
