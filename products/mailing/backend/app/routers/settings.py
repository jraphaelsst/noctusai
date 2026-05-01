"""Settings router — sender domains, sender config."""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from app.dependencies import get_current_user, get_org_id, get_admin_client
from noctusai_lib.primitives.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["Settings"])


class DomainAdd(BaseModel):
    domain: str


class SenderConfig(BaseModel):
    remetente_nome: Optional[str] = None
    remetente_email: Optional[str] = None


@router.get("/domains")
async def list_domains(authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_admin_client()
    result = db.table("sender_domains").select("*").eq("org_id", org_id).execute()
    return success_response(result.data or [])


@router.post("/domains")
async def add_domain(body: DomainAdd, authorization: Optional[str] = Header(None)):
    """Add a sender domain. TODO: integrate with Resend Domains API for DNS verification."""
    user, _ = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_admin_client()
    result = db.table("sender_domains").insert({
        "org_id": org_id,
        "domain": body.domain,
        "status": "pending",
    }).execute()
    if not result.data:
        raise HTTPException(status_code=400, detail="Erro ao adicionar dominio")
    return success_response(result.data[0])


@router.get("/domains/{domain_id}/verify")
async def verify_domain(domain_id: str, authorization: Optional[str] = Header(None)):
    """Check domain verification status. TODO: query Resend Domains API."""
    user, _ = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_admin_client()
    result = db.table("sender_domains").select("*").eq("id", domain_id).eq("org_id", org_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Dominio nao encontrado")
    return success_response(result.data[0])


@router.delete("/domains/{domain_id}")
async def remove_domain(domain_id: str, authorization: Optional[str] = Header(None)):
    user, _ = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_admin_client()
    db.table("sender_domains").delete().eq("id", domain_id).eq("org_id", org_id).execute()
    return {"ok": True, "message": "Dominio removido"}
