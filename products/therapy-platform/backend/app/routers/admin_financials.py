"""
Admin Financials Router — Global dashboard, wallet listing, commission overrides, payouts.

All endpoints require platform_admin role.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import get_current_user, get_user_role, get_admin_client, first_or_none
from app.responses import paginated_response, success_response
from app.responses import calculate_pagination
from app.schemas.financial import CommissionConfigRequest
from app.services import payout_service
from noctusai_lib.integrations.supabase_identity import (
    UserIdentity,
    fetch_user_identities,
)
from app.services._bulk import bulk_lookup

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/financials", tags=["Admin Financials"])


def _require_admin(user) -> str:
    """Enforce platform_admin role. Returns user.id."""
    role = get_user_role(user)
    if role != "platform_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores da plataforma")
    return user.id


@router.get("/")
async def global_dashboard(
    authorization: Optional[str] = Header(None),
):
    """Global financial dashboard: total revenue, commissions, payouts."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    # Total revenue from captured transactions
    tx_result = (
        db.table("transactions")
        .select("gross_amount, platform_fee_amount, clinic_share_amount, therapist_share_amount, status")
        .eq("status", "captured")
        .execute()
    )
    transactions = tx_result.data or []

    total_gross = sum(float(tx.get("gross_amount", 0)) for tx in transactions)
    total_platform_fees = sum(float(tx.get("platform_fee_amount", 0)) for tx in transactions)
    total_clinic_share = sum(float(tx.get("clinic_share_amount") or 0) for tx in transactions)
    total_therapist_share = sum(float(tx.get("therapist_share_amount", 0)) for tx in transactions)

    # Payout summary
    payout_result = (
        db.table("payouts")
        .select("amount, net_amount, fee_amount, status")
        .execute()
    )
    payouts = payout_result.data or []

    total_payouts_requested = sum(float(p.get("amount", 0)) for p in payouts)
    total_payouts_completed = sum(
        float(p.get("net_amount", 0)) for p in payouts if p.get("status") == "completed"
    )
    total_payout_fees = sum(float(p.get("fee_amount", 0)) for p in payouts)
    pending_payouts = sum(1 for p in payouts if p.get("status") == "pending")

    # Refund summary
    refund_result = (
        db.table("refund_requests")
        .select("refund_amount, status")
        .execute()
    )
    refunds = refund_result.data or []
    total_refunded = sum(
        float(r.get("refund_amount", 0)) for r in refunds if r.get("status") == "approved"
    )
    pending_refunds = sum(1 for r in refunds if r.get("status") == "pending")

    return success_response({
        "transactions": {
            "total_count": len(transactions),
            "total_gross": total_gross,
            "total_platform_fees": total_platform_fees,
            "total_clinic_share": total_clinic_share,
            "total_therapist_share": total_therapist_share,
        },
        "payouts": {
            "total_requested": total_payouts_requested,
            "total_completed": total_payouts_completed,
            "total_fees": total_payout_fees,
            "pending_count": pending_payouts,
        },
        "refunds": {
            "total_refunded": total_refunded,
            "pending_count": pending_refunds,
        },
    })


