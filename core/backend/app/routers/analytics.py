"""
Analytics Router — Platform analytics for NoctusAI admins.

GET /api/admin/analytics/overview  — KPIs: MRR, total orgs, active orgs, churn rate, total users
GET /api/admin/analytics/revenue   — Monthly revenue breakdown (last 12 months)
GET /api/admin/analytics/tenants   — Tenant health (orgs with user count, subscription status, last active)

All endpoints require platform admin role.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Header

from app.database import get_admin_client
from app.dependencies import get_current_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/analytics", tags=["Analytics"])


@router.get("/overview")
async def get_overview(authorization: Optional[str] = Header(None)):
    """Platform KPIs: MRR, total orgs, active orgs, churn rate, total users."""
    await get_current_admin(authorization)
    db = get_admin_client()

    # Total organizations
    orgs_result = db.table("organizations").select("id", count="exact").execute()
    total_orgs = orgs_result.count if orgs_result.count is not None else len(orgs_result.data or [])

    # Total users
    users_result = db.table("noctus_users").select("id", count="exact").execute()
    total_users = users_result.count if users_result.count is not None else len(users_result.data or [])

    # Active subscriptions (status = 'active' or 'trial')
    active_subs = db.table("subscriptions").select(
        "id, plan_id, status"
    ).in_("status", ["active", "trial"]).execute()
    active_sub_list = active_subs.data or []
    active_orgs = len(active_sub_list)

    # Calculate MRR: sum price_monthly for all active subscriptions
    mrr = 0.0
    if active_sub_list:
        plan_ids = list({s["plan_id"] for s in active_sub_list if s.get("plan_id")})
        if plan_ids:
            plans_result = db.table("plans").select("id, price_monthly").in_("id", plan_ids).execute()
            plan_prices = {p["id"]: float(p.get("price_monthly", 0)) for p in (plans_result.data or [])}
            for sub in active_sub_list:
                mrr += plan_prices.get(sub.get("plan_id", ""), 0)

    # Churn rate: canceled subs in last 30 days / total subs that were active 30 days ago
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()

    canceled_recent = db.table("subscriptions").select(
        "id", count="exact"
    ).eq("status", "canceled").gte("updated_at", thirty_days_ago).execute()
    canceled_count = canceled_recent.count if canceled_recent.count is not None else len(canceled_recent.data or [])

    # Total subs that existed 30 days ago (created before 30 days ago)
    all_subs = db.table("subscriptions").select(
        "id", count="exact"
    ).lte("created_at", thirty_days_ago).execute()
    total_subs_30d = all_subs.count if all_subs.count is not None else len(all_subs.data or [])

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
    twelve_months_ago = (datetime.utcnow() - timedelta(days=365)).isoformat()

    subs_result = db.table("subscriptions").select(
        "id, org_id, plan_id, status, started_at, canceled_at, created_at, plans(id, name, price_monthly)"
    ).gte("created_at", twelve_months_ago).order("created_at", desc=True).execute()

    subs = subs_result.data or []

    # Build monthly revenue breakdown
    months: dict = {}
    now = datetime.utcnow()
    for i in range(12):
        dt = now - timedelta(days=30 * i)
        key = dt.strftime("%Y-%m")
        months[key] = {"month": key, "new_subs": 0, "churned": 0, "mrr": 0.0}

    for sub in subs:
        created = sub.get("created_at", "")[:7]  # YYYY-MM
        canceled = (sub.get("canceled_at") or "")[:7]
        price = 0.0
        if sub.get("plans") and isinstance(sub["plans"], dict):
            price = float(sub["plans"].get("price_monthly", 0))

        if created in months:
            months[created]["new_subs"] += 1

        if canceled and canceled in months:
            months[canceled]["churned"] += 1

    # Calculate cumulative MRR per month
    # Get all active subs and their start dates
    all_active = db.table("subscriptions").select(
        "id, plan_id, status, started_at, canceled_at, plans(price_monthly)"
    ).in_("status", ["active", "trial"]).execute()

    active_subs = all_active.data or []
    for key in sorted(months.keys()):
        month_mrr = 0.0
        for sub in active_subs:
            started = (sub.get("started_at") or sub.get("created_at", ""))[:7]
            if started <= key:
                price = 0.0
                if sub.get("plans") and isinstance(sub["plans"], dict):
                    price = float(sub["plans"].get("price_monthly", 0))
                month_mrr += price
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
    orgs_result = db.table("organizations").select("*").order("created_at", desc=True).execute()
    orgs = orgs_result.data or []

    # Get user counts per org
    users_result = db.table("noctus_users").select("id, org_id").execute()
    users = users_result.data or []
    user_counts: dict = {}
    for u in users:
        oid = u.get("org_id")
        if oid:
            user_counts[oid] = user_counts.get(oid, 0) + 1

    # Get subscriptions with plan info
    subs_result = db.table("subscriptions").select(
        "id, org_id, status, started_at, plans(name, slug)"
    ).execute()
    subs = subs_result.data or []
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
                plan_name = sub["plans"].get("name", "Desconhecido")

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
