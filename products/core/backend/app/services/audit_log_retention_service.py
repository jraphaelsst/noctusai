"""Audit Log Retention Service — physical purge of expired audit_logs rows.

Owner directive (2026-09-23) + migration 053. Sibling of
`webhook_retention_service.py`, with one structural difference: `audit_logs`
is append-only (migration 053's `guard_audit_logs_append_only` trigger)
whereas `webhook_deliveries` carries no such guard. A plain
``db.table("audit_logs").delete()`` is therefore ALWAYS refused here — the
only door is the `public.purge_expired_audit_logs()` SECURITY DEFINER RPC,
which is the one thing allowed to set the transaction-local
`core.audit_log_purge` flag the trigger checks.

**Design:**

1. `run_retention_sweep(db)` calls `purge_expired_audit_logs()` via RPC and
   returns `{"purged": N}`. Meant to be called from the scheduler
   (`app/scheduler.py`'s `core_audit_log_retention_sweep` job).
2. Idempotent: safe to re-run. Caller provides service-role client (the RPC
   is `GRANT EXECUTE ... TO service_role` only — migration 053).

**LGPD**: audit_logs stores ids + structural request metadata (never raw
PII payloads — migration 053's header). Without this sweep, the trail grows
unbounded despite `retention_until` marking rows eligible for removal.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def run_retention_sweep(db: Any, batch_limit: int = 5000) -> Dict[str, int]:
    """Run a single audit_logs purge sweep via the `purge_expired_audit_logs`
    RPC — returns `{"purged": N}`. Idempotent: safe to re-run.
    """
    result = db.rpc("purge_expired_audit_logs", {"p_batch_limit": batch_limit}).execute()
    purged = result.data if isinstance(result.data, int) else 0
    logger.info("Audit log retention sweep: purged=%d", purged)
    return {"purged": purged}
