"""noctus.dev.agent_context_* — MCP wrappers over the agent-context cache.

Three tools mirror the keeper-pattern-cache surface (which is also wrapped
in `keeper_pattern.py` as the sibling drift-fix-on-contact landed):

  noctus.dev.agent_context(agent_name)             — return compact bundle
  noctus.dev.agent_context_refresh(force, agent_name) — re-populate
  noctus.dev.agent_context_list()                  — distinct agents in cache

KB § PATTERNS/agent-context-architecture.md.
"""
from __future__ import annotations

from . import agent_context_cache as acc


def register(server) -> None:
    @server.tool(
        name="noctus.dev.agent_context",
        description=(
            "Return the compact agent-context bundle for an agent — "
            "frontmatter + body + per-owned-KB compact extract (H1 + first "
            "paragraph + per-H2 first line). One round-trip replaces N "
            "Reads at dispatch time. Lazy-rebuilds if the live "
            "`bundle_sha = sha256(agent.md ∪ each owned_kb)` differs from "
            "the cached value (the cache self-heals on use). "
            "KB § PATTERNS/agent-context-architecture.md."
        ),
    )
    def _agent_context(agent_name: str) -> dict:
        return acc.lookup(agent_name)

    @server.tool(
        name="noctus.dev.agent_context_refresh",
        description=(
            "Re-populate the agent-context cache from "
            "`.claude/agents/*.md` + each agent's owned KB. Per-agent "
            "bundle_sha guard short-circuits in-sync agents (force=True "
            "rebuilds anyway). `agent_name=...` limits scope to one agent. "
            "Auto-run by pre-commit on agent.md OR owned-KB change."
        ),
    )
    def _refresh(force: bool = False, agent_name: str | None = None) -> dict:
        return acc.refresh(force=force, agent_name=agent_name)

    @server.tool(
        name="noctus.dev.agent_context_list",
        description=(
            "Distinct agent_names currently in the cache (the wired "
            "`.claude/agents/*.md` set). Rebuilds the cache if missing."
        ),
    )
    def _list() -> list[str]:
        return acc.list_agents()


__all__ = ["register"]
