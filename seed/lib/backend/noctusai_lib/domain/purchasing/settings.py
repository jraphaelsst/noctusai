"""Org settings: the approval threshold (`pur_settings`, ONE row per org, created on the first change).

`approval_threshold_cents` NULL / absent = no threshold. Above it an order needs an approver of the org (see
`orders.check_can_approve`). Until a row exists `GET` answers the default with `persisted=False`.

A change goes through the `pur_set_threshold` RPC: the row is locked, the change and its append-only audit row
(`pur_settings_log`) commit together, and it starts the approval cooldown (`APPROVAL_COOLDOWN_MINUTES`) in which orders
above the LOWEST threshold in force cannot be approved -- raising the limit and approving the order it just freed in the
same breath is exactly what the cooldown prevents. WHO may change it (an approver of the org) is the router's gate.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ._common import Scope, first, rpc
from .sql import APPROVAL_COOLDOWN_MINUTES


def _parse(ts) -> Optional[datetime]:
    if not ts:
        return None
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))


def get_settings(s: Scope) -> dict:
    row = first(s.tbl("settings").select("*").eq("org_id", s.org_id).limit(1).execute())
    if row is None:
        return {"approval_threshold_cents": None, "persisted": False, "threshold_changed_at": None, "cooldown_until": None}
    changed = _parse(row.get("threshold_changed_at"))
    return {
        "approval_threshold_cents": row.get("approval_threshold_cents"),
        "persisted": True,
        "threshold_changed_at": row.get("threshold_changed_at"),
        "cooldown_until": (changed + timedelta(minutes=APPROVAL_COOLDOWN_MINUTES)).isoformat() if changed else None,
    }


def threshold_cents(s: Scope) -> Optional[int]:
    value = get_settings(s)["approval_threshold_cents"]
    return None if value is None else int(value)


def set_threshold(s: Scope, cents: Optional[int], *, user_id: Optional[str] = None) -> dict:
    """Set the org's threshold (`None` clears it) atomically with its audit row; a no-change call is a replay."""
    rpc(s, "set_threshold", {"p_org": s.org_id, "p_user": user_id, "p_cents": cents})
    return get_settings(s)


__all__ = ["get_settings", "set_threshold", "threshold_cents"]
