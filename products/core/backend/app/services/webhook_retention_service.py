"""Webhook Retention Service — physical purge of expired webhook deliveries.

compliance-audit-reconciliation Phase 6 (finding 8, 2026-04-22).

**Design:**

1. `find_expired_deliveries(db, limit=1000)` — list delivery rows where
   `retention_until < now()`.
2. `purge_expired_deliveries(db, limit=1000)` — DELETE the expired rows.
   Batch size capped so a runaway sweep doesn't stall the DB.
3. `run_retention_sweep(db)` — batch runner. Meant to be called from a
   scheduler (follow-up: `core-scheduler-for-retention`). Exposed via
   `POST /api/admin/purge-webhook-deliveries` (platform_admin only) until
   the scheduler lands.

**LGPD Art. 16**: webhook payloads may contain PII (team invite emails,
etc.). Without this service, `webhook_deliveries` grew unbounded.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from noctusai_lib.primitives.timeutil import now_utc_iso

logger = logging.getLogger(__name__)


def find_expired_deliveries(db: Any, limit: int = 1000) -> list[Dict]:
    """Return delivery rows whose retention window has closed."""
    result = (
        db.table("webhook_deliveries")
        .select("id, retention_until")
        .lt("retention_until", now_utc_iso())
        .limit(limit)
        .execute()
    )
    return result.data or []


def purge_expired_deliveries(db: Any, limit: int = 1000) -> int:
    """Delete every expired delivery row. Returns purged-row count."""
    expired = find_expired_deliveries(db, limit=limit)
    if not expired:
        return 0
    ids = [row["id"] for row in expired]
    db.table("webhook_deliveries").delete().in_("id", ids).execute()
    return len(ids)


def run_retention_sweep(db: Any) -> Dict[str, int]:
    """Run a single sweep — returns `{"purged": N}`.

    Idempotent: safe to re-run. Caller provides service-role client.
    """
    purged = purge_expired_deliveries(db)
    logger.info("Webhook retention sweep: purged=%d", purged)
    return {"purged": purged}
