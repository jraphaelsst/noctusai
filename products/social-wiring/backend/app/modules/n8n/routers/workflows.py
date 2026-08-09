"""n8n workflows + tags + executions HTTP surface.

Endpoints:
    GET    /api/n8n/workflows                      list (scoped by client tag / unassigned)
    POST   /api/n8n/workflows/{id}/assign           add the account's client tag
    DELETE /api/n8n/workflows/{id}/assign           remove it (+ clear placement)
    PATCH  /api/n8n/workflows/{id}                  rename / activate-deactivate / move folder
    DELETE /api/n8n/workflows/{id}                  delete (+ clear placement)
    POST   /api/n8n/workflows/{id}/run              webhook dispatch (409 if not can_run — zero side effects)
    GET    /api/n8n/workflows/{id}/executions       list
    GET    /api/n8n/tags                            list
    POST   /api/n8n/tags                            create

``account_id`` = ``integration_accounts.id`` (provider='n8n'). No
accounts endpoint here — the FE reads the existing
``/api/integrations/accounts``.

Status codes (uniform across the whole n8n module):
    401 unauthenticated · 403 account outside caller's org ·
    404 unknown account/workflow/tag · 409 run blocked ·
    424 our credential is missing/incomplete ·
    502 n8n unreachable/auth-failed upstream.

Auth pattern: ``Depends(get_current_user_org)`` per
``KB § PATTERNS/backend.md § Auth — canonical pattern`` (see
``app/modules/youtube/routers/settings.py:16-19`` for why this dep is
canonical over ``Depends(get_user_client)``).

Routes are sync ``def`` (house convention — every router in this
product is sync; FastAPI dispatches sync handlers to a threadpool so
the ``IntegrationAccountService`` blocking-I/O calls don't stall the
event loop). The seed n8n adapter's ``N8nClient`` Protocol is
``async``-only, so each route bridges via a single local ``async def``
helper + ONE ``asyncio.run(...)`` call — never several sequential
``asyncio.run`` calls per route (wasteful event-loop spin-up), and
matches the ``asyncio.run(provider.authorization_url(...))`` bridging
``integration_accounts_router.py`` already uses for the seed's async
OAuth provider.
"""
from __future__ import annotations

import asyncio
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.integrations.n8n import N8nError, instance_root, raw_to_workflow

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.n8n.schemas.common import N8nFolderOut, N8nTagOut
from app.modules.n8n.schemas.workflows import (
    N8nAccountIdIn,
    N8nExecutionListResponse,
    N8nExecutionOut,
    N8nRunResult,
    N8nTagCreateIn,
    N8nWorkflowListResponse,
    N8nWorkflowOut,
    N8nWorkflowPatchIn,
)
from app.modules.n8n.services.account_resolver import (
    build_n8n_client,
    client_tag_out,
    decrypt_or_503,
    get_account_service,
    get_admin_client_dep,
    get_n8n_client_factory,
    resolve_n8n_account,
    translate_n8n_error,
)
from app.modules.n8n.services.folders_service import FoldersService, get_folders_service
from app.services.integration_account_service import IntegrationAccountService

router = APIRouter(prefix="/api/n8n", tags=["n8n"])


def _not_runnable_reason(workflow) -> str:
    """Mirror the seed adapter's private ``HttpxN8nClient.
    _not_runnable_reason`` (not exported — ``n8n_adapter.py``'s
    ``__all__`` is ``["HttpxN8nClient"]`` only). Small, deliberate
    duplication of 4 lines rather than reaching into a private
    symbol."""
    if not workflow.has_webhook_node:
        return "workflow has no webhook trigger node"
    if not workflow.active:
        return "workflow is inactive (a webhook only fires while active)"
    if workflow.archived:
        return "workflow is archived"
    return "workflow is not runnable"  # unreachable in practice — can_run implies one of the above


