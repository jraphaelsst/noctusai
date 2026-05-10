"""
Distributors service — query layer for `adconnect.distributors` and
`adconnect.distributor_memberships`.

Owns:
  • Listing distributors (brand-admin: all in org; distributor user: own only).
  • Resolving a user's distributor_id from their memberships (used by
    products_service to apply preferential pricing).
  • Single-distributor read.

Per the brief, full CRUD on distributors is Engineer A's Phase 1 territory.
This module ships read-side only — Phase 1 will extend with create/update.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def list_distributors_for_brand(db: Any, *, org_id: str) -> list[dict[str, Any]]:
    """List every distributor in a brand's org. Caller must be brand admin.

    The router enforces the role check; the service is the SQL boundary.
    """
    result = (
        db.table("distributors")
        .select("*")
        .eq("org_id", org_id)
        .eq("status", "ativo")
        .execute()
    )
    return list(result.data or [])


def list_distributors_for_user(db: Any, *, user_id: str) -> list[dict[str, Any]]:
    """List distributors a given user has membership in.

    Most distributor users have one membership; a user can technically have
    multiple (multi-distributor users — see PROJECT.md §7 open question #6).
    """
    memberships = (
        db.table("distributor_memberships")
        .select("distributor_id")
        .eq("user_id", user_id)
        .execute()
    )
    dist_ids = [str(m.get("distributor_id")) for m in (memberships.data or []) if m.get("distributor_id")]
    if not dist_ids:
        return []

    rows: list[dict[str, Any]] = []
    for did in dist_ids:
        # `.in_` would be ideal but the mock builder treats it as a no-op
        # filter; explicit per-id select keeps semantics stable across
        # mock + real Supabase. The N here is bounded (typical user has 1
        # distributor; multi-distributor users are rare).
        result = (
            db.table("distributors").select("*").eq("id", did).limit(1).execute()
        )
        rows.extend(result.data or [])
    return rows


def get_distributor(db: Any, *, distributor_id: str) -> Optional[dict[str, Any]]:
    """Fetch a single distributor row by id."""
    result = (
        db.table("distributors")
        .select("*")
        .eq("id", distributor_id)
        .limit(1)
        .execute()
    )
    rows = list(result.data or [])
    return rows[0] if rows else None


def resolve_user_distributor_id(db: Any, *, user_id: str) -> Optional[str]:
    """Return the user's primary distributor_id (first membership), or None.

    Used by products_service to apply preferential pricing. Multi-distributor
    users are deferred to Phase 7 frontend (distributor switcher) — until
    then we surface the first membership.
    """
    result = (
        db.table("distributor_memberships")
        .select("distributor_id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = list(result.data or [])
    if not rows:
        return None
    did = rows[0].get("distributor_id")
    return str(did) if did else None


__all__ = [
    "list_distributors_for_brand",
    "list_distributors_for_user",
    "get_distributor",
    "resolve_user_distributor_id",
]
