"""The org's approver list (`pur_approvers`) -- the ONLY source of approval authority besides org admin.

Org-scoped by construction (every read / write names `org_id`); there is deliberately no global permission path: a
grant for org A must never approve in org B. Grants / revocations go through the `pur_set_approver` RPC so the change and
its append-only audit row (`pur_settings_log`) commit together.
"""
from __future__ import annotations

from typing import Any

from ._common import Scope, first
from .orders import _rpc


def is_approver(s: Scope, user_id: Any) -> bool:
    """True iff `user_id` is in THIS org's approver list."""
    if not user_id:
        return False
    row = first(s.tbl("approvers").select("user_id").eq("org_id", s.org_id).eq("user_id", str(user_id)).limit(1).execute())
    return row is not None


def list_approvers(s: Scope) -> list[dict]:
    return s.rows("approvers", order_col="user_id")


def set_approver(s: Scope, user_id: Any, *, granted: bool, actor_id: Any) -> list[dict]:
    """Add (`granted=True`) or remove an approver of this org; idempotent. Returns the updated list."""
    _rpc(s, "set_approver", {"p_org": s.org_id, "p_actor": str(actor_id) if actor_id else None, "p_user": str(user_id), "p_grant": granted})
    return list_approvers(s)


__all__ = ["is_approver", "list_approvers", "set_approver"]
