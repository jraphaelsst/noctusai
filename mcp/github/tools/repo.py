"""github.repo.* tools — repository introspection.

`github.repo.view` — default branch / visibility / description. PURE
read, no confirm gate. Routes through the shared `gh.run_gh` seam.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import gh
from ..settings import get_settings
from ..types import RepoViewInput, RepoViewOutput

logger = logging.getLogger(__name__)

_FIELDS = "nameWithOwner,defaultBranchRef,description,isPrivate,url"


async def repo_view(args: dict) -> dict:
    inp = RepoViewInput(**args)
    s = get_settings()
    try:
        d = gh.run_gh(
            ["repo", "view", "--json", _FIELDS],
            gh_path=s.effective_gh_path,
            repo=inp.repo or s.default_repo,
            timeout=s.timeout_seconds,
        )
    except gh.GitHubCliError as e:
        return RepoViewOutput(error=typed_error(e)).model_dump()
    ref = d.get("defaultBranchRef") or {}
    return RepoViewOutput(
        nameWithOwner=d.get("nameWithOwner"),
        defaultBranch=ref.get("name") if isinstance(ref, dict) else None,
        description=d.get("description"),
        isPrivate=d.get("isPrivate"),
        url=d.get("url"),
    ).model_dump()


HANDLERS = {"github.repo.view": repo_view}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="github.repo.view",
            description="Repository metadata — default branch, visibility, "
            "description, URL. READ-ONLY.",
            inputSchema=RepoViewInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
