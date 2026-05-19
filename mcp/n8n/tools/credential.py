"""n8n.credential.* tools — credential lifecycle (create / delete / schema).

So workflows can stop hard-coding secrets inline: a credential is
created once here, then referenced by id from a node.

Reads (no confirm gate): schema (discover a credential type's required
fields, e.g. `httpHeaderAuth`).
Writes (confirm-gated): create / delete.

**Deliberate omission — gated-capability honesty (CLAUDE.md §1).** The
n8n public API has NO list/get-credentials endpoint: credential secret
`data` is write-only by design (the instance never echoes a stored
secret back, not even to its own UI). We do NOT invent a
list/get/read tool — a fabricated "list credentials" would either lie
or leak. Discovery is limited to `schema` (the *shape* of a type, not
any stored value); the created id/name is returned at create time and
is the only handle the operator gets. There is no read-back.

Every tool routes through the single `api.request_json` HTTP seam
(tests patch `n8n.api.request_json`). API failure ⇒ a typed-error
envelope (`_kit.errors.typed_error`), never a fabricated success.

`api` is invoked via the module (`api.request_json`), NOT `from ..api
import request_json`, so a test `patch("n8n.api.request_json")` is
actually observed by these handlers.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error

from .. import api
from ..settings import get_settings
from ..types import (
    CredentialCreateInput,
    CredentialCreateOutput,
    CredentialDeleteInput,
    CredentialDeleteOutput,
    CredentialSchemaInput,
    CredentialSchemaOutput,
)

logger = logging.getLogger(__name__)


def _ctx() -> dict:
    """Shared request context from settings."""
    s = get_settings()
    return {
        "base_url": s.base_url or "",
        "api_key": s.api_key or "",
        "timeout": s.timeout_seconds,
    }


# ─── Reads (no confirm gate) ─────────────────────────────────────────────


async def credential_schema(args: dict) -> dict:
    inp = CredentialSchemaInput(**args)
    try:
        data = api.request_json(
            "GET", f"/credentials/schema/{inp.credential_type_name}", **_ctx()
        )
    except api.N8nApiError as e:
        return CredentialSchemaOutput(error=typed_error(e)).model_dump(
            by_alias=True
        )
    # by_alias keeps the LLM-facing wire key `schema` (the field is
    # `json_schema` only to avoid shadowing pydantic.BaseModel.schema).
    return CredentialSchemaOutput(
        credential_type_name=inp.credential_type_name,
        json_schema=data if isinstance(data, dict) else None,
    ).model_dump(by_alias=True)


# ─── Writes (confirm-gated) ──────────────────────────────────────────────


async def credential_create(args: dict) -> dict:
    inp = CredentialCreateInput(**args)
    if not inp.confirm:
        return CredentialCreateOutput(
            error=typed_error(
                api.ConfirmationRequiredError("n8n.credential.create")
            )
        ).model_dump()
    body = {"name": inp.name, "type": inp.type, "data": inp.data}
    try:
        data = api.request_json(
            "POST", "/credentials", body=body, **_ctx()
        )
    except api.N8nApiError as e:
        return CredentialCreateOutput(error=typed_error(e)).model_dump()
    # n8n echoes id/name/type/createdAt — NEVER the secret `data` back.
    return CredentialCreateOutput(
        id=str((data or {}).get("id")) if isinstance(data, dict) else None,
        name=(data or {}).get("name") if isinstance(data, dict) else inp.name,
        type=(data or {}).get("type") if isinstance(data, dict) else inp.type,
        created=True,
    ).model_dump()


async def credential_delete(args: dict) -> dict:
    inp = CredentialDeleteInput(**args)
    if not inp.confirm:
        return CredentialDeleteOutput(
            error=typed_error(
                api.ConfirmationRequiredError("n8n.credential.delete")
            )
        ).model_dump()
    try:
        api.request_json("DELETE", f"/credentials/{inp.id}", **_ctx())
    except api.N8nApiError as e:
        return CredentialDeleteOutput(
            id=inp.id, error=typed_error(e)
        ).model_dump()
    return CredentialDeleteOutput(id=inp.id, deleted=True).model_dump()


# ─── Registration (the _kit leaf-module contract) ────────────────────────


HANDLERS = {
    "n8n.credential.create": credential_create,
    "n8n.credential.delete": credential_delete,
    "n8n.credential.schema": credential_schema,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="n8n.credential.create",
            description="Create a credential (name/type/data) so a "
            "workflow node can reference it by id instead of hard-coding "
            "the secret inline. WRITE — confirm-gated (status 412 without "
            "confirm=true, no side-effect). n8n does NOT echo the secret "
            "`data` back; only id/name/type are returned. Use "
            "n8n.credential.schema first to discover the required `data` "
            "keys for a type.",
            inputSchema=CredentialCreateInput.model_json_schema(),
        ),
        Tool(
            name="n8n.credential.delete",
            description="Delete a credential by id. WRITE / "
            "HARD-TO-REVERSE (not API-undoable; the secret is gone) — "
            "confirm-gated (status 412 without confirm=true, no "
            "side-effect).",
            inputSchema=CredentialDeleteInput.model_json_schema(),
        ),
        Tool(
            name="n8n.credential.schema",
            description="Fetch the JSON schema for a credential type "
            "(e.g. 'httpHeaderAuth', 'httpBasicAuth') — discover the "
            "required `data` fields before n8n.credential.create. "
            "READ-ONLY. NOTE: there is NO list/get-credentials endpoint "
            "(n8n stores secrets write-only by design) — this is the "
            "only credential-discovery surface.",
            inputSchema=CredentialSchemaInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
