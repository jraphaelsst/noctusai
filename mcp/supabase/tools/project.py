"""supabase.project.* tools — project list / inspect.

Reads (no gate): list / get.

Every tool routes through the single `api.request_json` HTTP seam (tests
patch `supabase.api.request_json`). API failure ⇒ a typed-error
envelope, never a fabricated success. `api` is invoked via the module so
`patch("supabase.api.request_json")` is observed.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    ProjectGetInput,
    ProjectGetOutput,
    ProjectListInput,
    ProjectListOutput,
)

logger = logging.getLogger(__name__)

_PROJECTS_BASE = "/v1/projects"


def _ctx() -> dict:
    s = get_settings()
    return {
        "access_token": s.access_token or "",
        "base_url": s.base_url or "",
        "timeout": s.timeout_seconds,
    }


def _resolve_ref(passed: str | None) -> tuple[str, dict | None]:
    """Resolve the project ref reading THIS module's `get_settings` (so a
    test patching `supabase.tools.project.get_settings` is honoured), then
    render any error as the typed-error dict. Delegates the ref-precedence
    + 424-on-missing logic to the shared pure `api.resolve_ref`."""
    ref, err = api.resolve_ref(get_settings(), passed)
    return ref, (typed_error(err) if err else None)


# ─── Reads ───────────────────────────────────────────────────────────────


async def project_list(args: dict) -> dict:
    ProjectListInput(**args)
    try:
        data = api.request_json("GET", _PROJECTS_BASE, **_ctx())
    except api.SupabaseApiError as e:
        return ProjectListOutput(error=typed_error(e)).model_dump()
    return ProjectListOutput(
        projects=data if isinstance(data, list) else []
    ).model_dump()


async def project_get(args: dict) -> dict:
    inp = ProjectGetInput(**args)
    ref, err = _resolve_ref(inp.project_ref)
    if err:
        return ProjectGetOutput(error=err).model_dump()
    try:
        data = api.request_json("GET", f"{_PROJECTS_BASE}/{ref}", **_ctx())
    except api.SupabaseApiError as e:
        return ProjectGetOutput(error=typed_error(e)).model_dump()
    return ProjectGetOutput(
        project=data if isinstance(data, dict) else None
    ).model_dump()


HANDLERS = {
    "supabase.project.list": project_list,
    "supabase.project.get": project_get,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="supabase.project.list",
             description="List the projects on the account. READ-ONLY. "
             "Not project-scoped (needs only the access token).",
             inputSchema=ProjectListInput.model_json_schema()),
        Tool(name="supabase.project.get",
             description="Inspect one project — status/region/organization/"
             "database host. READ-ONLY. Uses project_ref (arg or "
             "SUPABASE_PROJECT_REF).",
             inputSchema=ProjectGetInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
