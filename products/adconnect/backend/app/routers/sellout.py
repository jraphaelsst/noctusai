"""
Sellout router — DB-backed (replaces the mock-backed JSON variant).

Three submission endpoints (per PROJECT.md §6 Phase 4):
  - POST /api/sellout                — estruturado mode
  - POST /api/sellout/upload-nfe     — NF-e XML upload
  - POST /api/sellout/upload-attachment  — freeform attachment
  - GET  /api/sellout                — list reports (own / all-by-org)
  - PATCH /api/sellout/{id}/review   — brand admin review

Auth uses the canonical `Depends(get_current_user_org)` triple from
`app.dependencies` (the dict-wrapper `app.auth_deps` retired 2026-05-11).
RLS-style scoping is enforced in service code: a distributor user only
ever sees their own rows; admin sees everything in their org. The
`org_id` defaults to `"adconnect-default"` until the identity foundation
lands a real org_id on the JWT.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    UploadFile,
    status,
)

from ..dependencies import get_current_user_org, require_role, resolve_role
from ..database import _db
from ..schemas.sellout import (
    SelloutEstruturadoIn,
    SelloutListOut,
    SelloutOut,
    SelloutReviewIn,
)
from ..services import sellout_service
from ..services.rewards_service import accrue_for_sellout_approval

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sellout", tags=["sellout"])

DEFAULT_ORG_ID = "adconnect-default"
SELLOUT_TABLE = sellout_service.SELLOUT_TABLE


def _db_for_user() -> Any:
    """Return a Supabase client for read/write. Phase 1 will swap this to a
    user-token-bound client; in the interim we use the admin client because
    custom-JWT auth doesn't carry a Supabase session.

    Lazy attribute access on `_db` so test patches of `_db.get_client` /
    `_db.get_admin_client` are honored — module-level binds (the legacy
    `from ..database import get_supabase_client` path) freeze the method
    at import time and bypass the patch."""
    try:
        client = _db.get_client()
    except Exception:
        client = None
    if client is None:
        try:
            client = _db.get_admin_client()
        except Exception:
            client = None
    if client is None:
        raise HTTPException(503, "Supabase client unavailable")
    return client


def _user_distributor(user: Any) -> Optional[str]:
    metadata = getattr(user, "user_metadata", None) or {}
    did = metadata.get("distributor_id") or metadata.get("distributorId")
    return str(did) if did else None


def _user_org(user: Any, org_id: Optional[str] = None) -> str:
    """Read brand ``org_id`` from the auth-resolved triple's ``org_id``
    (canonical), falling back to ``user.user_metadata.org_id``, then the
    single-instance default."""
    if org_id:
        return str(org_id)
    metadata = getattr(user, "user_metadata", None) or {}
    return str(metadata.get("org_id") or DEFAULT_ORG_ID)


@router.post("/submit", response_model=SelloutOut, status_code=status.HTTP_201_CREATED)
async def submit_estruturado(
    body: SelloutEstruturadoIn,
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    user, _token, auth_org_id = auth
    distributor_id = body.distributor_id or _user_distributor(user)
    if not distributor_id:
        raise HTTPException(400, "distributor_id obrigatório")
    db = _db_for_user()
    try:
        row = await sellout_service.submit_estruturado(
            db,
            org_id=_user_org(user, auth_org_id),
            distributor_id=distributor_id,
            submitted_by=getattr(user, "id", None),
            valor_total=body.valor_total,
            quantidade_itens=body.quantidade_itens,
            periodo_inicio=body.periodo_inicio,
            periodo_fim=body.periodo_fim,
            cnpj_cliente_final=body.cnpj_cliente_final,
            descricao_resumida=body.descricao_resumida,
            items_json=body.items_json,
            observacoes=body.observacoes,
        )
    except sellout_service.SubmissionError as exc:
        raise HTTPException(400, str(exc)) from exc
    return row


@router.post(
    "/upload-nfe",
    response_model=SelloutOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_nfe(
    file: UploadFile = File(...),
    distributor_id: str = Form(...),
    periodo_inicio: Optional[str] = Form(None),
    periodo_fim: Optional[str] = Form(None),
    observacoes: Optional[str] = Form(None),
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    user, _token, auth_org_id = auth
    xml_bytes = await file.read()
    db = _db_for_user()
    try:
        row = await sellout_service.submit_nfe(
            db,
            org_id=_user_org(user, auth_org_id),
            distributor_id=distributor_id,
            submitted_by=getattr(user, "id", None),
            xml_bytes=xml_bytes,
            filename=file.filename or "sellout.xml",
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            observacoes=observacoes,
        )
    except sellout_service.SubmissionError as exc:
        raise HTTPException(400, str(exc)) from exc
    return row


@router.post(
    "/upload-attachment",
    response_model=SelloutOut,
    status_code=status.HTTP_201_CREATED,
)
async def submit_attachment(
    file: UploadFile = File(...),
    distributor_id: str = Form(...),
    periodo_inicio: Optional[str] = Form(None),
    periodo_fim: Optional[str] = Form(None),
    observacoes: Optional[str] = Form(None),
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    user, _token, auth_org_id = auth
    file_bytes = await file.read()
    db = _db_for_user()
    try:
        row = await sellout_service.submit_attachment(
            db,
            org_id=_user_org(user, auth_org_id),
            distributor_id=distributor_id,
            submitted_by=getattr(user, "id", None),
            file_bytes=file_bytes,
            filename=file.filename or "sellout.bin",
            content_type=file.content_type or "application/octet-stream",
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            observacoes=observacoes,
        )
    except sellout_service.SubmissionError as exc:
        raise HTTPException(400, str(exc)) from exc
    return row


@router.get("/list", response_model=SelloutListOut)
def list_reports(
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    user, _token, _org_id = auth
    db = _db_for_user()
    distributor_id = _user_distributor(user)
    role = resolve_role(user)
    builder = db.table(SELLOUT_TABLE).select("*")
    if role == "admin":
        # Tenant scoping for admin runs through RLS:
        # `sellout_brand_admin_sees_all` policy joins through
        # `distributors.org_id == auth.jwt.org_id`. The previous
        # `.eq("org_id", ...)` filtered a column that doesn't exist on
        # `relatorios_sellout` (would error in production; mock accepts).
        pass
    elif distributor_id:
        builder = builder.eq("distributor_id", distributor_id)
    else:
        raise HTTPException(403, "Sem distribuidor associado")
    res = builder.execute()
    rows = list(res.data or [])
    return {"data": rows}


@router.patch("/{report_id}/review", response_model=SelloutOut)
async def review_report(
    body: SelloutReviewIn,
    report_id: str = Path(...),
    auth: tuple = Depends(require_role("admin")),
) -> dict[str, Any]:
    user, _token, _role = auth
    db = _db_for_user()
    try:
        row = await sellout_service.review(
            db,
            relatorio_id=report_id,
            status=body.status,
            review_notes=body.review_notes,
            reviewed_by=getattr(user, "id", None),
            org_id=_user_org(user),
        )
    except sellout_service.SubmissionError as exc:
        raise HTTPException(400, str(exc)) from exc

    # Reward accrual on approval — fire-and-don't-fail-the-review.
    if body.status == "aprovado":
        try:
            accrued = accrue_for_sellout_approval(
                db, relatorio_id=report_id, relatorio_row=row
            )
            logger.info(
                "sellout.review: %d accruals booked for relatorio %s",
                len(accrued),
                report_id,
            )
        except Exception as exc:
            logger.warning(
                "sellout.review: accrual hook failed for %s (%s)", report_id, exc
            )
    return row


__all__ = ["router"]
