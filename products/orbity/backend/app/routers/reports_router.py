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

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from noctusai_lib.api.rate_limit import client_ip_key

from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_current_user_org,
    get_org_client,
)
from app.schemas.reports import (
    PublicReportOut,
    ReportCreate,
    ReportOut,
    ReportSnapshotOut,
    ReportUpdate,
)
from app.rate_limit import limiter
from noctusai_lib.api.access_tiers import access_tier
from noctusai_lib.api.token_link import TokenLinkGone, TokenLinkNotFound, resolve_token_link, token_fingerprint

from app.services.reports_service import ReportsPublicService, ReportsService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Reports"])
public_reports_router = APIRouter(tags=["Reports Public"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc(token: str, org_id: UUID) -> ReportsService:
    return ReportsService(get_org_client(org_id), org_id=org_id)


def _public_svc() -> ReportsPublicService:
    """Public read service backed by the admin (service_role) client.

    Service_role bypasses RLS — safe because the server validates the token
    server-side (status, expiry) before returning any data. No client-supplied
    org_id is ever trusted.
    """
    return ReportsPublicService(get_admin_client())  # org-scope-ok: public token link, org derived from the token row


# ---------------------------------------------------------------------------
# Reports CRUD (authenticated)
# ---------------------------------------------------------------------------

@router.get("/api/reports", status_code=status.HTTP_200_OK)
def list_reports(
    client_id: str | None = Query(default=None),
    report_status: str | None = Query(default=None, alias="status"),
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_reports(client_id=client_id, status=report_status)
    except HTTPException:
        raise
    except Exception:
        logger.exception("reports.list failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar relatórios")


@router.post(
    "/api/reports",
    response_model=ReportOut,
    status_code=status.HTTP_201_CREATED,
)
def create_report(
    payload: ReportCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ReportOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_report(
            payload.model_dump(mode="json", exclude_none=True)
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("reports.create failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar relatório")
    return ReportOut(**row)


@router.get(
    "/api/reports/{report_id}",
    response_model=ReportOut,
    status_code=status.HTTP_200_OK,
)
def get_report(
    report_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ReportOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_report(report_id)
    except HTTPException:
        raise
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
def update_report(
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
    except HTTPException:
        raise
    except Exception:
        logger.exception("reports.update failed org=%s id=%s", org_id, report_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar relatório")
    if not row:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    return ReportOut(**row)


@router.delete("/api/reports/{report_id}", status_code=status.HTTP_200_OK)
def delete_report(
    report_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_report(report_id)
    except HTTPException:
        raise
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
def list_snapshots(
    report_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_snapshots(report_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception("reports.snapshots failed org=%s report=%s", org_id, report_id)
        raise HTTPException(status_code=502, detail="Falha ao listar snapshots")


@router.post(
    "/api/reports/{report_id}/generate",
    response_model=ReportSnapshotOut,
    status_code=status.HTTP_201_CREATED,
)
def generate_snapshot(
    report_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ReportSnapshotOut:
    """Aggregate metrics for the report period and save a frozen snapshot."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).generate_snapshot(report_id)
    except LookupError as exc:
        logger.warning("reports.generate refused org=%s report=%s: %s", org_id, report_id, type(exc).__name__)
        raise HTTPException(status_code=404, detail="report_not_found")
    except HTTPException:
        raise
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
@access_tier("public", reason="published-report link: unguessable token, server-checked expiry (fails closed), org-scoped snapshot read, no internal ids returned", category="token-link")
# shared_limit(scope=) pins the bucket: slowapi's default scope is the request PATH, which here contains the token -- every guess would get a
# fresh bucket and the limit would never trip.
@limiter.shared_limit("30/minute;300/hour", scope="report-public", key_func=client_ip_key)
def get_public_report(request: Request, token: str) -> PublicReportOut:
    """Token-gated public report (``token-link`` tier) -- no authentication, the link IS the credential.

    The token is resolved ONLY through ``resolve_token_link``: malformed or unknown (or a draft) is 404 -- indistinguishable,
    so draft/expired reports are not leaked; an expired link is 410 and a missing/unparsable ``expires_at`` counts as
    expired. The latest snapshot is read inside the report's own org. The response is an explicit public view: no ids."""
    not_found_detail = "Relatório não encontrado, não publicado ou expirado"
    svc = _public_svc()
    try:
        report = resolve_token_link(token, svc.fetch_published_report)
        snapshot = svc.latest_snapshot(report)
    except (TokenLinkNotFound, TokenLinkGone):
        # one answer for unknown / draft / expired, as before: a link that cannot be used reveals nothing
        raise HTTPException(status_code=404, detail=not_found_detail)
    except HTTPException:
        raise
    except Exception:
        logger.exception("reports.public_read %s failed", token_fingerprint(token))
        raise HTTPException(status_code=502, detail="Falha ao buscar relatório público")

    return PublicReportOut(
        name=report["name"],
        period_start=report["period_start"],
        period_end=report["period_end"],
        status=report["status"],
        expires_at=report.get("expires_at"),
        generated_at=snapshot["generated_at"] if snapshot else None,
        payload=snapshot["payload"] if snapshot else {},
    )
