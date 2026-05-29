"""brief_similarity_radar — pre-dispatch radar: have we briefed this recently?
And: which agent's owns_kb is semantically closest to this brief?

Why this exists
    Two questions the architect repeatedly asks at dispatch time:
      1. "Did I dispatch something LIKE THIS in the last week? Could I
         consult that engineer's work instead of duplicating?"
      2. "Which specialist agent owns the territory this brief touches?
         backend-engineer? devops-engineer?"

    Today both are guessed manually. This module makes both mechanical:
    feed it a draft brief, it returns similar past briefs (F7a) + the
    best-match agent (F7b).

Composition
    F7a (similarity check) reads `brief_ledger` (the .ndjson) +
    `vectorize.embed_text` for cosine.
    F7b (agent routing) reads each agent's `owns_kb` centroid from the
    agent-context cache.

KB § CONTEXT/PATTERNS/common/brief-similarity-radar.md.
"""
from __future__ import annotations

from typing import Any

# Canonical cosine — single source at _embedding_corpus (N=7 consolidation).
from . import _embedding_corpus as _ec

_cosine = _ec.cosine


def _embed(text: str) -> list[float] | None:
    """Embed text via vectorize; namespace-tag for cost attribution."""
    if not text or not text.strip():
        return None
    try:
        from . import vectorize
        result = vectorize.embed_text(text, namespace="brief_similarity_radar")
        if result.get("ok") and "vector" in result:
            return result["vector"]
    except Exception:  # noqa: BLE001
        return None
    return None


def similarity_check(
    description: str,
    since_days: int = 7,
    top_k: int = 5,
    min_score: float = 0.5,
) -> dict[str, Any]:
    """Find past briefs semantically similar to a new draft.

    Args:
      description: the new brief's description text.
      since_days: window of past briefs to consider (default 7).
      top_k: max number of similar briefs to return.
      min_score: filter floor on cosine (default 0.5).

    Returns:
      {
        ok: bool,
        query: str,
        hits: [{slug, agent, ts, description, score}],
        message?: str,    # set on empty corpus / provider failure
      }
    """
    if not description or not description.strip():
        return {"ok": False, "error": "empty description"}
    try:
        from . import brief_ledger as bl
        entries = bl.query(since_days=since_days)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"brief_ledger unavailable: {e}"}
    if not entries:
        return {
            "ok": True, "query": description, "hits": [],
            "message": f"no briefs in the last {since_days} day(s)",
        }
    q_vec = _embed(description)
    if q_vec is None:
        return {
            "ok": True, "query": description, "hits": [],
            "message": "embedding provider unreachable",
        }
    scored: list[tuple[float, dict]] = []
    for e in entries:
        # Embed the past description (or excerpt if available).
        past_text = e.get("description") or e.get("full_brief_excerpt") or ""
        if not past_text.strip():
            continue
        past_vec = _embed(past_text)
        if past_vec is None:
            continue
        score = _cosine(q_vec, past_vec)
        if score < min_score:
            continue
        scored.append((score, {
            "slug": e.get("slug"),
            "agent": e.get("agent"),
            "ts": e.get("ts"),
            "description": past_text[:200],
            "score": score,
        }))
    scored.sort(key=lambda t: t[0], reverse=True)
    return {
        "ok": True,
        "query": description,
        "hits": [d for _, d in scored[:top_k]],
    }


def route_to_agent(
    description: str,
    target_files: list[str] | None = None,
) -> dict[str, Any]:
    """Suggest which specialist agent best fits a brief.

    Method: embed the brief description (+ optional target file paths as
    context) → compute cosine vs each agent's owns_kb centroid → rank.

    Centroid source: each agent's compact bundle from the agent-context
    cache concatenates the agent body + each owned_kb doc body. Embedding
    that bundle and using it as the agent's centroid gives a meaningful
    semantic locus for routing.

    Args:
      description: brief description.
      target_files: optional list of file paths (joined into description
        for additional context).

    Returns:
      {
        ok: bool,
        query: str,
        rankings: [{agent, score}],   # sorted desc
        suggested: str | None,
        message?: str,
      }
    """
    if not description or not description.strip():
        return {"ok": False, "error": "empty description"}
    combined = description
    if target_files:
        combined = combined + "\n" + "\n".join(target_files)
    try:
        from . import agent_context_cache as acc
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"agent_context_cache unavailable: {e}"}
    # Pull each agent's bundle; embed; score.
    try:
        agents = acc.list_agents()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"agent_context_cache.list_agents failed: {e}"}
    q_vec = _embed(combined)
    if q_vec is None:
        return {
            "ok": True, "query": description,
            "rankings": [], "suggested": None,
            "message": "embedding provider unreachable",
        }
    rankings: list[tuple[float, str]] = []
    for agent_name in agents:
        try:
            bundle = acc.lookup(agent_name)
        except Exception:  # noqa: BLE001
            continue
        if not (bundle or {}).get("ok"):
            continue
        body = bundle.get("body") or ""
        if not body.strip():
            continue
        agent_vec = _embed(body[:4000])  # cap to keep embed call light
        if agent_vec is None:
            continue
        rankings.append((_cosine(q_vec, agent_vec), agent_name))
    rankings.sort(key=lambda t: t[0], reverse=True)
    suggested = rankings[0][1] if rankings else None
    return {
        "ok": True,
        "query": description,
        "rankings": [{"agent": a, "score": s} for s, a in rankings],
        "suggested": suggested,
    }


# ── MCP registration ─────────────────────────────────────────────────────────
def register(server) -> None:
    @server.tool(
        name="noctus.dev.brief_similarity_check",
        description=(
            "Pre-dispatch radar: find past briefs semantically similar to "
            "a new draft. Reads the per-user brief_ledger; embeds + cosines "
            "the description vs. past entries in the time window (default "
            "7 days). Use to catch 'did I dispatch this last week?' before "
            "duplicating work. "
            "KB § CONTEXT/PATTERNS/common/brief-similarity-radar.md."
        ),
    )
    def _check(description: str, since_days: int = 7,
               top_k: int = 5, min_score: float = 0.5) -> dict:
        return similarity_check(description, since_days=since_days,
                                top_k=top_k, min_score=min_score)

    @server.tool(
        name="noctus.dev.brief_route_to_agent",
        description=(
            "Suggest which specialist agent best fits a brief by embedding "
            "the description (+ optional target files) and cosining vs. "
            "each agent's compact bundle (body + owns_kb docs). Returns "
            "ranked agents + the suggested top pick. Use BEFORE dispatch "
            "to avoid 'wrong agent' miss-routes."
        ),
    )
    def _route(description: str, target_files: list[str] | None = None) -> dict:
        return route_to_agent(description, target_files=target_files)


__all__ = ["similarity_check", "route_to_agent", "register"]
