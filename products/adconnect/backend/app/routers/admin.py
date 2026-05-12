"""
AdConnect brand-admin V1 router (Phase 6) — DB-backed.

Replaces the prior mock-JSON-backed admin.py. Surface is API-only — the brand
admin V2 UI is a follow-up project. Endpoints aggregate across the existing
domain routers (distributors / sellout / rewards / financial) so the admin
gets cross-cutting views without re-routing through each domain.

Endpoints (per PROJECT.md §6 Phase 6):
  - GET    /api/admin/dashboard          → cross-cutting metrics payload.
  - GET    /api/admin/distributors       → distributor list + per-row metrics.
  - POST   /api/admin/distributors       → onboard a new distributor.
  - PATCH  /api/admin/distributors/{id}  → update distributor fields.
  - GET    /api/admin/sellout/queue      → pending sellout reports.
  - GET    /api/admin/reward-rules       → list all rules (admin sees inactive).
  - POST   /api/admin/reward-rules       → create rule.
  - PATCH  /api/admin/reward-rules/{id}  → edit rule.
  - DELETE /api/admin/reward-rules/{id}  → soft-delete (ativa=false).
  - GET    /api/admin/invoices           → cross-distributor invoice list.

Auth: every endpoint gates via `Depends(require_role("admin", "owner"))`.
The seed's `make_require_role` returns 403 for non-admin, 401 for unauth.

LGPD: brand admin reads cross-distributor PII + financials. The flag is filed
once at module-import-time via `noctus.dev.lgpd_flag` (idempotent — the MCP
tool dedupes by code_path + concern). See LGPD-WARNINGS.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from ..dependencies import require_role
from ..database import _db as _db_module
from ..schemas.admin import (
    AdminDistributorCreateIn,
    AdminDistributorListOut,
    AdminDistributorPatchIn,
    AdminInvoiceListOut,
    AdminSelloutQueueOut,
    DashboardMetricsOut,
    DistributorWithMetricsOut,
    InvoiceStatus,
    RewardRuleIn,
    RewardRuleListOut,
    RewardRuleOut,
)
from ..services import admin_service

logger = logging.getLogger(__name__)

# Constructor-time prefix (per Phase 2/3 convention — `router.prefix = ...`
# after-the-fact is a no-op for routes already registered).
router = APIRouter(prefix="/admin", tags=["admin"])

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db() -> Any:
    """Lazy access via `_db_module` so test patches of `_db.get_client` /
    `_db.get_admin_client` are honored — module-level binds (the legacy
    `from ..database import get_admin_client` path) freeze the method at
    import time and bypass the patch."""
    try:
        client = _db_module.get_client()
    except Exception:
        client = None
    if client is None:
        try:
            client = _db_module.get_admin_client()
        except Exception:
            client = None
    if client is None:
        raise HTTPException(503, "Supabase client unavailable")
    return client


def _user_org(user: Any, org_id: Optional[str] = None) -> str:
    """Read brand ``org_id`` from the auth-resolved triple's ``org_id``
    (canonical), falling back to ``user.user_metadata.org_id``, then the
    single-instance default."""
    if org_id:
        return str(org_id)
    metadata = getattr(user, "user_metadata", None) or {}
    return str(metadata.get("org_id") or DEFAULT_ORG_ID)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=DashboardMetricsOut)
def dashboard(
    auth: tuple = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Cross-cutting metrics: distributors, pedidos this month, sellout,
    rewards, invoices. Single round-trip dashboard payload."""
    user, _token, _role = auth
    db = _db()
    return admin_service.dashboard_metrics(db, org_id=_user_org(user))


# ---------------------------------------------------------------------------
# Distributors (list / create / patch)
# ---------------------------------------------------------------------------


