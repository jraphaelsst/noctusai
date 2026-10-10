"""Settings router — sender domains, sender config.

Sender-domain verification (P1b(c), 2026-10-10) goes through the seed Resend
Domains adapter (`noctusai_lib.integrations.resend`): `POST /domains` registers
the domain at Resend and stores the DNS records to publish; `GET
/domains/{id}/verify` asks Resend to check them and maps the result to
`pending|verified|failed`. No `RESEND_API_KEY` → 503, never a fake "verified".
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from app.dependencies import get_current_user_org, get_admin_client, get_settings
from noctusai_lib.integrations.resend import (
    DomainRecord,
    ResendDomains,
    ResendDomainsError,
    ResendNotConfigured,
    make_resend_domains,
)
from noctusai_lib.primitives.responses import success_response
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/email-marketing/settings', tags=["Settings"])


class DomainAdd(StrictHttpModel):
    domain: str


class SenderConfig(StrictHttpModel):
    remetente_nome: Optional[str] = None
    remetente_email: Optional[str] = None


@router.get("/domains")
async def list_domains(auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    db = get_admin_client()
    result = db.table("sender_domains").select("*").eq("org_id", org_id).execute()
    return success_response(result.data or [])


RESEND_NOT_CONFIGURED_DETAIL = (
    "Verificação de domínio indisponível: a integração com o Resend não está "
    "configurada (RESEND_API_KEY ausente). Nenhum domínio foi marcado como verificado."
)


def get_resend_domains(cfg=Depends(get_settings)) -> ResendDomains:
    """DI seam for the Resend Domains adapter (tests override it with
    `FakeResendDomains`). No key → 503; the seed factory never falls back to
    the Fake on its own."""
    try:
        return make_resend_domains(cfg.resend_api_key)
    except ResendNotConfigured:
        raise HTTPException(status_code=503, detail=RESEND_NOT_CONFIGURED_DETAIL)


def map_resend_status(status: str) -> str:
    """Resend vocabulary → `sender_domains.status` (CHECK pending|verified|failed)."""
    if status == "verified":
        return "verified"
    if status in ("failed", "temporary_failure"):
        return "failed"
    return "pending"


def _resend_error(exc: ResendDomainsError) -> HTTPException:
    logger.error("resend domains API error: %s", exc)
    return HTTPException(status_code=502, detail="O Resend recusou ou não respondeu à solicitação. Tente novamente.")


def _status_fields(rec: DomainRecord) -> dict:
    status = map_resend_status(rec.status)
    fields = {"status": status, "verified_at": None}
    if status == "verified":
        fields["verified_at"] = datetime.now(timezone.utc).isoformat()
    return fields


@router.post("/domains")
async def add_domain(
    body: DomainAdd,
    auth=Depends(get_current_user_org),
    resend: ResendDomains = Depends(get_resend_domains),
):
    """Register the domain at Resend and store the DNS records to publish."""
    user, _, org_id = auth
    domain = body.domain.strip().lower()
    if not domain:
        raise HTTPException(status_code=422, detail="Informe o domínio")
    try:
        rec = await resend.create(domain)
    except ResendDomainsError as exc:
        raise _resend_error(exc)
    db = get_admin_client()
    result = db.table("sender_domains").insert({
        "org_id": org_id,
        "domain": domain,
        "resend_domain_id": rec.id,
        "dns_records": rec.records,
        **_status_fields(rec),
    }).execute()
    if not result.data:
        raise HTTPException(status_code=400, detail="Erro ao adicionar dominio")
    return success_response(result.data[0])


@router.get("/domains/{domain_id}/verify")
async def verify_domain(
    domain_id: str,
    auth=Depends(get_current_user_org),
    resend: ResendDomains = Depends(get_resend_domains),
):
    """Ask Resend to check the DNS records, then store the mapped status."""
    user, _, org_id = auth
    db = get_admin_client()
    result = db.table("sender_domains").select("*").eq("id", domain_id).eq("org_id", org_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Dominio nao encontrado")
    row = result.data[0]
    if not row.get("resend_domain_id"):
        raise HTTPException(
            status_code=409,
            detail="Este domínio foi cadastrado antes da integração com o Resend. Remova-o e adicione novamente.",
        )
    try:
        rec = await resend.verify(row["resend_domain_id"])
    except ResendDomainsError as exc:
        raise _resend_error(exc)
    update = _status_fields(rec)
    if update["status"] == "verified" and row.get("verified_at"):
        update["verified_at"] = row["verified_at"]  # keep the first verification time
    if rec.records:
        update["dns_records"] = rec.records
    updated = (db.table("sender_domains").update(update)
               .eq("id", domain_id).eq("org_id", org_id).execute())
    return success_response(updated.data[0] if updated.data else {**row, **update})


@router.delete("/domains/{domain_id}")
async def remove_domain(domain_id: str, auth = Depends(get_current_user_org)):
    user, _, org_id = auth
    db = get_admin_client()
    db.table("sender_domains").delete().eq("id", domain_id).eq("org_id", org_id).execute()
    return {"ok": True, "message": "Dominio removido"}
