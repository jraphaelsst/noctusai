"""Contacts router — CRUD, import, search/filter."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from app.dependencies import get_current_user_org, get_org_id, get_admin_client
from app.schemas.contacts import ContactCreate, ContactUpdate, ContactImport

from app.services.contact_service import ContactService
from noctusai_lib.primitives.responses import success_response, paginated_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/contacts", tags=["Contacts"])


def _get_service(user) -> ContactService:
    org_id = get_org_id(user)
    return ContactService(get_admin_client(), org_id)


@router.get("")
async def list_contacts(
    auth = Depends(get_current_user_org), page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    user, _, org_id = auth
    svc = _get_service(user)
    data, total = svc.list_contacts(page, page_size, status=status, search=search)
    return paginated_response(data, total, page, page_size)


@router.post("")
async def create_contact(body: ContactCreate, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    result = svc.create_contact(body.model_dump())
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao criar contato")
    return success_response(result)


@router.get("/{contact_id}")
async def get_contact(contact_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    result = svc.get_contact(contact_id)
    if not result:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    return success_response(result)


@router.patch("/{contact_id}")
async def update_contact(contact_id: str, body: ContactUpdate, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    data = body.model_dump(exclude_unset=True)
    result = svc.update_contact(contact_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    return success_response(result)


@router.delete("/{contact_id}")
async def delete_contact(contact_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    svc.delete_contact(contact_id)
    return {"ok": True, "message": "Contato removido"}


@router.post("/import")
async def import_contacts(body: ContactImport, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(user)
    contacts_data = [c.model_dump() for c in body.contacts]
    result = svc.import_contacts(contacts_data)
    return success_response(result)