def _to_out(workflow, *, base_url: str, folder_id: Optional[UUID]) -> N8nWorkflowOut:
    return N8nWorkflowOut(
        id=workflow.id,
        name=workflow.name,
        active=workflow.active,
        archived=workflow.archived,
        tags=[N8nTagOut(id=t.id, name=t.name) for t in workflow.tags],
        folder_id=folder_id,
        can_run=workflow.can_run,
        run_blocked_reason=None if workflow.can_run else _not_runnable_reason(workflow),
        open_url=f"{instance_root(base_url)}/workflow/{workflow.id}",
        updated_at=workflow.updated_at,
    )


# ─── GET /api/n8n/workflows ─────────────────────────────────────────────
@router.get("/workflows", response_model=N8nWorkflowListResponse)
def list_workflows(
    account_id: UUID = Query(...),
    scope: Literal["client", "unassigned"] = Query(...),
    include_archived: bool = Query(default=False),
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    folders_svc: FoldersService = Depends(get_folders_service),
    client_factory=Depends(get_n8n_client_factory),
) -> N8nWorkflowListResponse:
    """``scope='client'`` → workflows carrying the account's configured
    tag. ``scope='unassigned'`` → workflows carrying NO tags at all
    (GUESS: "no client tag" is read as "no tags whatsoever" — this
    consumer is the only writer of n8n tags on the instance, per the
    seed adapter's docstring on why a tag is "the only viable
    multi-tenant scoping key"; flagged since it's load-bearing and the
    FE cannot see this reading). ``scope='client'`` with NO tag
    configured yet returns an empty list, not an error — a freshly
    connected client legitimately has zero assigned workflows.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    account = resolve_n8n_account(svc, admin, account_id, org_id)
    credential = decrypt_or_503(svc, account_id, org_id)
    client, base_url, _api_key = build_n8n_client(client_factory, credential)
    tag = client_tag_out(account)

    async def _fetch():
        return await client.list_workflows(include_archived=include_archived)

    try:
        workflows = asyncio.run(_fetch())
    except N8nError as exc:
        raise translate_n8n_error(exc) from exc

    if scope == "client":
        workflows = (
            [w for w in workflows if any(t.id == tag["id"] for t in w.tags)]
            if tag is not None
            else []
        )
    else:
        workflows = [w for w in workflows if not w.tags]

    placements = folders_svc.get_placements(account_id)
    folders = folders_svc.list_for_account(account_id, org_id)

    return N8nWorkflowListResponse(
        workflows=[
            _to_out(w, base_url=base_url, folder_id=placements.get(w.id))
            for w in workflows
        ],
        folders=[
            N8nFolderOut(id=f.id, name=f.name, parent_id=f.parent_id, position=f.position)
            for f in folders
        ],
    )


# ─── assign / unassign ──────────────────────────────────────────────────
@router.post("/workflows/{workflow_id}/assign", response_model=N8nWorkflowOut)
def assign_workflow(
    workflow_id: str,
    body: N8nAccountIdIn,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    folders_svc: FoldersService = Depends(get_folders_service),
    client_factory=Depends(get_n8n_client_factory),
) -> N8nWorkflowOut:
    """Add the account's client tag to the workflow's tag set,
    PRESERVING every other tag already on the workflow. 424 if the
    account has no client tag configured yet — GUESS: widening 424
    (normally "credential incomplete") to also cover "no client tag
    configured" since both are "the connect card is incomplete, fix it
    via Settings" states; flagged since the contract's literal 424
    definition only mentions the credential.
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    account = resolve_n8n_account(svc, admin, body.account_id, org_id)
    credential = decrypt_or_503(svc, body.account_id, org_id)
    client, base_url, _api_key = build_n8n_client(client_factory, credential)

    tag = client_tag_out(account)
    if tag is None:
        raise HTTPException(
            status.HTTP_424_FAILED_DEPENDENCY,
            detail=(
                "no client tag configured for this account. Configure one "
                "via PUT /api/n8n/settings first."
            ),
        )

    async def _assign():
        raw = await client.get_workflow(workflow_id)
        current = raw_to_workflow(raw)
        tag_ids = sorted({t.id for t in current.tags} | {tag["id"]})
        await client.set_workflow_tags(workflow_id, tag_ids)
        raw2 = await client.get_workflow(workflow_id)
        return raw_to_workflow(raw2)

    try:
        workflow = asyncio.run(_assign())
    except N8nError as exc:
        raise translate_n8n_error(exc) from exc

    placements = folders_svc.get_placements(body.account_id)
    return _to_out(workflow, base_url=base_url, folder_id=placements.get(workflow_id))


