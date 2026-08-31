"""
Automation router — WhatsApp flow engine CRUD + trigger + run-due.

Auth boundary:
  All /api/automation/* → Depends(get_current_user_org) → strict 401.

Endpoints:
  GET    /api/automation/flows                         list flows
  POST   /api/automation/flows                         create flow → 201
  GET    /api/automation/flows/{flow_id}               get flow
  PATCH  /api/automation/flows/{flow_id}               update flow
  DELETE /api/automation/flows/{flow_id}               delete flow

  GET    /api/automation/flows/{flow_id}/steps         list steps (ordered)
  POST   /api/automation/flows/{flow_id}/steps         add step → 201
  PATCH  /api/automation/steps/{step_id}               update step
  DELETE /api/automation/steps/{step_id}               delete step

  POST   /api/automation/flows/{flow_id}/trigger       trigger a flow for a lead → 201
  GET    /api/automation/executions                    list executions (org-scoped)
  GET    /api/automation/executions/{execution_id}     not implemented (list covers it)
  DELETE /api/automation/executions/{execution_id}     cancel execution

  POST   /api/automation/run-due                       process due pending_actions
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    coerce_org_uuid,
    get_current_user_org,
    get_user_client,
)
from app.schemas.automation import (
    ExecutionOut,
    FlowCreate,
    FlowOut,
    FlowTriggerRequest,
    FlowUpdate,
    RunDueResult,
    StepCreate,
    StepOut,
    StepUpdate,
)
from app.services.automation_service import AutomationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Automation"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _svc(token: str, org_id: UUID) -> AutomationService:
    return AutomationService(get_user_client(token), org_id=org_id)


# ---------------------------------------------------------------------------
# Flows CRUD
# ---------------------------------------------------------------------------

@router.get("/api/automation/flows", status_code=status.HTTP_200_OK)
async def list_flows(
    active_only: bool = Query(default=False),
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_flows(active_only=active_only)
    except Exception:
        logger.exception("automation.list_flows failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar fluxos")


@router.post(
    "/api/automation/flows",
    response_model=FlowOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_flow(
    payload: FlowCreate,
    auth: tuple = Depends(get_current_user_org),
) -> FlowOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_flow(payload.model_dump(exclude_none=True))
    except Exception:
        logger.exception("automation.create_flow failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar fluxo")
    return FlowOut(**row)


@router.get(
    "/api/automation/flows/{flow_id}",
    response_model=FlowOut,
    status_code=status.HTTP_200_OK,
)
async def get_flow(
    flow_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> FlowOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_flow(flow_id)
    except Exception:
        logger.exception("automation.get_flow failed org=%s id=%s", org_id, flow_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar fluxo")
    if not row:
        raise HTTPException(status_code=404, detail="Fluxo não encontrado")
    return FlowOut(**row)


@router.patch(
    "/api/automation/flows/{flow_id}",
    response_model=FlowOut,
    status_code=status.HTTP_200_OK,
)
async def update_flow(
    flow_id: str,
    payload: FlowUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> FlowOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_flow(flow_id, data)
    except Exception:
        logger.exception("automation.update_flow failed org=%s id=%s", org_id, flow_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar fluxo")
    if not row:
        raise HTTPException(status_code=404, detail="Fluxo não encontrado")
    return FlowOut(**row)


@router.delete("/api/automation/flows/{flow_id}", status_code=status.HTTP_200_OK)
async def delete_flow(
    flow_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_flow(flow_id)
    except Exception:
        logger.exception("automation.delete_flow failed org=%s id=%s", org_id, flow_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar fluxo")
    if not ok:
        raise HTTPException(status_code=404, detail="Fluxo não encontrado")
    return {"ok": True, "id": flow_id}


# ---------------------------------------------------------------------------
# Steps CRUD
# ---------------------------------------------------------------------------

@router.get(
    "/api/automation/flows/{flow_id}/steps",
    status_code=status.HTTP_200_OK,
)
async def list_steps(
    flow_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_steps(flow_id)
    except Exception:
        logger.exception("automation.list_steps failed org=%s flow=%s", org_id, flow_id)
        raise HTTPException(status_code=502, detail="Falha ao listar passos")


@router.post(
    "/api/automation/flows/{flow_id}/steps",
    response_model=StepOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_step(
    flow_id: str,
    payload: StepCreate,
    auth: tuple = Depends(get_current_user_org),
) -> StepOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_step(
            flow_id, payload.model_dump(exclude_none=True)
        )
    except Exception:
        logger.exception("automation.create_step failed org=%s flow=%s", org_id, flow_id)
        raise HTTPException(status_code=502, detail="Falha ao criar passo")
    return StepOut(**row)


@router.patch(
    "/api/automation/steps/{step_id}",
    response_model=StepOut,
    status_code=status.HTTP_200_OK,
)
async def update_step(
    step_id: str,
    payload: StepUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> StepOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_step(step_id, data)
    except Exception:
        logger.exception("automation.update_step failed org=%s id=%s", org_id, step_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar passo")
    if not row:
        raise HTTPException(status_code=404, detail="Passo não encontrado")
    return StepOut(**row)


@router.delete("/api/automation/steps/{step_id}", status_code=status.HTTP_200_OK)
async def delete_step(
    step_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_step(step_id)
    except Exception:
        logger.exception("automation.delete_step failed org=%s id=%s", org_id, step_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar passo")
    if not ok:
        raise HTTPException(status_code=404, detail="Passo não encontrado")
    return {"ok": True, "id": step_id}


# ---------------------------------------------------------------------------
# Flow trigger
# ---------------------------------------------------------------------------

@router.post(
    "/api/automation/flows/{flow_id}/trigger",
    response_model=ExecutionOut,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_flow(
    flow_id: str,
    payload: FlowTriggerRequest,
    auth: tuple = Depends(get_current_user_org),
) -> ExecutionOut:
    """Start a new execution for this flow against the given lead."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).start_execution(
            flow_id=flow_id,
            lead_id=str(payload.lead_id),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception(
            "automation.trigger_flow failed org=%s flow=%s lead=%s",
            org_id, flow_id, payload.lead_id,
        )
        raise HTTPException(status_code=502, detail="Falha ao iniciar execução")
    return ExecutionOut(**row)


