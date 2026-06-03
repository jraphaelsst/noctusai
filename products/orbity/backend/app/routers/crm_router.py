"""
CRM router — leads, funil kanban, stage moves, activities, scoring,
scoring-rules CRUD, and public lead capture.

Auth boundary:
  - All /api/crm/* → Depends(get_current_user_org) → strict 401
  - POST /api/capture/{org_id} → unauthenticated public endpoint
    (uses admin/service_role client so RLS INSERT policy applies to
    service_role bypass row in 005_crm_core.sql)

Endpoints:
  GET    /api/crm/funil                      kanban grouped by stage
  GET    /api/crm/stages                     list stages for org
  GET    /api/crm/leads                      paginated lead list
  POST   /api/crm/leads                      create lead → 201
  GET    /api/crm/leads/{id}                 lead detail
  PATCH  /api/crm/leads/{id}                 update lead
  DELETE /api/crm/leads/{id}                 delete lead
  PATCH  /api/crm/leads/{id}/stage           move stage
  GET    /api/crm/leads/{id}/activities      list activities
  POST   /api/crm/leads/{id}/activities      add activity → 201
  POST   /api/crm/leads/{id}/score           run scoring → 200
  GET    /api/crm/scoring-rules              list scoring rules
  POST   /api/crm/scoring-rules              create rule → 201
  PATCH  /api/crm/scoring-rules/{id}         update rule
  DELETE /api/crm/scoring-rules/{id}         delete rule

  POST   /api/capture/{org_id}               PUBLIC lead capture
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_user_client,
)
from app.schemas.crm import (
    ActivityCreate,
    ActivityOut,
    LeadCaptureRequest,
    LeadCreate,
    LeadOut,
    LeadUpdate,
    ScoringResultOut,
    ScoringRuleCreate,
    ScoringRuleOut,
    ScoringRuleUpdate,
    StageMoveRequest,
)
from app.services.crm_service import CRMService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["CRM"])
capture_router = APIRouter(tags=["Lead Capture"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _crm(token: str, org_id: UUID) -> CRMService:
    return CRMService(get_user_client(token), org_id=org_id)


def _admin_crm(org_id: UUID) -> CRMService:
    """CRM service backed by the admin (service_role) client.

    Used exclusively by the unauthenticated public capture endpoint so
    RLS service_role bypass policy allows the INSERT.
    """
    return CRMService(get_admin_client(), org_id=org_id)


# ---------------------------------------------------------------------------
# Funil + Stages
# ---------------------------------------------------------------------------

@router.get("/api/crm/funil", status_code=status.HTTP_200_OK)
async def get_funil(auth: tuple = Depends(get_current_user_org)) -> list:
    """Kanban view — leads grouped by stage, sorted by stage.position."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _crm(token, org_id).get_funil()
    except Exception:
        logger.exception("crm.funil failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao carregar funil")


@router.get("/api/crm/stages", status_code=status.HTTP_200_OK)
async def list_stages(auth: tuple = Depends(get_current_user_org)) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _crm(token, org_id).list_stages()
    except Exception:
        logger.exception("crm.stages failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar etapas")


# ---------------------------------------------------------------------------
# Leads CRUD
# ---------------------------------------------------------------------------

