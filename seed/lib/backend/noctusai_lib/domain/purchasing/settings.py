"""Org settings: the approval threshold (`pur_settings`, ONE row per org, created on the first PUT).

`approval_threshold_cents` NULL / absent = no threshold. Above it an order needs a holder of `purchasing.approve`
(see `orders.check_can_approve`). Until a row exists `GET` answers the default with `persisted=False`.
"""
from __future__ import annotations

from typing import Optional

from ._common import Scope, first, now_iso


def get_settings(s: Scope) -> dict:
    row = first(s.tbl("settings").select("*").eq("org_id", s.org_id).limit(1).execute())
    if row is None:
        return {"approval_threshold_cents": None, "persisted": False}
    return {"approval_threshold_cents": row.get("approval_threshold_cents"), "persisted": True}


def threshold_cents(s: Scope) -> Optional[int]:
    value = get_settings(s)["approval_threshold_cents"]
    return None if value is None else int(value)


def set_threshold(s: Scope, cents: Optional[int], *, user_id: Optional[str] = None) -> dict:
    """Upsert the org's threshold (`None` clears it). The unique `org_id` PK makes a lost race a retry, not a duplicate."""
    patch = {"approval_threshold_cents": cents, "updated_by": user_id, "updated_at": now_iso()}
    if first(s.tbl("settings").select("org_id").eq("org_id", s.org_id).limit(1).execute()) is None:
        s.tbl("settings").insert({"org_id": s.org_id, **patch}).execute()
    else:
        s.tbl("settings").update(patch).eq("org_id", s.org_id).execute()
    return get_settings(s)


__all__ = ["get_settings", "set_threshold", "threshold_cents"]