@router.delete("/workflows/{workflow_id}/assign", response_model=N8nWorkflowOut)
def unassign_workflow(
    workflow_id: str,
    body: N8nAccountIdIn,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    folders_svc: FoldersService = Depends(get_folders_service),
    client_factory=Depends(get_n8n_client_factory),
) -> N8nWorkflowOut:
    """Remove the account's client tag, preserving every other tag.
    ALSO clears the placement row (the workflow leaves the client's
    folder tree) — per the contract."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    account = resolve_n8n_account(svc, admin, body.account_id, org_id)
    credential = decrypt_or_503(svc, body.account_id, org_id)
    client, base_url, _api_key = build_n8n_client(client_factory, credential)
    tag = client_tag_out(account)

    async def _unassign():
        raw = await client.get_workflow(workflow_id)
        current = raw_to_workflow(raw)
        remaining = [t.id for t in current.tags if tag is None or t.id != tag["id"]]
        await client.set_workflow_tags(workflow_id, remaining)
        raw2 = await client.get_workflow(workflow_id)
        return raw_to_workflow(raw2)

    try:
        workflow = asyncio.run(_unassign())
    except N8nError as exc:
        raise translate_n8n_error(exc) from exc

    folders_svc.clear_placement(account_id=body.account_id, workflow_id=workflow_id)
    return _to_out(workflow, base_url=base_url, folder_id=None)


# ─── PATCH /api/n8n/workflows/{id} ──────────────────────────────────────
@router.patch("/workflows/{workflow_id}", response_model=N8nWorkflowOut)
def patch_workflow(
    workflow_id: str,
    body: N8nWorkflowPatchIn,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    folders_svc: FoldersService = Depends(get_folders_service),
    client_factory=Depends(get_n8n_client_factory),
) -> N8nWorkflowOut:
    """Rename (``name``) / activate-deactivate (``active``) are n8n-side
    writes via the client. ``folder_id`` is LOCAL-only (the placement
    table) — never touches n8n. Uses ``model_fields_set`` to
    distinguish "folder_id not supplied" (leave placement unchanged)
    from "folder_id explicitly null" (move to root) — same tri-state
    pattern as ``IntegrationAccountUpdate.marca_id``."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    resolve_n8n_account(svc, admin, body.account_id, org_id)
    credential = decrypt_or_503(svc, body.account_id, org_id)
    client, base_url, _api_key = build_n8n_client(client_factory, credential)

    async def _patch():
        workflow = None
        if body.active is not None:
            workflow = await (
                client.activate(workflow_id) if body.active else client.deactivate(workflow_id)
            )
        if body.name is not None:
            workflow = await client.rename(workflow_id, body.name)
        if workflow is None:
            raw = await client.get_workflow(workflow_id)
            workflow = raw_to_workflow(raw)
        return workflow

    try:
        workflow = asyncio.run(_patch())
    except N8nError as exc:
        raise translate_n8n_error(exc) from exc

    if "folder_id" in body.model_fields_set:
        folders_svc.set_placement(
            org_id=org_id,
            account_id=body.account_id,
            workflow_id=workflow_id,
            folder_id=body.folder_id,
        )

    placements = folders_svc.get_placements(body.account_id)
    return _to_out(workflow, base_url=base_url, folder_id=placements.get(workflow_id))


