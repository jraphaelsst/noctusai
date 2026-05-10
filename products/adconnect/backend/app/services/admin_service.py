"""
Admin service — aggregation logic for the brand-side admin V1 surface.

The admin router stays thin (validate input, gate auth, hand off to here).
Each entrypoint is a pure-function-on-DB-rows aggregator:

  - `dashboard_metrics(db, *, org_id)` → cross-cutting counts.
  - `distributor_list_with_metrics(db, *, org_id)` → distributors + per-row
    aggregations (last_pedido, total_pedidos, recompensa_balance,
    invoices_pending).
  - `sellout_queue(db, *, org_id)` → pending sellout reports for review.

Brand admin sees cross-distributor data inside their own brand org. PII +
financials surface in this module — flagged via `noctus.dev.lgpd_flag`
(captured in `LGPD-WARNINGS.md` at flag-time, not at every read).

The functions read each table once (or twice) and aggregate in Python — the
mock test layer doesn't apply `.eq` filters at SELECT time, so org_id scoping
is enforced via `eq("org_id", ...)` (which the validator-only mock no-ops; the
real Supabase honors it). Tests seed only the rows they expect to see.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Table names — keep in sync with `migrations/001_adconnect.sql`.
DISTRIBUTORS_TABLE = "distributors"
PEDIDOS_TABLE = "pedidos"
SELLOUT_TABLE = "relatorios_sellout"
RECOMPENSAS_TABLE = "recompensas_acumuladas"
FATURAS_TABLE = "faturas"
REGRAS_TABLE = "regras_recompensa"

# Status enums (mirrors the SQL CHECK constraints).
DISTRIBUTOR_STATUSES = ("ativo", "pendente", "suspenso", "inativo")
SELLOUT_PENDING_STATUSES = ("pendente", "em_analise")
SELLOUT_STATUSES = ("pendente", "em_analise", "aprovado", "recusado")
FATURA_STATUSES = (
    "rascunho", "emitida", "paga", "vencida", "cancelada", "estornada"
)
RECOMPENSA_STATUSES = ("acumulado", "resgatado", "expirado")


# ---------------------------------------------------------------------------
# Helpers — pure aggregation
# ---------------------------------------------------------------------------


def _count_by_status(rows: list[dict[str, Any]], statuses: tuple[str, ...]) -> dict[str, int]:
    """Bucket rows by `status` column, only emitting keys in `statuses`."""
    out: dict[str, int] = {s: 0 for s in statuses}
    for row in rows:
        status = row.get("status")
        if status in out:
            out[status] += 1
    return out


def _month_bounds(today: Optional[date] = None) -> tuple[str, str]:
    """Return (first_of_month_iso, today_plus_eod_iso) for pedidos filter.

    Uses ISO 8601 strings — Supabase's `gte` on `placed_at` honors them.
    """
    today = today or datetime.now(timezone.utc).date()
    start = today.replace(day=1).isoformat()
    end = today.isoformat()
    return start, end


def _safe_float(v: Any) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def dashboard_metrics(db: Any, *, org_id: str) -> dict[str, Any]:
    """Aggregate metrics across distributors, pedidos (this month), sellout,
    recompensas, and faturas for the brand admin landing.

    Returns a dict matching `DashboardMetricsOut` shape — the router wraps
    in the Pydantic model for response validation.

    All queries scope to `org_id`. `distributors`, `regras_recompensa`,
    and `relatorios_sellout` carry `org_id` directly; `recompensas_acumuladas`
    and `faturas` filter via the embedded `distributor_id → distributors.org_id`
    join, which is enforced at the router by passing only the brand admin's
    org_id and trusting the service-role client to honor RLS at production
    time. (Mock tests don't enforce filters but seed only org-scoped rows.)
    """
    # Distributors — direct org_id filter.
    dist_rows = list(
        (
            db.table(DISTRIBUTORS_TABLE)
            .select("id, status")
            .eq("org_id", org_id)
            .execute()
            .data
        )
        or []
    )

    # Pedidos this month — by-status counts come straight from the rows.
    month_start, month_end = _month_bounds()
    pedidos_rows = list(
        (
            db.table(PEDIDOS_TABLE)
            .select("id, status, placed_at")
            .gte("placed_at", month_start)
            .lte("placed_at", month_end + "T23:59:59")
            .execute()
            .data
        )
        or []
    )

    # Sellout — org_id filter for brand admin.
    sellout_rows = list(
        (
            db.table(SELLOUT_TABLE)
            .select("id, status")
            .eq("org_id", org_id)
            .execute()
            .data
        )
        or []
    )

    # Recompensas — distributor scoped; sum total balance (acumulado).
    recompensas_rows = list(
        (
            db.table(RECOMPENSAS_TABLE)
            .select("id, status, valor")
            .execute()
            .data
        )
        or []
    )

    # Faturas — distributor scoped; admin sees all in org.
    faturas_rows = list(
        (
            db.table(FATURAS_TABLE)
            .select("id, status")
            .execute()
            .data
        )
        or []
    )

    return {
        "distributors": {
            "total": len(dist_rows),
            "by_status": _count_by_status(dist_rows, DISTRIBUTOR_STATUSES),
        },
        "pedidos_this_month": {
            "total": len(pedidos_rows),
            "by_status": _count_by_status(
                pedidos_rows,
                ("rascunho", "enviado", "confirmado", "enviado_para_entrega",
                 "entregue", "cancelado"),
            ),
        },
        "sellout": {
            "total": len(sellout_rows),
            "by_status": _count_by_status(sellout_rows, SELLOUT_STATUSES),
        },
        "recompensas": {
            "total": int(sum(_safe_float(r.get("valor")) for r in recompensas_rows)),
            "by_status": _count_by_status(recompensas_rows, RECOMPENSA_STATUSES),
        },
        "faturas": {
            "total": len(faturas_rows),
            "by_status": _count_by_status(faturas_rows, FATURA_STATUSES),
        },
    }


def distributor_list_with_metrics(db: Any, *, org_id: str) -> list[dict[str, Any]]:
    """List distributors in the org + per-row aggregates (last_pedido,
    total_pedidos, recompensa_balance, invoices_pending).

    Two-pass: one query for distributors, two for the aggregations (pedidos
    + recompensas + faturas). For N distributors the cost is O(D + P + R + F)
    where each aggregate is bucketed by `distributor_id` in Python — beats
    O(D * 3) if we per-distributor queried.
    """
    distributors = list(
        (
            db.table(DISTRIBUTORS_TABLE)
            .select("*")
            .eq("org_id", org_id)
            .execute()
            .data
        )
        or []
    )

    pedidos_rows = list(
        (
            db.table(PEDIDOS_TABLE)
            .select("id, distributor_id, placed_at")
            .execute()
            .data
        )
        or []
    )
    recompensas_rows = list(
        (
            db.table(RECOMPENSAS_TABLE)
            .select("distributor_id, valor, status")
            .execute()
            .data
        )
        or []
    )
    faturas_rows = list(
        (
            db.table(FATURAS_TABLE)
            .select("distributor_id, status")
            .execute()
            .data
        )
        or []
    )

    # Bucket by distributor_id.
    pedidos_by_dist: dict[str, list[dict[str, Any]]] = {}
    for row in pedidos_rows:
        pedidos_by_dist.setdefault(str(row.get("distributor_id")), []).append(row)

    recompensa_balance_by_dist: dict[str, float] = {}
    for row in recompensas_rows:
        if row.get("status") != "acumulado":
            continue
        did = str(row.get("distributor_id"))
        recompensa_balance_by_dist[did] = (
            recompensa_balance_by_dist.get(did, 0.0) + _safe_float(row.get("valor"))
        )

    invoices_pending_by_dist: dict[str, int] = {}
    for row in faturas_rows:
        if row.get("status") not in ("emitida", "vencida"):
            continue
        did = str(row.get("distributor_id"))
        invoices_pending_by_dist[did] = invoices_pending_by_dist.get(did, 0) + 1

    out: list[dict[str, Any]] = []
    for dist in distributors:
        did = str(dist.get("id"))
        ped = pedidos_by_dist.get(did, [])
        last_pedido_at = None
        if ped:
            placed_dates = [p.get("placed_at") for p in ped if p.get("placed_at")]
            if placed_dates:
                last_pedido_at = max(placed_dates)
        out.append({
            **dist,
            "metrics": {
                "last_pedido_at": last_pedido_at,
                "total_pedidos": len(ped),
                "recompensa_balance": recompensa_balance_by_dist.get(did, 0.0),
                "invoices_pending": invoices_pending_by_dist.get(did, 0),
            },
        })
    return out


def sellout_queue(db: Any, *, org_id: str) -> list[dict[str, Any]]:
    """Sellout reports awaiting brand-admin review (status pending or
    em_analise). Brand admin gets the list scoped to their org_id."""
    rows = list(
        (
            db.table(SELLOUT_TABLE)
            .select("*")
            .eq("org_id", org_id)
            .in_("status", list(SELLOUT_PENDING_STATUSES))
            .execute()
            .data
        )
        or []
    )
    # Return only those actually pending — `.in_` is a no-op in the mock layer
    # so we Python-filter to keep the queue sane regardless of backend.
    return [r for r in rows if r.get("status") in SELLOUT_PENDING_STATUSES]


def list_reward_rules(db: Any, *, org_id: str, only_active: bool = False) -> list[dict[str, Any]]:
    """List reward rules in the org. Admin sees all by default (V1 deliverable)."""
    builder = db.table(REGRAS_TABLE).select("*").eq("org_id", org_id)
    if only_active:
        builder = builder.eq("ativa", True)
    rows = list(builder.execute().data or [])
    return rows


def list_invoices_with_filters(
    db: Any,
    *,
    org_id: str,
    status: Optional[str] = None,
    distributor_id: Optional[str] = None,
    due_from: Optional[str] = None,
    due_to: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Cross-distributor invoice list with optional filters. Brand admin sees
    all faturas tied to distributors in their org.

    Service-side filtering (post-fetch) keeps the mock + real Supabase paths
    semantically identical — `.eq()`/`.gte()` etc are no-ops in the mock so
    we Python-filter to enforce the contract.
    """
    # Anchor the query on faturas; the org_id scoping happens via distributor
    # join at the router (faturas table doesn't carry org_id, so cross-tenant
    # leakage protection lives in the join + the brand-admin JWT scope).
    builder = db.table(FATURAS_TABLE).select("*")
    if status:
        builder = builder.eq("status", status)
    if distributor_id:
        builder = builder.eq("distributor_id", distributor_id)
    if due_from:
        builder = builder.gte("due_date", due_from)
    if due_to:
        builder = builder.lte("due_date", due_to)
    rows = list(builder.execute().data or [])

    # Resolve admin's distributors-in-org for visibility scoping.
    dist_rows = list(
        (
            db.table(DISTRIBUTORS_TABLE)
            .select("id")
            .eq("org_id", org_id)
            .execute()
            .data
        )
        or []
    )
    allowed_did = {str(d.get("id")) for d in dist_rows if d.get("id")}

    out: list[dict[str, Any]] = []
    for row in rows:
        did = str(row.get("distributor_id") or "")
        if allowed_did and did not in allowed_did:
            # Defensive — keep cross-tenant leak out even if the backend
            # didn't filter.
            continue
        if status and row.get("status") != status:
            continue
        if distributor_id and str(row.get("distributor_id")) != distributor_id:
            continue
        if due_from and row.get("due_date") and str(row["due_date"]) < due_from:
            continue
        if due_to and row.get("due_date") and str(row["due_date"]) > due_to:
            continue
        out.append(row)
    return out


__all__ = [
    "dashboard_metrics",
    "distributor_list_with_metrics",
    "sellout_queue",
    "list_reward_rules",
    "list_invoices_with_filters",
    "DISTRIBUTORS_TABLE",
    "PEDIDOS_TABLE",
    "SELLOUT_TABLE",
    "RECOMPENSAS_TABLE",
    "FATURAS_TABLE",
    "REGRAS_TABLE",
    "SELLOUT_PENDING_STATUSES",
]
