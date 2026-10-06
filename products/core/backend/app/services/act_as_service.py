"""Act-as-org sessions (round 2) — the platform owner enters a product AS a customer org.

``public.act_as_sessions`` is service-role only. One LIVE row (``ended_at IS
NULL``) per superadmin; it ends on exit ("Sair"), when replaced by a new
act-as, or on core logout. No expiry, no 2FA, reason optional.

The effective-org resolver (``noctusai_lib.api.auth.effective_org``) is the
ONLY reader that turns a live row into "this request is for org X".

KB § PATTERNS/backend/tenancy-license-and-act-as.md
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.database import get_admin_client

logger = logging.getLogger(__name__)

ENDED_BY_VALUES = ("exit", "replaced", "logout")


def end_live_session(superadmin_id: str, ended_by: str, db=None) -> Optional[dict]:
    """End the superadmin's live session, if any. Returns the ended row or ``None``."""
    if ended_by not in ENDED_BY_VALUES:
        raise ValueError(f"ended_by must be one of {ENDED_BY_VALUES}, got {ended_by!r}")
    db = db or get_admin_client()
    result = (
        db.table("act_as_sessions")
        .update({"ended_at": datetime.now(timezone.utc).isoformat(), "ended_by": ended_by})
        .eq("superadmin_id", str(superadmin_id))
        .is_("ended_at", "null")
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def start_session(
    superadmin_id: str,
    target_org_id: str,
    entry_product_slug: str,
    *,
    reason: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    db=None,
) -> dict:
    """End any live session (``replaced``) and insert the new live row."""
    db = db or get_admin_client()
    end_live_session(superadmin_id, "replaced", db=db)
    row = {
        "superadmin_id": str(superadmin_id),
        "target_org_id": str(target_org_id),
        "entry_product_slug": entry_product_slug,
    }
    if reason:
        row["reason"] = reason
    if ip:
        row["ip"] = ip
    if user_agent:
        row["user_agent"] = user_agent
    return db.table("act_as_sessions").insert(row).execute().data[0]
