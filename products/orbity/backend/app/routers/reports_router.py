"""
Reports router — report definitions CRUD, snapshot generation, and the
public token-gated read endpoint.

Auth boundary:
  - All /api/reports/* (except public) → Depends(get_current_user_org) → strict 401
  - GET /api/reports/public/{token}   → unauthenticated public endpoint
    (uses admin/service_role client; server validates token server-side)

Endpoints:
  GET    /api/reports                         list reports for org
  POST   /api/reports                         create report → 201
  GET    /api/reports/{id}                    get report
  PATCH  /api/reports/{id}                    update report
  DELETE /api/reports/{id}                    delete report
  GET    /api/reports/{id}/snapshots          list snapshots for report
  POST   /api/reports/{id}/generate           generate snapshot → 201

  GET    /api/reports/public/{token}          PUBLIC token-gated report read
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
from app.schemas.reports import (
    PublicReportOut,
    ReportCreate,
    ReportOut,
    ReportSnapshotOut,
    ReportUpdate,
)
from app.services.reports_service import ReportsPublicService, ReportsService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Reports"])
public_reports_router = APIRouter(tags=["Reports Public"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc(token: str, org_id: UUID) -> ReportsService:
    return ReportsService(get_user_client(token), org_id=org_id)


def _public_svc() -> ReportsPublicService:
    """Public read service backed by the admin (service_role) client.

    Service_role bypasses RLS — safe because the server validates the token
    server-side (status, expiry) before returning any data. No client-supplied
    org_id is ever trusted.
    """
    return ReportsPublicService(get_admin_client())


# ---------------------------------------------------------------------------
# Reports CRUD (authenticated)
# ---------------------------------------------------------------------------

@router.get("/api/reports", status_code=status.HTTP_200_OK)
async def list_reports(
    client_id: str | None = Query(default=None),
    report_status: str | None = Query(default=None, alias="status"),
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_reports(client_id=client_id, status=report_status)
    except Exception:
        logger.exception("reports.list failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar relatórios")


@router.post(
    "/api/reports",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_report(
    payload: ReportCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ReportOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_report(
            payload.model_dump(mode="json", exclude_none=True)
        )
    except Exception:
        logger.exception("reports.create failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar relatório")
    return ReportOut(**row)


@router.get(
    "/api/reports/{report_id}",
    response_model=ReportOut,
    status_code=status.HTTP_200_OK,
)
async def get_report(
    report_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ReportOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_report(report_id)
    except Exception:
        logger.exception("reports.get failed org=%s id=%s", org_id, report_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar relatório")
    if not row:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    return ReportOut(**row)


@router.patch(
    "/api/reports/{report_id}",
    response_model=ReportOut,
    status_code=status.HTTP_200_OK,
)
async def update_report(
    report_id: str,
    payload: ReportUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> ReportOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(mode="json", exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_report(report_id, data)
    except Exception:
        logger.exception("reports.update failed org=%s id=%s", org_id, report_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar relatório")
    if not row:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    return ReportOut(**row)


@router.delete("/api/reports/{report_id}", status_code=status.HTTP_200_OK)
async def delete_report(
    report_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_report(report_id)
    except Exception:
        logger.exception("reports.delete failed org=%s id=%s", org_id, report_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar relatório")
    if not ok:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    return {"ok": True, "id": report_id}


# ---------------------------------------------------------------------------
# Snapshots (authenticated)
# ---------------------------------------------------------------------------

@router.get(
    "/api/reports/{report_id}/snapshots",
    status_code=status.HTTP_200_OK,
)
async def list_snapshots(
    report_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_snapshots(report_id)
    except Exception:
        logger.exception("reports.snapshots failed org=%s report=%s", org_id, report_id)
        raise HTTPException(status_code=502, detail="Falha ao listar snapshots")


@router.post(
    "/api/reports/{report_id}/generate",
    response_model=ReportSnapshotOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_snapshot(
    report_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ReportSnapshotOut:
    """Aggregate metrics for the report period and save a frozen snapshot."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).generate_snapshot(report_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception("reports.generate failed org=%s report=%s", org_id, report_id)
        raise HTTPException(status_code=502, detail="Falha ao gerar snapshot")
    return ReportSnapshotOut(**row)


# ---------------------------------------------------------------------------
# Public report read (unauthenticated — token-gated)
# ---------------------------------------------------------------------------

@public_reports_router.get(
    "/api/reports/public/{token}",
    response_model=PublicReportOut,
    status_code=status.HTTP_200_OK,
)
async def get_public_report(token: str) -> PublicReportOut:
    """Token-gated public report — no authentication required.

    The token IS the authorization. The server validates:
      1. Token exists in orbity.reports.
      2. status == "published".
      3. expires_at is NULL or in the future.
    Then returns the latest snapshot payload.

    Returns 404 for not-found, not-published, or expired reports to avoid
    leaking the existence of draft/expired reports via 403.
    """
    try:
        result = _public_svc().get_published_report_by_token(token)
    except Exception:
        logger.exception("reports.public_read token=%s failed", token)
        raise HTTPException(status_code=502, detail="Falha ao buscar relatório público")

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Relatório não encontrado, não publicado ou expirado",
        )

    report = result["report"]
    snapshot = result.get("snapshot")

    return PublicReportOut(
        report_id=report["id"],
        name=report["name"],
        period_start=report["period_start"],
        period_end=report["period_end"],
        status=report["status"],
        expires_at=report.get("expires_at"),
        snapshot_id=snapshot["id"] if snapshot else None,
        generated_at=snapshot["generated_at"] if snapshot else None,
        payload=snapshot["payload"] if snapshot else {},
    )