# ─── DELETE /api/n8n/workflows/{id} ─────────────────────────────────────
@router.delete(
    "/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_workflow(
    workflow_id: str,
    body: N8nAccountIdIn,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    folders_svc: FoldersService = Depends(get_folders_service),
    client_factory=Depends(get_n8n_client_factory),
) -> None:
    """Hard-to-reverse — n8n's ``DELETE /workflows/{id}`` is not
    API-undoable. Clears the local placement row on success."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    resolve_n8n_account(svc, admin, body.account_id, org_id)
    credential = decrypt_or_503(svc, body.account_id, org_id)
    client, _base_url, _api_key = build_n8n_client(client_factory, credential)

    try:
        asyncio.run(client.delete_workflow(workflow_id))
    except N8nError as exc:
        raise translate_n8n_error(exc) from exc

    folders_svc.clear_placement(account_id=body.account_id, workflow_id=workflow_id)


# ─── POST /api/n8n/workflows/{id}/run ───────────────────────────────────
@router.post("/workflows/{workflow_id}/run", response_model=N8nRunResult)
def run_workflow(
    workflow_id: str,
    body: N8nAccountIdIn,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    client_factory=Depends(get_n8n_client_factory),
) -> N8nRunResult:
    """``can_run`` is checked BEFORE any dispatch attempt — a blocked
    workflow raises 409 with ZERO side effects (``run_via_webhook`` is
    never called in that branch). Never fakes a dispatch."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    resolve_n8n_account(svc, admin, body.account_id, org_id)
    credential = decrypt_or_503(svc, body.account_id, org_id)
    client, _base_url, _api_key = build_n8n_client(client_factory, credential)

    async def _run():
        raw = await client.get_workflow(workflow_id)
        workflow = raw_to_workflow(raw)
        if not workflow.can_run:
            return None, workflow
        result = await client.run_via_webhook(workflow)
        return result, workflow

    try:
        result, workflow = asyncio.run(_run())
    except N8nError as exc:
        raise translate_n8n_error(exc) from exc

    if result is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=_not_runnable_reason(workflow))

    return N8nRunResult(
        workflow_id=result.workflow_id,
        dispatched=result.dispatched,
        http_status=result.http_status,
    )


# ─── GET /api/n8n/workflows/{id}/executions ─────────────────────────────
@router.get("/workflows/{workflow_id}/executions", response_model=N8nExecutionListResponse)
def list_executions(
    workflow_id: str,
    account_id: UUID = Query(...),
    limit: int = Query(default=20, ge=1, le=250),
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    client_factory=Depends(get_n8n_client_factory),
) -> N8nExecutionListResponse:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    resolve_n8n_account(svc, admin, account_id, org_id)
    credential = decrypt_or_503(svc, account_id, org_id)
    client, _base_url, _api_key = build_n8n_client(client_factory, credential)

    try:
        executions = asyncio.run(client.list_executions(workflow_id=workflow_id, limit=limit))
    except N8nError as exc:
        raise translate_n8n_error(exc) from exc

    return N8nExecutionListResponse(
        executions=[
            N8nExecutionOut(
                id=e.id,
                status=e.status,
                mode=e.mode,
                started_at=e.started_at,
                stopped_at=e.stopped_at,
            )
            for e in executions
        ]
    )


# ─── GET / POST /api/n8n/tags ────────────────────────────────────────────
@router.get("/tags", response_model=list[N8nTagOut])
def list_tags(
    account_id: UUID = Query(...),
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    client_factory=Depends(get_n8n_client_factory),
) -> list[N8nTagOut]:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    resolve_n8n_account(svc, admin, account_id, org_id)
    credential = decrypt_or_503(svc, account_id, org_id)
    client, _base_url, _api_key = build_n8n_client(client_factory, credential)

    try:
        tags = asyncio.run(client.list_tags())
    except N8nError as exc:
        raise translate_n8n_error(exc) from exc

    return [N8nTagOut(id=t.id, name=t.name) for t in tags]


@router.post("/tags", response_model=N8nTagOut, status_code=status.HTTP_201_CREATED)
def create_tag(
    body: N8nTagCreateIn,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    client_factory=Depends(get_n8n_client_factory),
) -> N8nTagOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    resolve_n8n_account(svc, admin, body.account_id, org_id)
    credential = decrypt_or_503(svc, body.account_id, org_id)
    client, _base_url, _api_key = build_n8n_client(client_factory, credential)

    try:
        tag = asyncio.run(client.create_tag(body.name))
    except N8nError as exc:
        raise translate_n8n_error(exc) from exc

    return N8nTagOut(id=tag.id, name=tag.name)


__all__ = ["router"]
