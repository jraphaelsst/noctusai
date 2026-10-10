"""Contacts router — CRUD, import, search/filter."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from app.dependencies import get_current_user_org, get_admin_client, get_settings
from app.modules.email_marketing.schemas.contacts import ContactCreate, ContactUpdate, ContactImport

from app.modules.email_marketing.services.contact_service import ContactService
from app.modules.email_marketing.services.email_optin import (
    OPTIN_PENDING,
    build_confirmation_sender,
    send_confirmation,
)
from noctusai_lib.primitives.responses import success_response, paginated_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/email-marketing/contacts', tags=["Contacts"])


def _get_service(org_id) -> ContactService:
    return ContactService(get_admin_client(), org_id)


def get_confirmation_sender(cfg=Depends(get_settings)):
    """Double opt-in sender seam: the Real Resend sender, or None when Resend
    is not configured (then nothing is sent and the response says why). Tests
    inject a ``FakeEmailSender`` via ``app.dependency_overrides``."""
    return build_confirmation_sender(cfg)


@router.get("")
async def list_contacts(
    auth = Depends(get_current_user_org), page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    user, _, org_id = auth
    svc = _get_service(org_id)
    data, total = svc.list_contacts(page, page_size, status=status, search=search)
    return paginated_response(data, total, page, page_size)


@router.post("")
async def create_contact(
    body: ContactCreate,
    auth = Depends(get_current_user_org),
    sender = Depends(get_confirmation_sender),
    cfg = Depends(get_settings),
):
    user, _, org_id = auth
    svc = _get_service(org_id)
    result = svc.create_contact(body.model_dump())
    if not result:
        raise HTTPException(status_code=400, detail="Erro ao criar contato")
    if result.get("email_optin") == OPTIN_PENDING:
        # Double opt-in: the confirmation outcome is part of the response —
        # a not-sent mail is never silent.
        result = {**result, "confirmation": await send_confirmation(sender, cfg, result)}
    return success_response(result)


@router.get("/{contact_id}")
async def get_contact(contact_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(org_id)
    result = svc.get_contact(contact_id)
    if not result:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    return success_response(result)


@router.patch("/{contact_id}")
async def update_contact(contact_id: str, body: ContactUpdate, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(org_id)
    data = body.model_dump(exclude_unset=True)
    result = svc.update_contact(contact_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    return success_response(result)


@router.delete("/{contact_id}")
async def delete_contact(contact_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    svc = _get_service(org_id)
    svc.delete_contact(contact_id)
    return {"ok": True, "message": "Contato removido"}


@router.post("/import")
async def import_contacts(
    body: ContactImport,
    auth = Depends(get_current_user_org),
    sender = Depends(get_confirmation_sender),
    cfg = Depends(get_settings),
):
    user, _, org_id = auth
    svc = _get_service(org_id)
    contacts_data = [c.model_dump() for c in body.contacts]
    result = svc.import_contacts(contacts_data, double_opt_in=body.double_opt_in)
    pending = result.pop("pending")
    if body.double_opt_in:
        outcomes = [await send_confirmation(sender, cfg, row) for row in pending]
        failed = [o["reason"] for o in outcomes if not o["sent"]]
        result["confirmation"] = {
            "requested": len(outcomes),
            "sent": len(outcomes) - len(failed),
            "failed": len(failed),
            "reason": failed[0] if failed else None,
        }
    return success_response(result)


@router.post("/{contact_id}/resend-confirmation")
async def resend_confirmation(
    contact_id: str,
    auth = Depends(get_current_user_org),
    sender = Depends(get_confirmation_sender),
    cfg = Depends(get_settings),
):
    """Re-send the double opt-in email to a contact still awaiting confirmation."""
    user, _, org_id = auth
    contact = _get_service(org_id).get_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if contact.get("email_optin") != OPTIN_PENDING:
        raise HTTPException(status_code=409, detail="Contato não está aguardando confirmação")
    return success_response({"confirmation": await send_confirmation(sender, cfg, contact)})