@router.get("/api/crm/leads", status_code=status.HTTP_200_OK)
async def list_leads(
    stage_id: str | None = Query(default=None),
    owner_id: str | None = Query(default=None),
    source: str | None = Query(default=None),
    temperature: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _crm(token, org_id).list_leads(
            stage_id=stage_id,
            owner_id=owner_id,
            source=source,
            temperature=temperature,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("crm.list_leads failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar leads")


@router.post(
    "/api/crm/leads",
    response_model=LeadOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_lead(
    payload: LeadCreate,
    auth: tuple = Depends(get_current_user_org),
) -> LeadOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _crm(token, org_id).create_lead(payload.model_dump(exclude_none=True))
    except Exception:
        logger.exception("crm.create_lead failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar lead")
    return LeadOut(**row)


@router.get(
    "/api/crm/leads/{lead_id}",
    response_model=LeadOut,
    status_code=status.HTTP_200_OK,
)
async def get_lead(
    lead_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> LeadOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _crm(token, org_id).get_lead(lead_id)
    except Exception:
        logger.exception("crm.get_lead failed org=%s id=%s", org_id, lead_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar lead")
    if not row:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return LeadOut(**row)


@router.patch(
    "/api/crm/leads/{lead_id}",
    response_model=LeadOut,
    status_code=status.HTTP_200_OK,
)
async def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> LeadOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _crm(token, org_id).update_lead(lead_id, data)
    except Exception:
        logger.exception("crm.update_lead failed org=%s id=%s", org_id, lead_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar lead")
    if not row:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return LeadOut(**row)


@router.delete("/api/crm/leads/{lead_id}", status_code=status.HTTP_200_OK)
async def delete_lead(
    lead_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _crm(token, org_id).delete_lead(lead_id)
    except Exception:
        logger.exception("crm.delete_lead failed org=%s id=%s", org_id, lead_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar lead")
    if not ok:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return {"ok": True, "id": lead_id}


# ---------------------------------------------------------------------------
# Stage move
# ---------------------------------------------------------------------------

@router.patch(
    "/api/crm/leads/{lead_id}/stage",
    response_model=LeadOut,
    status_code=status.HTTP_200_OK,
)
async def move_stage(
    lead_id: str,
    payload: StageMoveRequest,
    auth: tuple = Depends(get_current_user_org),
) -> LeadOut:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _crm(token, org_id).move_lead_stage(
            lead_id,
            str(payload.stage_id),
            user_id=str(user.id) if hasattr(user, "id") else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("crm.move_stage failed org=%s lead=%s", org_id, lead_id)
        raise HTTPException(status_code=502, detail="Falha ao mover lead")
    if not row:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return LeadOut(**row)


# ---------------------------------------------------------------------------
# Activities
# ---------------------------------------------------------------------------

@router.get(
    "/api/crm/leads/{lead_id}/activities",
    status_code=status.HTTP_200_OK,
)
async def list_activities(
    lead_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _crm(token, org_id).list_activities(lead_id)
    except Exception:
        logger.exception("crm.list_activities failed org=%s lead=%s", org_id, lead_id)
        raise HTTPException(status_code=502, detail="Falha ao listar atividades")


@router.post(
    "/api/crm/leads/{lead_id}/activities",
    response_model=ActivityOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_activity(
    lead_id: str,
    payload: ActivityCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ActivityOut:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _crm(token, org_id).add_activity(
            lead_id,
            payload.type,
            note=payload.note,
            created_by=str(user.id) if hasattr(user, "id") else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception("crm.add_activity failed org=%s lead=%s", org_id, lead_id)
        raise HTTPException(status_code=502, detail="Falha ao registrar atividade")
    return ActivityOut(**row)


# ---------------------------------------------------------------------------
# Lead scoring
# ---------------------------------------------------------------------------

@router.post(
    "/api/crm/leads/{lead_id}/score",
    response_model=ScoringResultOut,
    status_code=status.HTTP_200_OK,
)
async def score_lead(
    lead_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ScoringResultOut:
    """Run scoring rules against lead.custom_fields; upsert result."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _crm(token, org_id).score_lead(lead_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception("crm.score_lead failed org=%s lead=%s", org_id, lead_id)
        raise HTTPException(status_code=502, detail="Falha ao pontuar lead")
    return ScoringResultOut(**row)


# ---------------------------------------------------------------------------
# Scoring rules CRUD
# ---------------------------------------------------------------------------

@router.get(
    "/api/crm/scoring-rules",
    status_code=status.HTTP_200_OK,
)
async def list_scoring_rules(
    form_id: str | None = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    svc = _crm(token, org_id)
    try:
        query = (
            svc._t("lead_scoring_rules")
            .select("*")
            .eq("org_id", str(org_id))
            .order("created_at", desc=False)
        )
        if form_id:
            query = query.eq("form_id", form_id)
        result = query.execute()
    except Exception:
        logger.exception("crm.list_scoring_rules failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar regras")
    return result.data or []


@router.post(
    "/api/crm/scoring-rules",
    response_model=ScoringRuleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_scoring_rule(
    payload: ScoringRuleCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ScoringRuleOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    svc = _crm(token, org_id)
    row_data = {**payload.model_dump(), "org_id": str(org_id)}
    try:
        result = svc._t("lead_scoring_rules").insert(row_data).execute()
    except Exception:
        logger.exception("crm.create_scoring_rule failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar regra")
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=502, detail="Insert returned no data")
    return ScoringRuleOut(**rows[0])


@router.patch(
    "/api/crm/scoring-rules/{rule_id}",
    response_model=ScoringRuleOut,
    status_code=status.HTTP_200_OK,
)
async def update_scoring_rule(
    rule_id: str,
    payload: ScoringRuleUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> ScoringRuleOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    svc = _crm(token, org_id)
    try:
        result = (
            svc._t("lead_scoring_rules")
            .update(data)
            .eq("org_id", str(org_id))
            .eq("id", rule_id)
            .execute()
        )
    except Exception:
        logger.exception("crm.update_scoring_rule failed org=%s id=%s", org_id, rule_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar regra")
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return ScoringRuleOut(**rows[0])


@router.delete(
    "/api/crm/scoring-rules/{rule_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_scoring_rule(
    rule_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    svc = _crm(token, org_id)
    try:
        result = (
            svc._t("lead_scoring_rules")
            .delete()
            .eq("org_id", str(org_id))
            .eq("id", rule_id)
            .execute()
        )
    except Exception:
        logger.exception("crm.delete_scoring_rule failed org=%s id=%s", org_id, rule_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar regra")
    if not (result.data or []):
        raise HTTPException(status_code=404, detail="Regra não encontrada")
    return {"ok": True, "id": rule_id}


# ---------------------------------------------------------------------------
# Public lead capture (unauthenticated)
# ---------------------------------------------------------------------------

@capture_router.post(
    "/api/capture/{org_id}",
    status_code=status.HTTP_201_CREATED,
)
async def capture_lead(
    org_id: UUID,
    payload: LeadCaptureRequest,
) -> dict:
    """Public lead capture — no auth required.

    The org_id in the URL is the public tenant identifier (shared in
    ad-forms and custom web forms). The admin client (service_role)
    bypasses RLS INSERT policy to allow the write.

    Known keys (name/email/phone/company/source/value/stage_id) map to
    lead columns; everything else lands in custom_fields JSONB.
    """
    try:
        # model_dump(mode="json") serializes UUID → str for stage_id
        raw = payload.model_dump(mode="json")
        svc = _admin_crm(org_id)
        row = svc.capture_lead(raw)
    except Exception:
        logger.exception("capture_lead failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao registrar lead")
    return {"ok": True, "id": row.get("id")}
