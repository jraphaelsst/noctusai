"""Settings router — sender domains, sender config."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from app.dependencies import get_current_user_org, get_org_id, get_admin_client
from noctusai_lib.primitives.responses import success_response
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["Settings"])


class DomainAdd(StrictHttpModel):
    domain: str


class SenderConfig(StrictHttpModel):
    remetente_nome: Optional[str] = None
    remetente_email: Optional[str] = None


@router.get("/domains")
async def list_domains(auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    org_id = get_org_id(user)
    db = get_admin_client()
    result = db.table("sender_domains").select("*").eq("org_id", org_id).execute()
    return success_response(result.data or [])


@router.post("/domains")
async def add_domain(body: DomainAdd, auth = Depends(get_current_user_org)):
    """Add a sender domain. TODO: integrate with Resend Domains API for DNS verification."""
    user, _, org_id = auth
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
async def verify_domain(domain_id: str, auth = Depends(get_current_user_org)):
    """Check domain verification status. TODO: query Resend Domains API."""
    user, _, org_id = auth
    org_id = get_org_id(user)
    db = get_admin_client()
    result = db.table("sender_domains").select("*").eq("id", domain_id).eq("org_id", org_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Dominio nao encontrado")
    return success_response(result.data[0])


@router.delete("/domains/{domain_id}")
async def remove_domain(domain_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    org_id = get_org_id(user)
    db = get_admin_client()
    db.table("sender_domains").delete().eq("id", domain_id).eq("org_id", org_id).execute()
    return {"ok": True, "message": "Dominio removido"}