@router.get("/wallets")
async def list_all_wallets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    owner_type: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """List all wallets (admin only)."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)
    query = db.table("wallets").select("*", count="exact")

    if owner_type:
        query = query.eq("owner_type", owner_type)

    end = offset + validated_page_size - 1
    result = query.order("last_updated", desc=True).range(offset, end).execute()

    total = result.count if result.count is not None else 0
    return paginated_response(result.data or [], total, page, page_size)


@router.post("/commissions")
async def set_commission_override(
    body: CommissionConfigRequest,
    authorization: Optional[str] = Header(None),
):
    """Set commission configuration.

    Accepts either ``global_rate_pct`` (updates ``platform_settings`` row
    keyed ``global_commission_rate``) or ``override`` (upserts a row in
    ``platform_commission_overrides``). Either or both may be sent.

    Returns ``{global_rate_pct, override}`` with the persisted values.
    """
    user, _ = await get_current_user(authorization)
    admin_id = _require_admin(user)
    db = get_admin_client()

    response: dict = {}

    if body.global_rate_pct is not None:
        new_value = str(body.global_rate_pct)
        existing_setting = (
            db.table("platform_settings")
            .select("key")
            .eq("key", "global_commission_rate")
            .execute()
        )
        if first_or_none(existing_setting):
            (
                db.table("platform_settings")
                .update({"value": new_value})
                .eq("key", "global_commission_rate")
                .execute()
            )
        else:
            (
                db.table("platform_settings")
                .insert({"key": "global_commission_rate", "value": new_value})
                .execute()
            )
        response["global_rate_pct"] = float(body.global_rate_pct)

    if body.override is not None:
        ov = body.override
        existing = (
            db.table("platform_commission_overrides")
            .select("id")
            .eq("target_type", ov.entity_type)
            .eq("target_id", ov.entity_id)
            .execute()
        )
        existing_row = first_or_none(existing)
        payload = {
            "target_type": ov.entity_type,
            "target_id": ov.entity_id,
            "custom_commission_pct": float(ov.rate_pct),
            "set_by_admin_id": admin_id,
        }
        if existing_row:
            result = (
                db.table("platform_commission_overrides")
                .update({
                    "custom_commission_pct": float(ov.rate_pct),
                    "set_by_admin_id": admin_id,
                })
                .eq("id", existing_row["id"])
                .execute()
            )
        else:
            result = (
                db.table("platform_commission_overrides")
                .insert(payload)
                .execute()
            )
        saved = first_or_none(result) or payload
        response["override"] = {
            "id": saved.get("id"),
            "entity_type": ov.entity_type,
            "entity_id": ov.entity_id,
            "rate_pct": float(ov.rate_pct),
        }

    if not response:
        raise HTTPException(
            status_code=422,
            detail="Informe global_rate_pct ou override.",
        )

    return success_response(response)


@router.get("/commissions")
async def get_commission_config(
    authorization: Optional[str] = Header(None),
):
    """Return the global commission rate + every override.

    Shape matches ``useAdminCommissions`` in
    ``frontend/src/hooks/useAdminFinancials.ts``::

        { global_rate_pct: number, overrides: CommissionOverride[] }

    Overrides include ``entity_name`` (resolved name of the clinic /
    therapist) for the admin UI to render.
    """
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    setting_result = (
        db.table("platform_settings")
        .select("value")
        .eq("key", "global_commission_rate")
        .execute()
    )
    setting_row = first_or_none(setting_result)
    try:
        global_rate_pct = float(setting_row["value"]) if setting_row else 10.0
    except (TypeError, ValueError):
        global_rate_pct = 10.0

    override_result = (
        db.table("platform_commission_overrides")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    raw_overrides = override_result.data or []

    therapist_ids = [
        row["target_id"]
        for row in raw_overrides
        if row.get("target_type") == "therapist" and row.get("target_id")
    ]
    clinic_ids = [
        row["target_id"]
        for row in raw_overrides
        if row.get("target_type") == "clinic" and row.get("target_id")
    ]

    identities = fetch_user_identities(db, therapist_ids)
    clinic_name_map = bulk_lookup(db, "clinics", clinic_ids, value_cols="name")
    clinic_name_map = {k: (v or "") for k, v in clinic_name_map.items()}

    overrides: list = []
    for row in raw_overrides:
        tid = row.get("target_id") or ""
        ttype = row.get("target_type") or ""
        if ttype == "therapist":
            identity = identities.get(tid, UserIdentity(user_id=tid))
            name = identity.nome
        elif ttype == "clinic":
            name = clinic_name_map.get(tid, "")
        else:
            name = ""
        overrides.append({
            "id": row.get("id"),
            "entity_id": tid,
            "entity_type": ttype,
            "entity_name": name,
            "rate_pct": float(row.get("custom_commission_pct", 0) or 0),
        })

    return success_response({
        "global_rate_pct": global_rate_pct,
        "overrides": overrides,
    })


@router.delete("/commissions/{override_id}")
async def delete_commission_override(
    override_id: str,
    authorization: Optional[str] = Header(None),
):
    """Delete a commission override row."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    existing = (
        db.table("platform_commission_overrides")
        .select("id")
        .eq("id", override_id)
        .execute()
    )
    if not first_or_none(existing):
        raise HTTPException(status_code=404, detail="Override não encontrado")

    (
        db.table("platform_commission_overrides")
        .delete()
        .eq("id", override_id)
        .execute()
    )
    return success_response({"id": override_id, "deleted": True})


@router.get("/summary")
async def financial_summary(
    authorization: Optional[str] = Header(None),
):
    """Return the four headline metrics shown on the admin Financials page.

    Shape matches ``AdminFinancialSummary`` in
    ``frontend/src/types/financial.ts``::

        { total_revenue, platform_fees, payouts_completed, payouts_pending }

    Aggregates from ``transactions`` (status=``captured``) and ``payouts``.
    """
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    tx_result = (
        db.table("transactions")
        .select("gross_amount, platform_fee_amount, status")
        .eq("status", "captured")
        .execute()
    )
    txs = tx_result.data or []
    total_revenue = sum(float(t.get("gross_amount", 0) or 0) for t in txs)
    platform_fees = sum(float(t.get("platform_fee_amount", 0) or 0) for t in txs)

    payout_result = (
        db.table("payouts")
        .select("amount, net_amount, status")
        .execute()
    )
    payouts = payout_result.data or []
    payouts_completed = sum(
        float(p.get("net_amount", 0) or 0)
        for p in payouts
        if p.get("status") == "completed"
    )
    payouts_pending = sum(
        float(p.get("amount", 0) or 0)
        for p in payouts
        if p.get("status") == "pending"
    )

    return success_response({
        "total_revenue": total_revenue,
        "platform_fees": platform_fees,
        "payouts_completed": payouts_completed,
        "payouts_pending": payouts_pending,
    })


@router.get("/transactions")
async def list_all_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    date_start: Optional[str] = Query(None),
    date_end: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """List all transactions for the admin console (paginated)."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    validated_page, validated_page_size, offset = calculate_pagination(page, page_size)
    query = db.table("transactions").select("*", count="exact")

    if status:
        query = query.eq("status", status)
    if date_start:
        query = query.gte("created_at", date_start)
    if date_end:
        query = query.lte("created_at", date_end)

    query = query.order("created_at", desc=True)
    end = offset + validated_page_size - 1
    result = query.range(offset, end).execute()
    total = result.count if result.count is not None else 0
    return paginated_response(result.data or [], total, page, page_size)


@router.get("/payouts")
async def list_all_payouts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    recipient_type: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """List all payouts (admin only)."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    filters = {}
    if status:
        filters["status"] = status
    if recipient_type:
        filters["recipient_type"] = recipient_type

    data, total = await payout_service.list_payouts(filters, page, page_size, db)
    return paginated_response(data, total, page, page_size)


@router.post("/payouts/{payout_id}/process")
async def process_payout(
    payout_id: str,
    authorization: Optional[str] = Header(None),
):
    """Process a pending payout (admin only). Triggers Stripe transfer."""
    user, _ = await get_current_user(authorization)
    _require_admin(user)
    db = get_admin_client()

    result = await payout_service.process_payout(payout_id, db)
    return success_response(result)
