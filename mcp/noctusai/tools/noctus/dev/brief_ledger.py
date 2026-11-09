"""brief_ledger — append-only ledger of dispatched-engineer briefs.

Why this exists
    Briefs are ephemeral today — the architect composes one, dispatches,
    integrates, moves on. Nothing remembers "what did we dispatch last
    week?" That makes the brief_similarity_radar (F7) impossible without
    a corpus to search.

    This ledger records every brief the architect composes via
    `engineer_brief_compose` (or any other surface that opts in by
    calling `brief_ledger.append`). Append-only, per-user, gitignored.

What's recorded
    For each brief: timestamp, slug (the worktree/branch slug the brief
    was for), agent (which specialist), target_files, description,
    and a content-hash for dedup.

Where it lives
    `.claude/cache/brief-ledger.ndjson` — gitignored (per-user noise,
    no shared methodology value).

Why gitignored
    Briefs are ephemeral architect work-product. Sharing across the team
    would surface noise. Per-user is the right scope; if cross-user
    aggregation becomes useful, that's a future evolution.

KB § CONTEXT/PATTERNS/common/brief-similarity-radar.md.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

from ._pii_guard import PiiLedgerError, assert_no_pii

logger = logging.getLogger(__name__)


def _ledger_path() -> Path:
    """Lazy REPO_ROOT lookup so test fixtures can monkeypatch."""
    from .cache_backend import cache_dir
    return cache_dir() / "brief-ledger.ndjson"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


MISS_OUTCOMES = frozenset({"miss", "rework"})


def append(
    slug: str,
    agent: str,
    target_files: list[str] | None,
    description: str,
    full_brief: str | None = None,
    meta: dict | None = None,
    outcome: str | None = None,
    ai_logger: Callable[..., dict] | None = None,
) -> dict[str, Any]:
    """Append a brief entry to the ledger.

    `outcome` in {"miss","rework"} also writes `kind="drift"` (with a
    `resolve_when`) to the auto-improvement ledger, attributed to `agent`;
    successes are not logged there. The logger result rides on the return
    as `ai` (failure -> `ai.ok False`, never swallowed). `ai_logger`
    defaults to `auto_improvement.log_entry`.

    Args:
      slug: worktree/branch slug (e.g. "w2-e3-code-embeddings").
      agent: specialist name (e.g. "backend-engineer").
      target_files: optional list of files the brief touched.
      description: short brief summary.
      full_brief: optional full brief text (for similarity matching).
      meta: optional structured metadata (e.g. {"top_k": 5}).

    Returns: `{ok, entry, ledger_path}`; never raises on the two EXPECTED
    refusals, which are explicit and distinguishable via `error_kind`:
      * `"disk"` -- OSError creating/writing the ledger (`ledger_path` named,
        warning logged). Advisory layer: the caller decides whether to block.
      * `"pii"`  -- the PII guard refused the entry (kind + field only, never
        the value); nothing is written.
    Anything else (programming errors) propagates -- no blanket catch.
    """
    path = _ledger_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": _now_iso(),
            "slug": slug,
            "agent": agent,
            "target_files": target_files or [],
            "description": description,
            "content_hash": _content_hash(full_brief or description),
            "meta": meta or {},
        }
        if outcome:
            entry["outcome"] = outcome
        if full_brief:
            entry["full_brief_excerpt"] = full_brief[:1000]
        assert_no_pii(entry, field="brief_ledger")
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except PiiLedgerError as e:
        return {"ok": False, "error_kind": "pii", "error": str(e)[:200]}
    except OSError as e:
        logger.warning("brief_ledger: disk failure writing %s: %s", path, e)
        return {"ok": False, "error_kind": "disk", "ledger_path": str(path),
                "error": f"{type(e).__name__}: {e}"[:200]}
    try:
        from settings import REPO_ROOT
        rel = str(path.relative_to(REPO_ROOT))
    except (ImportError, ValueError):
        rel = str(path)
    result: dict[str, Any] = {"ok": True, "entry": entry, "ledger_path": rel}
    if outcome in MISS_OUTCOMES:
        if ai_logger is None:
            from .auto_improvement import log_entry as ai_logger  # noqa: PLC0415
        try:
            result["ai"] = ai_logger(
                scope="scoped", kind="drift", target=f"brief:{slug}",
                description=f"brief outcome {outcome}: {description}"[:500],
                agent=agent, source_ref=f"brief:{slug}",
                resolve_when="manual:brief miss/rework triage")
        except Exception as exc:  # noqa: BLE001 — surfaced, not swallowed
            result["ai"] = {"ok": False, "error": f"ai_logger raised: {exc}"[:300]}
    return result


def query(
    since_days: int = 7,
    agent: str | None = None,
    slug_substring: str | None = None,
) -> list[dict[str, Any]]:
    """Read briefs within last N days; optionally filter by agent/slug.

    Args:
      since_days: window in days (default 7).
      agent: filter to one specialist name.
      slug_substring: filter slugs that contain this substring.

    Returns: list of entry dicts, newest first.
    """
    path = _ledger_path()
    if not path.exists():
        return []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("ts", "") < cutoff:
            continue
        if agent and entry.get("agent") != agent:
            continue
        if slug_substring and slug_substring not in entry.get("slug", ""):
            continue
        entries.append(entry)
    entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return entries


def list_recent(limit: int = 20) -> list[dict[str, Any]]:
    """Most-recent N entries regardless of age."""
    path = _ledger_path()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return entries[:limit]


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.brief_ledger_append",
        description=(
            "Append a brief entry to the architect's per-user brief ledger "
            "(.claude/cache/brief-ledger.ndjson, gitignored). Called by "
            "engineer_brief_compose at the end of compose; can also be "
            "called manually to record a brief composed elsewhere. "
            "KB § CONTEXT/PATTERNS/common/brief-similarity-radar.md."
        ),
    )
    def _append(slug: str, agent: str, description: str,
                target_files: list[str] | None = None,
                full_brief: str | None = None,
                meta: dict | None = None, outcome: str | None = None) -> dict:
        return append(slug, agent, target_files, description, full_brief, meta,
                      outcome=outcome)

    @server.tool(
        name="noctus.dev.brief_ledger_query",
        description=(
            "Read briefs from the per-user ledger filtered by time window "
            "and optionally agent / slug substring. Returns newest first."
        ),
    )
    def _query(since_days: int = 7, agent: str | None = None,
               slug_substring: str | None = None) -> list[dict]:
        return query(since_days=since_days, agent=agent,
                     slug_substring=slug_substring)

    @server.tool(
        name="noctus.dev.brief_ledger_recent",
        description=(
            "Most-recent N brief ledger entries regardless of age. Use for "
            "quick 'what did I dispatch lately?' lookups."
        ),
    )
    def _recent(limit: int = 20) -> list[dict]:
        return list_recent(limit=limit)


__all__ = ["append", "query", "list_recent", "register"]