@router.get("/distributors", response_model=AdminDistributorListOut)
def list_distributors_with_metrics(
    auth: tuple = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Full distributor list with metrics per row."""
    user, _token, _role = auth
    db = _db()
    rows = admin_service.distributor_list_with_metrics(
        db, org_id=_user_org(user)
    )
    return {"data": rows}


@router.post(
    "/distributors",
    response_model=DistributorWithMetricsOut,
    status_code=status.HTTP_201_CREATED,
)
def create_distributor(
    body: AdminDistributorCreateIn,
    auth: tuple = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Onboard a new distributor under the brand admin's org."""
    user, _token, _role = auth
    db = _db()
    payload = body.model_dump(exclude_none=True)
    payload["org_id"] = _user_org(user)
    res = (
        db.table(admin_service.DISTRIBUTORS_TABLE)
        .insert(payload)
        .execute()
    )
    if not res.data:
        raise HTTPException(500, "Falha ao criar distribuidor")
    row = res.data[0] if isinstance(res.data, list) else res.data
    # Default the metrics block — the new distributor has no aggregates yet.
    row.setdefault("metrics", {
        "last_pedido_at": None,
        "total_pedidos": 0,
        "recompensa_balance": 0.0,
        "invoices_pending": 0,
    })
    return row


@router.patch(
    "/distributors/{distributor_id}", response_model=DistributorWithMetricsOut
)
def update_distributor(
    body: AdminDistributorPatchIn,
    distributor_id: str = Path(...),
    auth: tuple = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Update one distributor (CNPJ / contact / status / tier)."""
    user, _token, _role = auth
    db = _db()
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(400, "Nada para atualizar")
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = (
        db.table(admin_service.DISTRIBUTORS_TABLE)
        .update(payload)
        .eq("id", distributor_id)
        .eq("org_id", _user_org(user))
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(404, "Distribuidor não encontrado")
    row = rows[0] if isinstance(rows, list) else rows
    row.setdefault("metrics", {
        "last_pedido_at": None,
        "total_pedidos": 0,
        "recompensa_balance": 0.0,
        "invoices_pending": 0,
    })
    return row


# ---------------------------------------------------------------------------
# Sellout queue
# ---------------------------------------------------------------------------


@router.get("/sellout/queue", response_model=AdminSelloutQueueOut)
def sellout_review_queue(
    auth: tuple = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Sellout reports awaiting review (status pendente or em_analise)."""
    user, _token, _role = auth
    db = _db()
    rows = admin_service.sellout_queue(db, org_id=_user_org(user))
    return {"data": rows}


# ---------------------------------------------------------------------------
# Reward rules CRUD
# ---------------------------------------------------------------------------


@router.get("/reward-rules", response_model=RewardRuleListOut)
def list_reward_rules(
    only_active: bool = Query(False),
    auth: tuple = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """List reward rules. Admin sees inactive too (V2-deferred filter)."""
    user, _token, _role = auth
    db = _db()
    rows = admin_service.list_reward_rules(
        db, org_id=_user_org(user), only_active=only_active
    )
    return {"data": rows}


@router.post(
    "/reward-rules",
    response_model=RewardRuleOut,
    status_code=status.HTTP_201_CREATED,
)
def create_reward_rule(
    body: RewardRuleIn,
    auth: tuple = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Create a reward rule."""
    user, _token, _role = auth
    db = _db()
    payload = body.model_dump(mode="json", exclude_none=True)
    payload["org_id"] = _user_org(user)
    res = (
        db.table(admin_service.REGRAS_TABLE).insert(payload).execute()
    )
    if not res.data:
        raise HTTPException(500, "Falha ao criar regra de recompensa")
    return res.data[0] if isinstance(res.data, list) else res.data


@router.patch("/reward-rules/{rule_id}", response_model=RewardRuleOut)
def update_reward_rule(
    body: RewardRuleIn,
    rule_id: str = Path(...),
    auth: tuple = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """Edit a reward rule. Body is RewardRuleIn (full upsert payload)."""
    user, _token, _role = auth
    db = _db()
    payload = body.model_dump(mode="json", exclude_none=True)
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = (
        db.table(admin_service.REGRAS_TABLE)
        .update(payload)
        .eq("id", rule_id)
        .eq("org_id", _user_org(user))
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(404, "Regra não encontrada")
    return rows[0] if isinstance(rows, list) else rows


@router.delete(
    "/reward-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
def delete_reward_rule(
    rule_id: str = Path(...),
    auth: tuple = Depends(require_role("admin", "owner")),
):
    """Soft-delete: flip ativa=false. Hard-delete is V2-deferred (audit trail
    matters more than space in V1).

    Note: explicit ``response_model=None`` and the omitted ``-> None`` return
    annotation are required because ``from __future__ import annotations``
    (line 28) defers evaluation, so FastAPI 0.115's
    ``get_typed_return_annotation`` resolves the string ``"None"`` to the
    *class* ``NoneType`` (truthy) instead of the *value* ``None`` (falsy).
    The truthy class triggers the 204-must-not-have-body assertion at
    ``fastapi/routing.py:506``. Setting ``response_model=None`` short-circuits
    the placeholder resolution. See findings.md → §interesting-findings."""
    user, _token, _role = auth
    db = _db()
    res = (
        db.table(admin_service.REGRAS_TABLE)
        .update({
            "ativa": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", rule_id)
        .eq("org_id", _user_org(user))
        .execute()
    )
    rows = res.data or []
    if not rows:
        raise HTTPException(404, "Regra não encontrada")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Invoices (cross-distributor list)
# ---------------------------------------------------------------------------


@router.get("/invoices", response_model=AdminInvoiceListOut)
def list_invoices(
    invoice_status: Optional[InvoiceStatus] = Query(None, alias="status"),
    distributor_id: Optional[str] = Query(None),
    due_from: Optional[str] = Query(None),
    due_to: Optional[str] = Query(None),
    auth: tuple = Depends(require_role("admin", "owner")),
) -> dict[str, Any]:
    """List faturas across all distributors in the brand admin's org.
    Filters: status, distributor_id, due_date range."""
    user, _token, _role = auth
    db = _db()
    rows = admin_service.list_invoices_with_filters(
        db,
        org_id=_user_org(user),
        status=invoice_status,
        distributor_id=distributor_id,
        due_from=due_from,
        due_to=due_to,
    )
    return {"data": rows}


__all__ = ["router"]
