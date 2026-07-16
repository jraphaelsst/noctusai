"""n8n.workflow.* tools — list / inspect / activate / deactivate / …

Thin MCP In/Out shaping over `noctusai_lib.integrations.n8n`'s
`N8nClient` — the `mcp/google/tools/youtube.py:1` / `mcp/meta/tools
/ads.py:31` pattern. NO connector-side HTTP, no connector-side error
taxonomy, no connector-side raw→VO mapping: `client.get_client()`
(`mcp/n8n/client.py`) returns an `N8nClient` (real or the seed's
`FakeN8nClient` in tests), and every handler just calls a Protocol
method and shapes the result into its Pydantic Out model.

Reads (no confirm gate): list / get.
Writes (confirm-gated): activate / deactivate / update / create /
delete / set_tags.

Every handler catches `(api.N8nApiError, N8nError)` — the confirm-gate/
not-configured signal and the seed's own error hierarchy — and maps
both through `api.map_seed_error` before `typed_error`, so the Output
`error` envelope is always the same `N8nApiError` shape regardless of
which layer raised.

`sanitize_workflow_put_body` (the seed's canonical PUT/POST allowlist)
is still called HERE too, ONLY to report `sent_keys` on the Output —
the actual sanitize-before-PUT happens again, idempotently, inside
`client.update_workflow`/`create_workflow`. `set_workflow_tags` no
longer needs `tag_refs_body` at all: the id→body-shape translation is
now fully internal to the seed adapter.
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from _kit.errors import typed_error
from noctusai_lib.integrations.n8n import N8nError, Tag, Workflow, sanitize_workflow_put_body

from .. import api
from ..client import get_client
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

logger = logging.getLogger(__name__)


def _summary(w: Workflow) -> WorkflowSummary:
    return WorkflowSummary(
        id=w.id,
        name=w.name,
        active=w.active,
        tags=[t.name for t in w.tags],
        createdAt=w.created_at.isoformat() if w.created_at else None,
        updatedAt=w.updated_at.isoformat() if w.updated_at else None,
    )


def _tag_summaries(tags: list[Tag]) -> list[TagSummary]:
    return [TagSummary(id=t.id, name=t.name) for t in tags]


# ─── Reads ───────────────────────────────────────────────────────────────


async def workflow_list(args: dict) -> dict:
    inp = WorkflowListInput(**args)
    try:
        client = get_client()
        # The seed client already exhausts n8n's own pagination
        # (cursor-follow) and returns the true full set — `active`/
        # `name`/`limit` filter client-side against that complete,
        # correct list rather than trusting unverified upstream query
        # params (the same "no upstream-shape guess" call the seed's
        # own `list_workflows(tag=...)` makes).
        workflows = await client.list_workflows(include_archived=True)
    except (api.N8nApiError, N8nError) as e:
        return WorkflowListOutput(error=typed_error(api.map_seed_error(e))).model_dump()
    if inp.active is not None:
        workflows = [w for w in workflows if w.active == inp.active]
    if inp.name is not None:
        workflows = [w for w in workflows if w.name == inp.name]
    workflows = workflows[: inp.limit]
    return WorkflowListOutput(
        workflows=[_summary(w) for w in workflows],
        # The seed client already exhausted pagination — there is no
        # further page to fetch; `next_cursor` was already dead output
        # (no `cursor` input field exists on `WorkflowListInput`).
        next_cursor=None,
    ).model_dump()


async def workflow_get(args: dict) -> dict:
    inp = WorkflowGetInput(**args)
    try:
        client = get_client()
        workflow = await client.get_workflow(inp.id)
    except (api.N8nApiError, N8nError) as e:
        return WorkflowGetOutput(error=typed_error(api.map_seed_error(e))).model_dump()
    return WorkflowGetOutput(
        workflow=workflow if isinstance(workflow, dict) else None
    ).model_dump()


# ─── Writes (confirm-gated) ──────────────────────────────────────────────


async def _set_active(workflow_id: str, activate: bool) -> dict:
    try:
        client = get_client()
        workflow = (
            await client.activate(workflow_id)
            if activate
            else await client.deactivate(workflow_id)
        )
    except (api.N8nApiError, N8nError) as e:
        return WorkflowActiveStateOutput(error=typed_error(api.map_seed_error(e))).model_dump()
    return WorkflowActiveStateOutput(
        id=workflow_id, active=workflow.active, changed=True
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
    # Computed here ONLY for the `sent_keys` Output field — the actual
    # PUT-sanitize happens again (idempotently) inside
    # `client.update_workflow`.
    body = sanitize_workflow_put_body(inp.workflow)
    try:
        client = get_client()
        workflow = await client.update_workflow(inp.id, inp.workflow)
    except (api.N8nApiError, N8nError) as e:
        return WorkflowUpdateOutput(error=typed_error(api.map_seed_error(e))).model_dump()
    return WorkflowUpdateOutput(
        id=workflow.id,
        name=workflow.name,
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
    try:
        client = get_client()
        workflow = await client.create_workflow(inp.workflow)
    except (api.N8nApiError, N8nError) as e:
        return WorkflowCreateOutput(error=typed_error(api.map_seed_error(e))).model_dump()
    return WorkflowCreateOutput(
        id=workflow.id, name=workflow.name, created=True
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
        client = get_client()
        await client.delete_workflow(inp.id)
    except (api.N8nApiError, N8nError) as e:
        return WorkflowDeleteOutput(
            id=inp.id, error=typed_error(api.map_seed_error(e))
        ).model_dump()
    return WorkflowDeleteOutput(id=inp.id, deleted=True).model_dump()


async def workflow_set_tags(args: dict) -> dict:
    inp = WorkflowSetTagsInput(**args)
    if not inp.confirm:
        return WorkflowSetTagsOutput(
            error=typed_error(
                api.ConfirmationRequiredError("n8n.workflow.set_tags")
            )
        ).model_dump()
    try:
        client = get_client()
        tags = await client.set_workflow_tags(inp.id, inp.tag_ids)
    except (api.N8nApiError, N8nError) as e:
        return WorkflowSetTagsOutput(
            id=inp.id, error=typed_error(api.map_seed_error(e))
        ).model_dump()
    return WorkflowSetTagsOutput(
        id=inp.id, tags=_tag_summaries(tags), updated=True
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
