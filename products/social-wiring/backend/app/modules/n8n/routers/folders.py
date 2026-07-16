"""n8n folder-tree HTTP surface.

Endpoints:
    GET    /api/n8n/folders                    list an account's folder tree (flat; FE nests client-side)
    POST   /api/n8n/folders                     create
    PATCH  /api/n8n/folders/{folder_id}         rename / reparent / reorder
    DELETE /api/n8n/folders/{folder_id}         delete (reassigning children + placed workflows)

GET/POST carry ``account_id`` (which account's tree). PATCH/DELETE
target an existing row uniquely identified by ``folder_id`` and derive
org ownership FROM THE ROW ITSELF — the contract's body shape for
those two methods carries no ``account_id`` (can't be spoofed to a
different account this way either).

``DELETE .../folders/{id}?reassign_to=<uuid>`` — the FE (S4, already
shipped) OMITS the query param entirely to mean "reassign to root"
(a literal ``"null"`` string would 422 against ``Optional[UUID]``
parsing); this is now the binding encoding both sides share.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.n8n.schemas.common import N8nFolderOut
from app.modules.n8n.schemas.folders import N8nFolderCreateIn, N8nFolderUpdateIn
from app.modules.n8n.services.account_resolver import (
    get_account_service,
    get_admin_client_dep,
    resolve_n8n_account,
)
from app.modules.n8n.services.folders_service import (
    UNSET,
    FolderCycleError,
    FolderNameConflict,
    FolderNotFound,
    FoldersService,
    get_folders_service,
)
from app.services.integration_account_service import IntegrationAccountService

router = APIRouter(prefix="/api/n8n", tags=["n8n"])


def _out(row) -> N8nFolderOut:
    return N8nFolderOut(id=row.id, name=row.name, parent_id=row.parent_id, position=row.position)


def _require_owned_folder(folders_svc: FoldersService, folder_id: UUID, org_id: UUID):
    """404 unknown folder, 403 belongs to a different org — mirrors
    ``resolve_n8n_account``'s split, derived from the folder row's own
    ``org_id`` column rather than a caller-supplied ``account_id``."""
    row = folders_svc.get(folder_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="folder not found")
    if row.org_id != org_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="folder does not belong to your organization",
        )
    return row


@router.get("/folders", response_model=list[N8nFolderOut])
def list_folders(
    account_id: UUID = Query(...),
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    folders_svc: FoldersService = Depends(get_folders_service),
) -> list[N8nFolderOut]:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    resolve_n8n_account(svc, admin, account_id, org_id)
    return [_out(f) for f in folders_svc.list_for_account(account_id, org_id)]


@router.post("/folders", response_model=N8nFolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(
    body: N8nFolderCreateIn,
    auth: tuple = Depends(get_current_user_org),
    svc: IntegrationAccountService = Depends(get_account_service),
    admin=Depends(get_admin_client_dep),
    folders_svc: FoldersService = Depends(get_folders_service),
) -> N8nFolderOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    resolve_n8n_account(svc, admin, body.account_id, org_id)
    try:
        row = folders_svc.create(
            org_id=org_id,
            account_id=body.account_id,
            name=body.name,
            parent_id=body.parent_id,
        )
    except FolderNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FolderNameConflict as exc:
        # GUESS: 409 for a UNIQUE(account_id, parent_id, name) violation —
        # the contract's status table doesn't name a "folder name conflict"
        # class explicitly; 409 is the closest fit among the allowed codes
        # (a state-conflict, same family as "run blocked").
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _out(row)


@router.patch("/folders/{folder_id}", response_model=N8nFolderOut)
def update_folder(
    folder_id: UUID,
    body: N8nFolderUpdateIn,
    auth: tuple = Depends(get_current_user_org),
    folders_svc: FoldersService = Depends(get_folders_service),
) -> N8nFolderOut:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    _require_owned_folder(folders_svc, folder_id, org_id)

    parent_arg: object = UNSET
    if "parent_id" in body.model_fields_set:
        parent_arg = body.parent_id

    try:
        row = folders_svc.update(
            folder_id, name=body.name, parent_id=parent_arg, position=body.position
        )
    except FolderNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FolderCycleError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except FolderNameConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _out(row)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_folder(
    folder_id: UUID,
    reassign_to: Optional[UUID] = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
    folders_svc: FoldersService = Depends(get_folders_service),
) -> None:
    """``reassign_to`` absent ⇒ children folders + placed workflows
    move to root (the binding FE encoding — see module docstring)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    _require_owned_folder(folders_svc, folder_id, org_id)
    try:
        folders_svc.delete(folder_id, reassign_to=reassign_to)
    except FolderNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FolderCycleError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


__all__ = ["router"]
