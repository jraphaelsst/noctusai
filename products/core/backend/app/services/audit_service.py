"""
NoctusAI Core — Audit Log Service.

Records actions for security auditing, compliance, and the platform-wide
action-history trail (owner directive 2026-09-23; migration 053 widened the
table — see that migration's header for the full column list + LGPD note).

-- CREATE TABLE audit_logs (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   user_id uuid REFERENCES noctus_users(id),
--   org_id uuid REFERENCES organizations(id),
--   action text NOT NULL,
--   resource_type text NOT NULL,
--   resource_id text,
--   details jsonb NOT NULL DEFAULT '{}',
--   ip_address text,
--   user_agent text,
--   created_at timestamptz NOT NULL DEFAULT now(),
--   -- migration 053:
--   product_slug text, method text, route_template text,
--   path_params jsonb NOT NULL DEFAULT '{}', status_code int,
--   correlation_id text, role text,
--   actor_kind text NOT NULL DEFAULT 'user' CHECK (actor_kind IN ('user', 'agent', 'service')),
--   client_hint text, duration_ms int, before_snapshot jsonb NOT NULL DEFAULT '{}',
--   retention_until timestamptz NOT NULL DEFAULT (now() + INTERVAL '400 days')
-- );
-- CREATE INDEX idx_audit_logs_org ON audit_logs(org_id, created_at DESC);
-- ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
--
-- audit_logs is append-only (migration 053, `guard_audit_logs_append_only`
-- trigger): UPDATE is always refused; DELETE only succeeds via the
-- scheduled `purge_expired_audit_logs()` sweep. This module never attempts
-- either — insert-only by construction, matching the guard.
"""
import logging
from typing import Optional
from app.database import get_admin_client

logger = logging.getLogger(__name__)


async def log(
    user_id: Optional[str],
    org_id: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    request=None,
    *,
    product_slug: Optional[str] = None,
    method: Optional[str] = None,
    route_template: Optional[str] = None,
    path_params: Optional[dict] = None,
    status_code: Optional[int] = None,
    correlation_id: Optional[str] = None,
    role: Optional[str] = None,
    actor_kind: Optional[str] = None,
    client_hint: Optional[str] = None,
    duration_ms: Optional[int] = None,
    before_snapshot: Optional[dict] = None,
) -> dict:
    """
    Create an audit log entry.

    Args:
        user_id: The acting user's UUID (None for system actions).
        org_id: The organization context UUID.
        action: Action performed (e.g. 'create', 'update', 'delete', 'login', 'revoke').
        resource_type: Type of resource (e.g. 'subscription', 'license', 'api_key', 'user').
        resource_id: Optional ID of the affected resource.
        details: Optional JSON details about the action. IDs/enums/counts only — never PII.
        request: Optional FastAPI Request object (to extract IP and user-agent).
        product_slug: Optional slug of the product that originated the action
            (core itself, or a product calling through core's audit surface).
        method: Optional HTTP method of the originating request (e.g. 'POST').
        route_template: Optional route template (e.g. '/api/orgs/{org_id}/users'),
            not the interpolated path — keeps cardinality bounded for grouping.
        path_params: Optional dict of the route's path parameters (ids only).
        status_code: Optional HTTP status code the request resolved to.
        correlation_id: Optional id correlating this entry with other audit
            rows / logs from the same originating request.
        role: Optional acting user's role/org_role at the time of the action.
        actor_kind: Optional 'user' | 'agent' | 'service' (DB CHECK-enforced;
            defaults to 'user' at the DB layer when omitted).
        client_hint: Optional coarse platform/browser-family hint — never the
            raw User-Agent string (that is `user_agent`, extracted from `request`).
        duration_ms: Optional request duration in milliseconds.
        before_snapshot: Optional dict of the resource's state before the
            change (ids/values relevant to the diff — never a raw PII dump).

    Returns:
        The created audit log record.
    """
    db = get_admin_client()

    data = {
        "action": action,
        "resource_type": resource_type,
        "details": details or {},
    }

    if user_id:
        data["user_id"] = user_id
    if org_id:
        data["org_id"] = org_id
    if resource_id:
        data["resource_id"] = resource_id
    if product_slug:
        data["product_slug"] = product_slug
    if method:
        data["method"] = method
    if route_template:
        data["route_template"] = route_template
    if path_params:
        data["path_params"] = path_params
    if status_code is not None:
        data["status_code"] = status_code
    if correlation_id:
        data["correlation_id"] = correlation_id
    if role:
        data["role"] = role
    if actor_kind:
        data["actor_kind"] = actor_kind
    if client_hint:
        data["client_hint"] = client_hint
    if duration_ms is not None:
        data["duration_ms"] = duration_ms
    if before_snapshot:
        data["before_snapshot"] = before_snapshot

    # Extract IP address and user-agent from request if available
    if request:
        # FastAPI Request object
        ip_address = None
        if hasattr(request, "headers"):
            # Prefer X-Forwarded-For for proxied requests
            ip_address = request.headers.get("x-forwarded-for")
            if ip_address:
                ip_address = ip_address.split(",")[0].strip()
        if not ip_address and hasattr(request, "client") and request.client:
            ip_address = request.client.host

        if ip_address:
            data["ip_address"] = ip_address

        user_agent = None
        if hasattr(request, "headers"):
            user_agent = request.headers.get("user-agent")
        if user_agent:
            data["user_agent"] = user_agent[:500]  # Truncate long user-agents

    result = db.table("audit_logs").insert(data).execute()

    if not result.data:
        logger.error(f"Failed to create audit log: action={action} resource_type={resource_type}")
        return {}

    logger.debug(
        f"Audit log: user={user_id} action={action} "
        f"resource_type={resource_type} resource_id={resource_id}"
    )
    return result.data[0]
