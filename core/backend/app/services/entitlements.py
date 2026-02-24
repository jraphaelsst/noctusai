"""
NoctusAI Core — Entitlement & Feature Gating Service.

Checks plan limits and feature flags for organizations based on their
active subscription and plan configuration.

Plans table fields used:
  - max_users (int, -1 = unlimited)
  - max_products (int, -1 = unlimited)
  - features (jsonb, e.g. {"sso": true, "webhooks": true, "audit_logs": true})
"""
import logging
from app.database import get_admin_client

logger = logging.getLogger(__name__)


async def _get_org_plan(org_id: str) -> dict | None:
    """Get the active plan for an organization via its subscription."""
    db = get_admin_client()

    result = db.table("subscriptions").select(
        "*, plans(*)"
    ).eq("org_id", org_id).eq("status", "active").execute()

    if not result.data:
        return None
    return result.data[0].get("plans")


async def _is_test_org(org_id: str) -> bool:
    """Check if an organization is a test org (always passes all checks)."""
    db = get_admin_client()
    result = db.table("organizations").select("category").eq("id", org_id).single().execute()
    if result.data and result.data.get("category") == "test":
        return True
    return False


async def check_user_limit(org_id: str) -> dict:
    """
    Check if the organization can add more users based on the plan's max_users.

    Returns:
        {
            "allowed": bool,
            "current": int,
            "limit": int,         # -1 means unlimited
            "remaining": int | None
        }
    """
    # Test orgs always pass
    if await _is_test_org(org_id):
        return {"allowed": True, "current": 0, "limit": -1, "remaining": None}

    plan = await _get_org_plan(org_id)
    if not plan:
        return {"allowed": False, "current": 0, "limit": 0, "remaining": 0}

    max_users = plan.get("max_users", -1)

    # Count current org members
    db = get_admin_client()
    members = db.table("noctus_users").select("id", count="exact").eq("org_id", org_id).execute()
    current_count = members.count if members.count is not None else len(members.data or [])

    # Unlimited
    if max_users == -1:
        return {"allowed": True, "current": current_count, "limit": -1, "remaining": None}

    remaining = max_users - current_count
    return {
        "allowed": remaining > 0,
        "current": current_count,
        "limit": max_users,
        "remaining": max(remaining, 0),
    }


async def check_product_limit(org_id: str) -> dict:
    """
    Check if the organization can add more products based on the plan's max_products.

    Returns:
        {
            "allowed": bool,
            "current": int,
            "limit": int,         # -1 means unlimited
            "remaining": int | None
        }
    """
    # Test orgs always pass
    if await _is_test_org(org_id):
        return {"allowed": True, "current": 0, "limit": -1, "remaining": None}

    plan = await _get_org_plan(org_id)
    if not plan:
        return {"allowed": False, "current": 0, "limit": 0, "remaining": 0}

    max_products = plan.get("max_products", -1)

    # Count current active licenses (active products)
    db = get_admin_client()
    licenses = db.table("licenses").select("id", count="exact").eq(
        "org_id", org_id
    ).eq("status", "active").execute()
    current_count = licenses.count if licenses.count is not None else len(licenses.data or [])

    # Unlimited
    if max_products == -1:
        return {"allowed": True, "current": current_count, "limit": -1, "remaining": None}

    remaining = max_products - current_count
    return {
        "allowed": remaining > 0,
        "current": current_count,
        "limit": max_products,
        "remaining": max(remaining, 0),
    }


async def check_feature(org_id: str, feature_key: str) -> bool:
    """
    Check if an organization's plan includes a specific feature.

    Features are stored in the plan's `features` jsonb column, e.g.:
        {"sso": true, "webhooks": true, "audit_logs": false}

    Returns True if the feature is present and truthy, False otherwise.
    Test orgs always return True.
    """
    if await _is_test_org(org_id):
        return True

    plan = await _get_org_plan(org_id)
    if not plan:
        return False

    features = plan.get("features", {})
    return bool(features.get(feature_key, False))


async def get_org_entitlements(org_id: str) -> dict:
    """
    Return all entitlements for an organization: limits, features, plan info.

    Returns:
        {
            "plan": { ... } | None,
            "is_test": bool,
            "users": { "allowed": bool, "current": int, "limit": int, "remaining": int|None },
            "products": { "allowed": bool, "current": int, "limit": int, "remaining": int|None },
            "features": { "feature_key": bool, ... }
        }
    """
    is_test = await _is_test_org(org_id)
    plan = await _get_org_plan(org_id)

    users = await check_user_limit(org_id)
    products = await check_product_limit(org_id)

    features = {}
    if plan:
        raw_features = plan.get("features", {})
        features = {k: bool(v) for k, v in raw_features.items()}
    elif is_test:
        features = {"all": True}

    plan_summary = None
    if plan:
        plan_summary = {
            "id": plan.get("id"),
            "name": plan.get("name"),
            "slug": plan.get("slug"),
        }

    return {
        "plan": plan_summary,
        "is_test": is_test,
        "users": users,
        "products": products,
        "features": features,
    }
