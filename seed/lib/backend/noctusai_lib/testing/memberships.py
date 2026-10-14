"""Seed a mock core client with profiles AND the memberships core keeps for them.

In the real database core's 079 trigger mirrors every profile org (``noctus_users.org_id``) into
an ACTIVE ``public.org_memberships`` row. ``MockSupabaseClient`` has no triggers, so a test that
seeds profiles only would show every "members of org X" read (``noctusai_lib.domain.org_memberships``)
an empty org. Seed through here instead, then add any extra (non-home) memberships explicitly.
"""
from __future__ import annotations

from typing import Any, Iterable


def memberships_from_profiles(rows: Iterable[dict]) -> list[dict]:
    """The ACTIVE membership the 079 trigger creates for each profile that has an org
    (``org_role`` NULL -> ``member``, as the trigger's COALESCE)."""
    return [
        {"user_id": r["id"], "org_id": r["org_id"], "org_role": r.get("org_role") or "member",
         "status": "active", "created_at": r.get("created_at")}
        for r in rows if r.get("org_id")
    ]


def seed_profiles(core_db: Any, rows: Iterable[dict], *, extra_memberships: Iterable[dict] = ()) -> None:
    """``noctus_users`` = ``rows``; ``org_memberships`` = their home memberships + ``extra_memberships``."""
    rows = [dict(r) for r in rows]
    core_db.set_table_data("noctus_users", rows)
    core_db.set_table_data("org_memberships", [*memberships_from_profiles(rows), *map(dict, extra_memberships)])


__all__ = ["memberships_from_profiles", "seed_profiles"]
