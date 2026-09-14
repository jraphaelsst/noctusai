"""Org-role sets — contract §B.0.

    READ  = {owner, admin, member, viewer}
    WRITE = {owner, admin, member}
    ADMIN = {owner, admin}

(Security review 2026-09-14 suggested an `editor` role; noc has none, so
`member` holds that position — contract §B.0's own note.) These are the
`user_roles=` arguments every `require_scopes(...)` binding in
`app/dependencies.py` passes for a `caller_kind == "user"` caller; a
`caller_kind == "product"` caller is instead gated on the scope list
(`academia:read` / `academia:*:write` / `academia:import`).
"""
from __future__ import annotations

READ: frozenset[str] = frozenset({"owner", "admin", "member", "viewer"})
WRITE: frozenset[str] = frozenset({"owner", "admin", "member"})
ADMIN: frozenset[str] = frozenset({"owner", "admin"})

__all__ = ["ADMIN", "READ", "WRITE"]
