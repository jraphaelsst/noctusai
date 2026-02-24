"""
NoctusAI Core — Audit Log Service.

Records user actions for security auditing and compliance.

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
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- CREATE INDEX idx_audit_logs_org ON audit_logs(org_id, created_at DESC);
-- ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
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
) -> dict:
    """
    Create an audit log entry.

    Args:
        user_id: The acting user's UUID (None for system actions).
        org_id: The organization context UUID.
        action: Action performed (e.g. 'create', 'update', 'delete', 'login', 'revoke').
        resource_type: Type of resource (e.g. 'subscription', 'license', 'api_key', 'user').
        resource_id: Optional ID of the affected resource.
        details: Optional JSON details about the action.
        request: Optional FastAPI Request object (to extract IP and user-agent).

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
