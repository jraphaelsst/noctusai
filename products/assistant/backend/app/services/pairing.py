"""`paired_at` bookkeeping for the forward-only rule.

WAHA reports the session state on every `session.status` webhook. The first `WORKING` after (re)pairing stamps
`assistant.whatsapp_connections.paired_at`; a fresh QR request (`SCAN_QR_CODE`) clears it, because the line is no
longer paired. Until `paired_at` is set, `assistant.append_intake` records every message as `skipped` (`not_paired`),
so history that WAHA pushes at pairing never reaches a classifier.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

STATUS_WORKING = "WORKING"
STATUS_NEEDS_QR = "SCAN_QR_CODE"


def apply_session_status(client_factory: Callable[[], Any], record: Any, status: str) -> None:
    """Stamp / clear `paired_at` for a `session.status` event. Idempotent."""
    table = client_factory().table("whatsapp_connections")
    if status == STATUS_WORKING:
        table.update({"paired_at": datetime.now(timezone.utc).isoformat()}).eq("id", str(record.id)).eq(
            "org_id", str(record.org_id)
        ).is_("paired_at", "null").execute()
    elif status == STATUS_NEEDS_QR:
        table.update({"paired_at": None}).eq("id", str(record.id)).eq("org_id", str(record.org_id)).execute()
    else:
        return
    logger.info("pairing state connection=%s status=%s", record.id, status)
