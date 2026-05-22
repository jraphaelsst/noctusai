"""supabase.migration.* tools — migration history list / apply.

Reads (no gate): list (`GET /v1/projects/{ref}/database/migrations`).
Writes (confirm-gated): apply (`POST .../database/migrations`) — runs
DDL/SQL against the live database AND records it in the migration
history.

The migrations endpoints are STABLE in the Supabase Management API v1
OpenAPI spec (verified 2026-05-21 against
`https://api.supabase.com/api/v1-json`: GET + POST on
`/v1/projects/{ref}/database/migrations`) — so they are wrapped in v1
(`db.query` also covers ad-hoc DDL, but a recorded migration is the
right tool when you want it in the history).

Every tool routes through the single `api.request_json` HTTP seam (tests
patch `supabase.api.request_json`). API failure ⇒ a typed-error
envelope, never a fabricated success.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    MigrationApplyInput,
    MigrationApplyOutput,
    MigrationListInput,
    MigrationListOutput,
)

logger = logging.getLogger(__name__)


def _migrations_base(ref: str) -> str:
    return f"/v1/projects/{ref}/database/migrations"


def _ctx() -> dict:
    s = get_settings()
    return {
        "access_token": s.access_token or "",
        "base_url": s.base_url or "",
        "timeout": s.timeout_seconds,
    }


def _resolve_ref(passed: str | None) -> tuple[str, dict | None]:
    """Resolve the project ref reading THIS module's `get_settings` (so a
    test patching `supabase.tools.migration.get_settings` is honoured);
    render any error as the typed-error dict. Shared precedence/424 logic
    lives in `api.resolve_ref`."""
    ref, err = api.resolve_ref(get_settings(), passed)
    return ref, (typed_error(err) if err else None)


async def migration_list(args: dict) -> dict:
    inp = MigrationListInput(**args)
    ref, err = _resolve_ref(inp.project_ref)
    if err:
        return MigrationListOutput(error=err).model_dump()
    try:
        data = api.request_json("GET", _migrations_base(ref), **_ctx())
    except api.SupabaseApiError as e:
        return MigrationListOutput(error=typed_error(e)).model_dump()
    return MigrationListOutput(migrations=data, ok=True).model_dump()


async def migration_apply(args: dict) -> dict:
    inp = MigrationApplyInput(**args)
    if not inp.confirm:
        return MigrationApplyOutput(
            error=typed_error(api.ConfirmationRequiredError(
                "supabase.migration.apply",
                "runs migration SQL against the LIVE database and records "
                "it in the migration history",
            )),
        ).model_dump()
    ref, err = _resolve_ref(inp.project_ref)
    if err:
        return MigrationApplyOutput(error=err).model_dump()
    body: dict = {"query": inp.query}
    if inp.name is not None:
        body["name"] = inp.name
    try:
        data = api.request_json(
            "POST", _migrations_base(ref), body=body, **_ctx()
        )
    except api.SupabaseApiError as e:
        return MigrationApplyOutput(error=typed_error(e)).model_dump()
    return MigrationApplyOutput(ok=True, result=data).model_dump()


HANDLERS = {
    "supabase.migration.list": migration_list,
    "supabase.migration.apply": migration_apply,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(name="supabase.migration.list",
             description="List the applied migrations on the project. "
             "READ-ONLY. Uses project_ref (arg or SUPABASE_PROJECT_REF).",
             inputSchema=MigrationListInput.model_json_schema()),
        Tool(name="supabase.migration.apply",
             description="Apply + record a database migration (runs SQL "
             "against the LIVE database). WRITE — confirm-gated (412).",
             inputSchema=MigrationApplyInput.model_json_schema()),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
