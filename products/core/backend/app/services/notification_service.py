"""
NoctusAI Core — Notification Service.

Creates and dispatches in-app notifications for users.

-- CREATE TABLE notifications (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   user_id uuid NOT NULL REFERENCES noctus_users(id),
--   org_id uuid REFERENCES organizations(id),
--   type text NOT NULL CHECK (type IN ('team_invite', 'subscription_change', 'usage_alert', 'system')),
--   title text NOT NULL,
--   message text NOT NULL,
--   metadata jsonb NOT NULL DEFAULT '{}',
--   read boolean NOT NULL DEFAULT false,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
-- ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "notifications_own" ON notifications FOR ALL USING (user_id = auth.uid());
"""
import logging
from typing import Optional
from app.database import get_admin_client
from app.services import team_memberships

logger = logging.getLogger(__name__)


async def create(
    user_id: str,
    org_id: Optional[str],
    type: str,
    title: str,
    message: str,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Create a single notification for a user.

    Args:
        user_id: Target user UUID.
        org_id: Associated organization UUID (optional).
        type: One of 'team_invite', 'subscription_change', 'usage_alert', 'system'.
        title: Notification title.
        message: Notification body text.
        metadata: Optional JSON metadata.

    Returns:
        The created notification record.
    """
    db = get_admin_client()

    data = {
        "user_id": user_id,
        "type": type,
        "title": title,
        "message": message,
        "metadata": metadata or {},
        "read": False,
    }
    if org_id:
        data["org_id"] = org_id

    result = db.table("notifications").insert(data).execute()
    if not result.data:
        logger.error(f"Failed to create notification for user={user_id}")
        return {}

    logger.info(f"Notification created: type={type} user={user_id}")
    return result.data[0]


async def notify_team(
    org_id: str,
    type: str,
    title: str,
    message: str,
    metadata: Optional[dict] = None,
    exclude_user_id: Optional[str] = None,
) -> list[dict]:
    """
    Send a notification to all members of an organization.

    Args:
        org_id: Organization UUID.
        type: Notification type.
        title: Notification title.
        message: Notification body text.
        metadata: Optional JSON metadata.
        exclude_user_id: Optionally exclude a specific user (e.g. the actor).

    Returns:
        List of created notification records.
    """
    db = get_admin_client()

    # All org members = ACTIVE memberships (noctus_users.org_id is only a user's last-active org)
    member_ids = [
        uid for uid in team_memberships.active_member_user_ids(db, org_id)
        if not exclude_user_id or uid != str(exclude_user_id)
    ]

    if not member_ids:
        logger.info(f"No team members found for org={org_id}")
        return []

    # Bulk INSERT all notifications in a single query (avoids N+1)
    rows = [
        {
            "user_id": member_id,
            "org_id": org_id,
            "type": type,
            "title": title,
            "message": message,
            "metadata": metadata or {},
            "read": False,
        }
        for member_id in member_ids
    ]

    result = db.table("notifications").insert(rows).execute()
    notifications = result.data or []

    logger.info(f"Team notified: org={org_id} type={type} count={len(notifications)}")
    return notifications
