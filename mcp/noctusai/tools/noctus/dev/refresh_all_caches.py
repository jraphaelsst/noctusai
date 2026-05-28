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
from pathlib import Path
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


_ALL_CACHES = (
    "keeper-patterns",
    "agent-context",
    "auto-improvement",
    "kb-embeddings",
    "code-embeddings",
    # 6th + 7th (memory-embeddings, corpus-embeddings) being landed by a
    # parallel session — when that branch integrates first, they slot in
    # before noc-graph here.
    "noc-graph",  # 8th — structured graph mirror (KB § PATTERNS/architect/noc-graph.md)
)


def detect_stale_caches(repo_root: Path | None = None) -> list[str]:
    """Return the subset of caches whose source has drifted since last refresh.

    Lightweight check — opens each cache's freshness keeper and includes
    the cache name iff issues surface. NO refresh happens; this is the
    "only refresh what's actually stale" predicate.

    Args:
      repo_root: optional override (defaults to settings.REPO_ROOT).

    Returns: list of cache names in `_ALL_CACHES` order whose source
    differs from the cached state.
    """
    stale: list[str] = []
    # Each cache has its own freshness keeper in compliance.py. We
    # invoke each, and consider the cache stale if ANY issues surface.
    keeper_map: dict[str, str] = {
        "keeper-patterns":    "check_keeper_cache_freshness",
        "agent-context":      "check_agent_context_cache_freshness",
        "auto-improvement":   "check_auto_improvement_cache_freshness",
        "kb-embeddings":      "check_kb_vector_canonical",
        "code-embeddings":    "check_code_embeddings_cache_freshness",
        "noc-graph":          "check_noc_graph_cache_freshness",
    }
    try:
        from . import compliance as _c
    except Exception:  # noqa: BLE001
        return list(_ALL_CACHES)  # defensive: if compliance won't import, refresh everything
    for cache_name in _ALL_CACHES:
        keeper_name = keeper_map[cache_name]
        keeper_fn = getattr(_c, keeper_name, None)
        if keeper_fn is None:
            # Conservative: if no keeper, mark stale so caller has the option to refresh.
            stale.append(cache_name)
            continue
        try:
            issues = keeper_fn(repo_root) if repo_root else keeper_fn()
        except Exception:  # noqa: BLE001 — defensive
            stale.append(cache_name)
            continue
        if issues:
            stale.append(cache_name)
    return stale


def refresh_all(
    force: bool = False,
    skip: list[str] | None = None,
    only: list[str] | None = None,
    only_stale: bool = False,
) -> dict[str, Any]:
    """Refresh keeper-mirror caches.

    Selection (mutually exclusive, applied in this priority):
      1. `only=[...]`: refresh ONLY the listed caches; everything else
         skipped. Pass empty list to refresh nothing.
      2. `only_stale=True`: pre-check freshness keepers and refresh ONLY
         caches with surfaced drift. Skips clean ones entirely (no SHA
         walk overhead).
      3. Neither + `skip=[...]`: refresh every cache except those in skip.
      4. None of the above: refresh all 5 (each cache's internal SHA
         guard still skips in-sync content; only overhead is the walk).

    Args:
      force: pass `force=True` to each refreshed cache (rebuild even when
        source_sha matches). Combine with `only=[...]` for targeted force.
      skip: cache names to omit (used when `only` / `only_stale` not set).
      only: explicit allowlist; supersedes `skip`. Names must be in
        `_ALL_CACHES`; unknown names surface in warnings.
      only_stale: pre-check freshness keepers; refresh only stale caches.

    Returns: orchestration summary `{ok, ts, refreshed, failures,
    total_rows_written, warnings, skipped, selection_mode}`.
    """
    # Resolve selection.
    selection_mode = "all"
    if only is not None:
        # Specified: only refresh listed caches.
        valid = set(_ALL_CACHES)
        requested = set(only)
        unknown = requested - valid
        active = requested & valid
        selection_mode = "only"
    elif only_stale:
        stale = detect_stale_caches()
        active = set(stale)
        unknown = set()
        selection_mode = "only-stale"
    else:
        skip_set = set(skip or [])
        active = set(_ALL_CACHES) - skip_set
        unknown = set()
        selection_mode = "skip" if skip else "all"

    refreshed: dict[str, dict] = {}
    failures: list[str] = []
    warnings: list[str] = []
    total_rows = 0
    if unknown:
        warnings.append(
            f"unknown cache name(s) ignored: {sorted(unknown)}; "
            f"valid: {sorted(_ALL_CACHES)}"
        )
    skipped_names = sorted(set(_ALL_CACHES) - active)

    # 1. keeper-pattern cache
    if "keeper-patterns" in active:
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
    if "agent-context" in active:
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
    if "auto-improvement" in active:
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
    if "kb-embeddings" in active:
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
    if "code-embeddings" in active:
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

    # 8. noc-graph cache (structured graph mirror)
    if "noc-graph" in active:
        try:
            from . import noc_graph_cache as ng
            result, err = _refresh_one("noc-graph",
                                       lambda: ng.refresh(force=force))
            refreshed["noc-graph"] = result
            if err:
                failures.append("noc-graph")
                warnings.append(err)
            else:
                total_rows += result.get("rows_written", 0)
        except Exception as e:  # noqa: BLE001
            failures.append("noc-graph")
            warnings.append(f"noc-graph import: {str(e)[:120]}")

    return {
        "ok": not failures,
        "ts": _now_iso(),
        "refreshed": refreshed,
        "failures": failures,
        "total_rows_written": total_rows,
        "warnings": warnings,
        "skipped": skipped_names,
        "selection_mode": selection_mode,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.refresh_all_caches",
        description=(
            "Refresh keeper-mirror caches. SELECTION MODES (mutually exclusive):\n"
            "  • only=[...]:     refresh ONLY listed caches (most specified).\n"
            "  • only_stale=True: pre-check freshness keepers; refresh ONLY stale.\n"
            "  • skip=[...]:     refresh all except listed.\n"
            "  • (none):         refresh all 5 (each cache's source_sha guard "
            "                    still skips in-sync content; only orchestrator "
            "                    walk overhead).\n"
            "Valid cache names: keeper-patterns / agent-context / "
            "auto-improvement / kb-embeddings / code-embeddings.\n"
            "Optional `force=True` to rebuild even when source_sha matches.\n"
            "Returns per-cache outcome + failures + total_rows_written + "
            "selection_mode. KB § CONTEXT/PATTERNS/common/cache-auto-freshness.md."
        ),
    )
    def _refresh(force: bool = False,
                 skip: list[str] | None = None,
                 only: list[str] | None = None,
                 only_stale: bool = False) -> dict:
        return refresh_all(force=force, skip=skip, only=only, only_stale=only_stale)

    @server.tool(
        name="noctus.dev.detect_stale_caches",
        description=(
            "Pre-check freshness keepers across the 5 keeper-mirror caches; "
            "return the list of cache names whose source differs from the "
            "cached state. NO refresh happens — this is the predicate "
            "powering `refresh_all_caches(only_stale=True)`. Lightweight "
            "compared to a full refresh; useful for status displays."
        ),
    )
    def _detect() -> list[str]:
        return detect_stale_caches()


__all__ = ["refresh_all", "detect_stale_caches", "register"]