# ---------------------------------------------------------------------------
# Executions
# ---------------------------------------------------------------------------

@router.get("/api/automation/executions", status_code=status.HTTP_200_OK)
async def list_executions(
    lead_id: str | None = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_executions(lead_id=lead_id)
    except Exception:
        logger.exception("automation.list_executions failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar execuções")


@router.delete(
    "/api/automation/executions/{execution_id}",
    status_code=status.HTTP_200_OK,
)
async def cancel_execution(
    execution_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).cancel_execution(execution_id)
    except Exception:
        logger.exception(
            "automation.cancel_execution failed org=%s id=%s", org_id, execution_id
        )
        raise HTTPException(status_code=502, detail="Falha ao cancelar execução")
    if not row:
        raise HTTPException(status_code=404, detail="Execução não encontrada")
    return {"ok": True, "id": execution_id}


# ---------------------------------------------------------------------------
# run-due — process pending actions
# ---------------------------------------------------------------------------

@router.post(
    "/api/automation/run-due",
    response_model=RunDueResult,
    status_code=status.HTTP_200_OK,
)
async def run_due(
    auth: tuple = Depends(get_current_user_org),
) -> RunDueResult:
    """Process due automation_pending_actions for this org.

    Intended to be called by the scheduler (pg_cron / Celery beat).
    NOC-REMEDIATE[orbity-automation-scheduler] — attach real trigger. — 2026-06-03
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        counts = _svc(token, org_id).run_due()
    except Exception:
        logger.exception("automation.run_due failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao processar ações pendentes")
    return RunDueResult(**counts)
