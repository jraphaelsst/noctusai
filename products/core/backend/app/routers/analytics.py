"""
Analytics Router — Platform analytics for NoctusAI admins.

GET /api/admin/analytics/overview  — KPIs: MRR, total orgs, active orgs, churn rate, total users
GET /api/admin/analytics/revenue   — Monthly revenue breakdown (last 12 months)
GET /api/admin/analytics/tenants   — Tenant health (orgs with user count, subscription status, last active)

All endpoints require platform admin role.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Header

from app.database import get_admin_client
from app.dependencies import get_current_admin
from app.services import billing_metrics
from noctusai_lib.integrations.persistence.paging import iter_paged_rows


def _count(query) -> int:
    """Exact row count without transferring the rows (a 1-row page + count)."""
    result = query.limit(1).execute()
    if result.count is None:
        raise RuntimeError("analytics: PostgREST returned no count for a count='exact' query")
    return result.count


def _all(db, table: str, columns: str) -> list[dict]:
    """Every row of a table, paged past PostgREST's silent 1 000-row cap."""
    return list(iter_paged_rows(
        lambda start, end: db.table(table).select(columns).order("id").range(start, end).execute().data,
        label=f"analytics {table}",
    ))

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/analytics", tags=["Analytics"])


@router.get("/overview")
async def get_overview(authorization: Optional[str] = Header(None)):
    """Platform KPIs: MRR, total orgs, active orgs, churn rate, total users."""
    await get_current_admin(authorization)
    db = get_admin_client()

    # Total organizations
    total_orgs = _count(db.table("organizations").select("id", count="exact"))

    # Total users
    total_users = _count(db.table("noctus_users").select("id", count="exact"))

    # MRR: what billing subscriptions actually pay per month (trials pay
    # nothing; yearly counts /12; paged past the 1 000-row cap). See
    # `app/services/billing_metrics.py` for the fix this replaced.
    all_subs = billing_metrics.load_billing_subscriptions(db)
    mrr_result = billing_metrics.compute_mrr(all_subs, billing_metrics.load_plan_prices(db))
    mrr = float(mrr_result.as_dict()["mrr"])
    # Orgs with access through a subscription (trial included).
    active_orgs = len({
        s.get("org_id") for s in all_subs
        if s.get("status") in ("active", "trial", "past_due", "grace")
    })

    # Churn rate: canceled subs in last 30 days / total subs that were active 30 days ago
    thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    canceled_count = _count(
        db.table("subscriptions").select("id", count="exact")
        .eq("status", "canceled").gte("updated_at", thirty_days_ago)
    )

    # Total subs that existed 30 days ago (created before 30 days ago)
    total_subs_30d = _count(
        db.table("subscriptions").select("id", count="exact").lte("created_at", thirty_days_ago)
    )

    churn_rate = round((canceled_count / total_subs_30d * 100), 1) if total_subs_30d > 0 else 0.0

    return {
        "data": {
            "mrr": round(mrr, 2),
            "total_orgs": total_orgs,
            "active_orgs": active_orgs,
            "total_users": total_users,
            "churn_rate": churn_rate,
        }
    }


@router.get("/revenue")
async def get_revenue(authorization: Optional[str] = Header(None)):
    """Monthly revenue breakdown for the last 12 months."""
    await get_current_admin(authorization)
    db = get_admin_client()

    # Fetch all subscriptions with plan data from last 12 months
    twelve_months_ago = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()

    subs = list(iter_paged_rows(
        lambda start, end: db.table("subscriptions").select(
            "id, org_id, plan_id, status, started_at, canceled_at, created_at"
        ).gte("created_at", twelve_months_ago).order("id").range(start, end).execute().data,
        label="analytics subscriptions (12 months)",
    ))

    # Build monthly revenue breakdown
    months: dict = {}
    now = datetime.now(timezone.utc)
    for i in range(12):
        dt = now - timedelta(days=30 * i)
        key = dt.strftime("%Y-%m")
        months[key] = {"month": key, "new_subs": 0, "churned": 0, "mrr": 0.0}

    for sub in subs:
        created = sub.get("created_at", "")[:7]  # YYYY-MM
        canceled = (sub.get("canceled_at") or "")[:7]
        if created in months:
            months[created]["new_subs"] += 1

        if canceled and canceled in months:
            months[canceled]["churned"] += 1

    # MRR per month: every subscription that had started by that month and
    # had not been canceled yet, at what it pays per month. A row still in
    # trial/incomplete never paid, so it never counts.
    history = billing_metrics.load_billing_subscriptions(db)
    plan_prices = billing_metrics.load_plan_prices(db)
    for key in sorted(months.keys()):
        month_mrr = 0.0
        for sub in history:
            if sub.get("status") in ("trial", "incomplete"):
                continue
            started = (sub.get("started_at") or sub.get("created_at") or "")[:7]
            ended = (sub.get("canceled_at") or "")[:7]
            if not started or started > key or (ended and ended <= key):
                continue
            amount, currency = billing_metrics.monthly_amount(sub, plan_prices)
            if currency == "BRL":
                month_mrr += float(amount)
        months[key]["mrr"] = round(month_mrr, 2)

    # Return sorted by month descending
    revenue_list = sorted(months.values(), key=lambda x: x["month"], reverse=True)

    return {"data": revenue_list}


@router.get("/tenants")
async def get_tenants(authorization: Optional[str] = Header(None)):
    """Tenant health: orgs with user count, subscription status, last active."""
    await get_current_admin(authorization)
    db = get_admin_client()

    # Get all organizations
    orgs = _all(db, "organizations", "*")
    orgs.sort(key=lambda o: str(o.get("created_at") or ""), reverse=True)

    # Get user counts per org
    users = _all(db, "noctus_users", "id, org_id")
    user_counts: dict = {}
    for u in users:
        oid = u.get("org_id")
        if oid:
            user_counts[oid] = user_counts.get(oid, 0) + 1

    # Get subscriptions with plan info
    subs = _all(db, "subscriptions", "id, org_id, status, started_at, plans(nome, slug)")
    sub_map: dict = {}
    for s in subs:
        oid = s.get("org_id")
        # Keep the most recent / active subscription per org
        if oid and (oid not in sub_map or s.get("status") in ("active", "trial")):
            sub_map[oid] = s

    tenants = []
    for org in orgs:
        org_id = org["id"]
        sub = sub_map.get(org_id)
        plan_name = "Sem plano"
        sub_status = "none"
        if sub:
            sub_status = sub.get("status", "none")
            if sub.get("plans") and isinstance(sub["plans"], dict):
                plan_name = sub["plans"].get("nome", "Desconhecido")

        tenants.append({
            "org_id": org_id,
            "org_nome": org.get("nome", ""),
            "slug": org.get("slug", ""),
            "user_count": user_counts.get(org_id, 0),
            "plan": plan_name,
            "status": sub_status,
            "last_active": org.get("updated_at") or org.get("created_at"),
            "created_at": org.get("created_at"),
        })

    return {"data": tenants}
