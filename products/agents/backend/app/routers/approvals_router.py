"""``/api/approvals`` — list pending + decide (contract §E.2,
``projects/julia-agents-academia-CONTRACT.md``).

The requester-or-admin check happens in THIS router, before calling
``broker.resolve`` — the broker's own error surface (``AlreadyDecided`` /
``Orphaned`` / ``NotFound``) doesn't express "may this caller decide".
See ``app/stores/errors.py::Orphaned`` for why that exception is imported
from ``app.stores.errors`` rather than the not-yet-built ``app.runtime.errors``.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    ADMIN_ROLES,
    get_approval_broker_dep,
    get_approval_store_dep,
    get_core_client,
    require_member,
)
from app.schemas.agents import ApprovalDecisionRequest, ApprovalListOut, ApprovalOut
from app.stores.approvals import ApprovalRecord
from app.stores.errors import AlreadyDecided, NotFound, Orphaned
from noctusai_lib.api.auth.session import AuthContext, resolve_org_role

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

_NOT_FOUND = {"detail": "Aprovação não encontrada.", "code": "not_found"}


def _approval_out(record: ApprovalRecord) -> ApprovalOut:
    return ApprovalOut(
        id=record.id,
        conversation_id=record.conversation_id,
        tool_name=record.tool_name,
        tool_input=dict(record.tool_input),
        classe=record.classe,
        resumo=record.resumo,
        diff=record.diff,
        decision=record.decision,
        decided_by=record.decided_by,
        decided_at=record.decided_at,
        requested_by=record.requested_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _approval_out_from_broker_result(org_id: UUID, result: dict) -> ApprovalOut:
    """``ApprovalBroker.resolve`` returns "the updated approvals row" as a
    plain dict (contract §E.9) — normalize UUID/str fields defensively so
    a Real broker (Postgres row, string ids) and the Fake stand-in
    (already-UUID fields) both map cleanly."""

    def _uuid(value):
        return value if isinstance(value, UUID) or value is None else UUID(str(value))

    return ApprovalOut(
        id=_uuid(result["id"]),
        conversation_id=_uuid(result["conversation_id"]),
        tool_name=result["tool_name"],
        tool_input=dict(result.get("tool_input") or {}),
        classe=result.get("classe", "escrita"),
        resumo=result["resumo"],
        diff=result.get("diff"),
        decision=result["decision"],
        decided_by=_uuid(result.get("decided_by")),
        decided_at=result.get("decided_at"),
        requested_by=_uuid(result["requested_by"]),
        created_at=result["created_at"],
        updated_at=result["updated_at"],
    )


@router.get("", response_model=ApprovalListOut)
async def list_approvals(
    estado: str = Query(default="pendente"),
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_approval_store_dep),
) -> ApprovalListOut:
    if estado != "pendente":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"detail": "estado deve ser 'pendente'.", "code": "invalid_field"},
        )
    role = resolve_org_role(get_core_client(), ctx.user_id)
    owner_user_id = None if role in ADMIN_ROLES else ctx.user_id
    records = store.list_pending(ctx.org_id, owner_user_id=owner_user_id)
    items = [_approval_out(r) for r in records]
    return ApprovalListOut(items=items, total=len(items))


@router.post("/{approval_id}/decision", response_model=ApprovalOut)
async def decide_approval(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    ctx: AuthContext = Depends(require_member),
    broker=Depends(get_approval_broker_dep),
    store=Depends(get_approval_store_dep),
) -> ApprovalOut:
    try:
        approval = store.get(ctx.org_id, approval_id)
    except NotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc

    role = resolve_org_role(get_core_client(), ctx.user_id)
    is_admin = role in ADMIN_ROLES
    if approval.requested_by != ctx.user_id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "Você não pode decidir esta aprovação.", "code": "not_allowed"},
        )

    try:
        result = await broker.resolve(
            ctx.org_id, approval_id, aprovada=payload.aprovada, decided_by=ctx.user_id
        )
    except AlreadyDecided as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Esta aprovação já foi decidida.", "code": "already_decided"},
        ) from exc
    except Orphaned as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": "Não há um turno ativo aguardando esta aprovação.",
                "code": "orphaned",
            },
        ) from exc
    except NotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc

    return _approval_out_from_broker_result(ctx.org_id, result)


__all__ = ["router"]
