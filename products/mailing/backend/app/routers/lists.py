"""Contact lists router — CRUD, members, resolve."""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from app.dependencies import get_current_user, get_org_id, get_admin_client
from app.schemas.lists import ListCreate, ListUpdate, ListMembersAdd, ListMembersRemove
from app.services.list_service import ListService
from noctusai_shared.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lists", tags=["Lists"])


def _get_service(user) -> ListService:
    org_id = get_org_id(user)
    return ListService(get_admin_client(), org_id)


@router.get("")
async def list_all(authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    return success_response(svc.list_all())


@router.post("")
async def create_list(body: ListCreate, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    result = svc.create_list(body.model_dump())
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao criar lista")
    return success_response(result)


@router.get("/{list_id}")
async def get_list(list_id: str, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    result = svc.get_list(list_id)
    if not result:
        raise HTTPException(status_code=404, detail="Lista nao encontrada")
    return success_response(result)


@router.patch("/{list_id}")
async def update_list(list_id: str, body: ListUpdate, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    data = body.model_dump(exclude_unset=True)
    result = svc.update_list(list_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Lista nao encontrada")
    return success_response(result)


@router.delete("/{list_id}")
async def delete_list(list_id: str, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    svc.delete_list(list_id)
    return {"ok": True, "message": "Lista removida"}


@router.post("/{list_id}/members")
async def add_members(list_id: str, body: ListMembersAdd, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    result = svc.add_members(list_id, body.contact_ids)
    return success_response(result)


@router.delete("/{list_id}/members")
async def remove_members(list_id: str, body: ListMembersRemove, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    svc.remove_members(list_id, body.contact_ids)
    return {"ok": True, "message": "Membros removidos"}


@router.get("/{list_id}/contacts")
async def resolve_contacts(list_id: str, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    svc = _get_service(user)
    contacts = svc.resolve_contacts(list_id)
    return success_response(contacts, total=len(contacts))
