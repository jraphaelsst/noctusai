"""noctus.dev.keeper_pattern_* — MCP wrappers over the keeper-pattern cache.

KB § PATTERNS/keeper-pattern-cache.md declared the three MCP tools as the
public API but only the CLI flags shipped (doc-tool-coherence drift).
Resolved on-contact while landing the sibling agent-context cache (Phase B):

  noctus.dev.keeper_pattern_lookup(keeper_name?, file_path?)
  noctus.dev.keeper_pattern_refresh(force=False)
  noctus.dev.keeper_pattern_list()

KB § PATTERNS/keeper-pattern-cache.md.
"""
from __future__ import annotations

from . import keeper_pattern_cache as kpc


def register(server) -> None:
    @server.tool(
        name="noctus.dev.keeper_pattern_lookup",
        description=(
            "Query the keeper-pattern cache (local SQLite mirror of "
            "`compliance.py`) by keeper-name substring AND/OR file path "
            "(e.g. `.claude/agents/devops-engineer.md` heuristic-maps to "
            "`agent_format` + `agent_archetype`). The "
            "keeper-check-before-doc'ing discipline starts here — query "
            "BEFORE authoring any gated doc so the keeper doesn't gate "
            "you. KB § PATTERNS/keeper-check-before-docing.md."
        ),
    )
    def _lookup(
        keeper_name: str | None = None, file_path: str | None = None
    ) -> list[dict]:
        return kpc.lookup(keeper_name=keeper_name, file_path=file_path)

    @server.tool(
        name="noctus.dev.keeper_pattern_refresh",
        description=(
            "Re-populate the keeper-pattern cache from `compliance.py` + "
            "colocated test fixtures. Idempotent — `force=False` "
            "short-circuits when `source_sha` matches. Auto-run by "
            "pre-commit on `compliance.py` change. Pass `worktree_path` "
            "when called from inside a git worktree so `compliance.py` is "
            "read from THAT worktree, not the MCP server's fixed-CWD "
            "primary — omitting it silently mirrors the stale primary copy."
        ),
    )
    def _refresh(force: bool = False, worktree_path: str | None = None) -> dict:
        return kpc.refresh(force=force, worktree_path=worktree_path)

    @server.tool(
        name="noctus.dev.keeper_pattern_list",
        description=(
            "Distinct keeper names currently in the cache (permanent "
            "rows). Rebuilds the cache if missing."
        ),
    )
    def _list() -> list[str]:
        return kpc.list_keepers()


__all__ = ["register"]
