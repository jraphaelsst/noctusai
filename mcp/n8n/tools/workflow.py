"""n8n.workflow.* tools — list / inspect / activate / deactivate.

Reads (no confirm gate): list / get.
Writes (confirm-gated): activate / deactivate.

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
    WorkflowActivateInput,
    WorkflowActiveStateOutput,
    WorkflowDeactivateInput,
    WorkflowGetInput,
    WorkflowGetOutput,
    WorkflowListInput,
    WorkflowListOutput,
    WorkflowCreateInput,
    WorkflowCreateOutput,
    WorkflowDeleteInput,
    WorkflowDeleteOutput,
    WorkflowSetTagsInput,
    WorkflowSetTagsOutput,
    WorkflowSummary,
    WorkflowUpdateInput,
    WorkflowUpdateOutput,
    TagSummary,
)

# n8n public-API PUT /workflows/{id} rejects additional properties — only
# these four keys are accepted. Activation/tags are managed via their own
# endpoints, not the workflow body.
_PUT_KEYS = ("name", "nodes", "connections", "settings")

logger = logging.getLogger(__name__)


def _ctx() -> dict:
    """Shared request context from settings."""
    s = get_settings()
    return {
        "base_url": s.base_url or "",
        "api_key": s.api_key or "",
        "timeout": s.timeout_seconds,
    }


def _summary(d: dict) -> WorkflowSummary:
    raw_tags = d.get("tags") or []
    tags = [
        t.get("name") if isinstance(t, dict) else str(t)
        for t in raw_tags
        if t is not None
    ]
    return WorkflowSummary(
        id=str(d.get("id", "")),
        name=d.get("name", ""),
        active=bool(d.get("active", False)),
        tags=[t for t in tags if t],
        createdAt=d.get("createdAt"),
        updatedAt=d.get("updatedAt"),
    )


# ─── Reads ───────────────────────────────────────────────────────────────


async def workflow_list(args: dict) -> dict:
    inp = WorkflowListInput(**args)
    try:
        data = api.request_json(
            "GET",
            "/workflows",
            params={
                "active": (
                    None if inp.active is None
                    else ("true" if inp.active else "false")
                ),
                "name": inp.name,
                "limit": inp.limit,
            },
            **_ctx(),
        )
    except api.N8nApiError as e:
        return WorkflowListOutput(error=typed_error(e)).model_dump()
    items = (data or {}).get("data", []) if isinstance(data, dict) else []
    return WorkflowListOutput(
        workflows=[_summary(d) for d in items],
        next_cursor=(data or {}).get("nextCursor")
        if isinstance(data, dict) else None,
    ).model_dump()


async def workflow_get(args: dict) -> dict:
    inp = WorkflowGetInput(**args)
    try:
        data = api.request_json(
            "GET", f"/workflows/{inp.id}", **_ctx()
        )
    except api.N8nApiError as e:
        return WorkflowGetOutput(error=typed_error(e)).model_dump()
    return WorkflowGetOutput(
        workflow=data if isinstance(data, dict) else None
    ).model_dump()


# ─── Writes (confirm-gated) ──────────────────────────────────────────────


async def _set_active(workflow_id: str, activate: bool) -> dict:
    verb = "activate" if activate else "deactivate"
    try:
        data = api.request_json(
            "POST", f"/workflows/{workflow_id}/{verb}", **_ctx()
        )
    except api.N8nApiError as e:
        return WorkflowActiveStateOutput(error=typed_error(e)).model_dump()
    active = (
        bool(data.get("active")) if isinstance(data, dict)
        and "active" in data else activate
    )
    return WorkflowActiveStateOutput(
        id=workflow_id, active=active, changed=True
    ).model_dump()


async def workflow_activate(args: dict) -> dict:
    inp = WorkflowActivateInput(**args)
    if not inp.confirm:
        return WorkflowActiveStateOutput(
            error=typed_error(
                api.ConfirmationRequiredError("n8n.workflow.activate")
            )
        ).model_dump()
    return await _set_active(inp.id, True)


async def workflow_deactivate(args: dict) -> dict:
    inp = WorkflowDeactivateInput(**args)
    if not inp.confirm:
        return WorkflowActiveStateOutput(
            error=typed_error(
                api.ConfirmationRequiredError("n8n.workflow.deactivate")
            )
        ).model_dump()
    return await _set_active(inp.id, False)


async def workflow_update(args: dict) -> dict:
    inp = WorkflowUpdateInput(**args)
    if not inp.confirm:
        return WorkflowUpdateOutput(
            error=typed_error(
                api.ConfirmationRequiredError("n8n.workflow.update")
            )
        ).model_dump()
    # Sanitize to the PUT-accepted keys (drop id/active/tags/timestamps/…
    # so n8n does not 400 on additional properties). `settings` must be
    # present; default to {} when the source omitted it.
    body = {k: inp.workflow[k] for k in _PUT_KEYS if k in inp.workflow}
    body.setdefault("settings", inp.workflow.get("settings") or {})
    try:
        data = api.request_json(
            "PUT", f"/workflows/{inp.id}", body=body, **_ctx()
        )
    except api.N8nApiError as e:
        return WorkflowUpdateOutput(error=typed_error(e)).model_dump()
    return WorkflowUpdateOutput(
        id=str((data or {}).get("id", inp.id))
        if isinstance(data, dict) else inp.id,
        name=(data or {}).get("name")
        if isinstance(data, dict) else body.get("name"),
        updated=True,
        sent_keys=sorted(body.keys()),
    ).model_dump()


async def workflow_create(args: dict) -> dict:
    inp = WorkflowCreateInput(**args)
    if not inp.confirm:
        return WorkflowCreateOutput(
            error=typed_error(
                api.ConfirmationRequiredError("n8n.workflow.create")
            )
        ).model_dump()
    body = {k: inp.workflow[k] for k in _PUT_KEYS if k in inp.workflow}
    body.setdefault("settings", inp.workflow.get("settings") or {})
    try:
        data = api.request_json("POST", "/workflows", body=body, **_ctx())
    except api.N8nApiError as e:
        return WorkflowCreateOutput(error=typed_error(e)).model_dump()
    return WorkflowCreateOutput(
        id=str((data or {}).get("id")) if isinstance(data, dict) else None,
        name=(data or {}).get("name") if isinstance(data, dict) else None,
        created=True,
    ).model_dump()


async def workflow_delete(args: dict) -> dict:
    inp = WorkflowDeleteInput(**args)
    if not inp.confirm:
        return WorkflowDeleteOutput(
            error=typed_error(
                api.ConfirmationRequiredError("n8n.workflow.delete")
            )
        ).model_dump()
    try:
        api.request_json("DELETE", f"/workflows/{inp.id}", **_ctx())
    except api.N8nApiError as e:
        return WorkflowDeleteOutput(
            id=inp.id, error=typed_error(e)
        ).model_dump()
    return WorkflowDeleteOutput(id=inp.id, deleted=True).model_dump()


def _tags(raw: object) -> list[TagSummary]:
    out: list[TagSummary] = []
    for t in raw or []:
        if isinstance(t, dict) and t.get("id"):
            out.append(TagSummary(id=str(t["id"]), name=t.get("name", "")))
    return out


async def workflow_set_tags(args: dict) -> dict:
    inp = WorkflowSetTagsInput(**args)
    if not inp.confirm:
        return WorkflowSetTagsOutput(
            error=typed_error(
                api.ConfirmationRequiredError("n8n.workflow.set_tags")
            )
        ).model_dump()
    # n8n PUT /workflows/{id}/tags body = [{"id": "<tagId>"}, ...]
    body_list = [{"id": tid} for tid in inp.tag_ids]
    try:
        data = api.request_json(
            "PUT", f"/workflows/{inp.id}/tags", body=body_list, **_ctx()
        )
    except api.N8nApiError as e:
        return WorkflowSetTagsOutput(
            id=inp.id, error=typed_error(e)
        ).model_dump()
    return WorkflowSetTagsOutput(
        id=inp.id,
        tags=_tags(data if isinstance(data, list) else (data or {}).get("tags")),
        updated=True,
    ).model_dump()


# ─── Registration (the _kit leaf-module contract) ────────────────────────


HANDLERS = {
    "n8n.workflow.list": workflow_list,
    "n8n.workflow.get": workflow_get,
    "n8n.workflow.activate": workflow_activate,
    "n8n.workflow.deactivate": workflow_deactivate,
    "n8n.workflow.update": workflow_update,
    "n8n.workflow.create": workflow_create,
    "n8n.workflow.delete": workflow_delete,
    "n8n.workflow.set_tags": workflow_set_tags,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="n8n.workflow.list",
            description="List workflows (optionally filter active/name). "
            "READ-ONLY.",
            inputSchema=WorkflowListInput.model_json_schema(),
        ),
        Tool(
            name="n8n.workflow.get",
            description="Fetch one workflow incl. nodes + connections "
            "(raw, full fidelity). READ-ONLY. `id` is the string from "
            "the workflow URL.",
            inputSchema=WorkflowGetInput.model_json_schema(),
        ),
        Tool(
            name="n8n.workflow.activate",
            description="Activate a workflow. WRITE — confirm-gated "
            "(status 412 without confirm=true, no side-effect).",
            inputSchema=WorkflowActivateInput.model_json_schema(),
        ),
        Tool(
            name="n8n.workflow.deactivate",
            description="Deactivate a workflow. WRITE — confirm-gated.",
            inputSchema=WorkflowDeactivateInput.model_json_schema(),
        ),
        Tool(
            name="n8n.workflow.update",
            description="Replace a workflow's definition (get → mutate → "
            "update). Sanitizes to name/nodes/connections/settings so "
            "n8n won't 400 on extra keys. WRITE / hard-to-reverse — "
            "confirm-gated (status 412 without confirm=true, no "
            "side-effect). Back up via n8n.workflow.get first.",
            inputSchema=WorkflowUpdateInput.model_json_schema(),
        ),
        Tool(
            name="n8n.workflow.create",
            description="Create a new workflow (name/nodes/connections/"
            "settings; extra keys auto-stripped). WRITE — confirm-gated.",
            inputSchema=WorkflowCreateInput.model_json_schema(),
        ),
        Tool(
            name="n8n.workflow.delete",
            description="Delete a workflow. WRITE / HARD-TO-REVERSE (not "
            "API-undoable) — confirm-gated. n8n.workflow.get first to "
            "keep a restore snapshot.",
            inputSchema=WorkflowDeleteInput.model_json_schema(),
        ),
        Tool(
            name="n8n.workflow.set_tags",
            description="Replace the tag set on a workflow (tag_ids from "
            "n8n.tag.list; [] clears). WRITE — confirm-gated.",
            inputSchema=WorkflowSetTagsInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
