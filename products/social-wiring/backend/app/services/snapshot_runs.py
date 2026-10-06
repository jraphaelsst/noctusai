"""``social_wiring.snapshot_runs`` claim-row guard — shared by every daily
per-account snapshot job (YouTube, Instagram).

Extracted from ``app.modules.youtube.services.snapshot_service`` when the
Instagram daily job became its second consumer (DRY, N=2). The table is
keyed ``(account_id, snapshot_date)``; every connection is its own
``integration_accounts`` row, so jobs of different providers never collide.

Semantics:
- a ``done`` row for the day → skip (unless ``force``);
- a ``running`` row younger than ``stale_running_after`` → skip (another
  worker is on it — the scheduler tick and a manual "Sincronizar" racing);
  ``None`` keeps the historical YouTube behaviour (always re-claim);
- otherwise upsert ``running`` (fresh insert, or reset of an ``error`` /
  stale ``running`` row) and proceed.

The check-then-upsert is not a single atomic statement (PostgREST has no
conditional upsert); the window is milliseconds and a duplicate run is
idempotent (every write is an upsert on a natural key), so the guard bounds
wasted provider quota rather than protecting correctness.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_SCHEMA = "social_wiring"
_TABLE = "snapshot_runs"

__all__ = ["claim_snapshot_run", "mark_snapshot_run"]


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        logger.warning("snapshot_runs: unparseable started_at %r — treating as stale", value)
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def claim_snapshot_run(
    admin: Any,
    *,
    account_id: UUID,
    snapshot_date: date,
    force: bool = False,
    stale_running_after: Optional[timedelta] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Try to claim the day's run. ``True`` = proceed, ``False`` = skip."""
    now = now or datetime.now(timezone.utc)
    resp = (
        admin.schema(_SCHEMA)
        .table(_TABLE)
        .select("status, started_at")
        .eq("account_id", str(account_id))
        .eq("snapshot_date", snapshot_date.isoformat())
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    if rows and not force:
        status = rows[0].get("status")
        if status == "done":
            return False
        if status == "running" and stale_running_after is not None:
            started = _parse_ts(rows[0].get("started_at"))
            if started is not None and now - started < stale_running_after:
                return False

    (
        admin.schema(_SCHEMA)
        .table(_TABLE)
        .upsert(
            {
                "account_id": str(account_id),
                "snapshot_date": snapshot_date.isoformat(),
                "status": "running",
                "started_at": now.isoformat(),
            },
            on_conflict="account_id,snapshot_date",
        )
        .execute()
    )
    return True


def mark_snapshot_run(
    admin: Any,
    *,
    account_id: UUID,
    snapshot_date: date,
    status: str,
    note: Optional[str] = None,
) -> None:
    """Set the run's final status (``done`` | ``error``), optionally with a
    short ``note`` (e.g. a partial-run summary)."""
    payload: dict[str, Any] = {"status": status}
    if note is not None:
        payload["note"] = note[:2000]
    (
        admin.schema(_SCHEMA)
        .table(_TABLE)
        .update(payload)
        .eq("account_id", str(account_id))
        .eq("snapshot_date", snapshot_date.isoformat())
        .execute()
    )
