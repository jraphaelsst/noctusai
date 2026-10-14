"""Who belongs to an org = the ACTIVE ``public.org_memberships`` rows of it (multi-org).

``noctus_users.org_id`` is only each person's LAST-ACTIVE org (it follows the org picker, core
081). Reading it as "the members of org X" makes a member whose last pick is elsewhere vanish
from a team page, from a seat count and from a notification fan-out. Every "members of X"
question -- core's team page and the seed product team router alike -- reads here.

The writes that span several rows (remove / change role / move / accept a CORE invitation) are
single SECURITY DEFINER functions in core (``team_membership_ops`` / ``member_access_rules``),
called by core. :func:`join_org` is the one single-row write: a person JOINS an org (a product
invitation accepted, a self sign-up). It never touches the person's profile org -- they reach
the new org through the org picker -- and never lifts a suspension.

KB § PATTERNS/backend/tenancy-license-gate.md § Members
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Iterator, Optional

from noctusai_lib.integrations.persistence.paging import iter_paged_rows

logger = logging.getLogger(__name__)

#: ``.in_()`` values ride in the URL query string: batch them.
_IN_BATCH = 150

#: Membership statuses a join may (re)activate. ``suspended`` is an org decision a join must not
#: lift; ``active`` is already a member.
_REJOINABLE = ("removed", "invited")


def _batched(values: list, size: int = _IN_BATCH) -> Iterator[list]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def get_membership(db: Any, org_id: str, user_id: str) -> Optional[dict]:
    """The (user, org) membership row, any status, or ``None``."""
    resp = (
        db.table("org_memberships")
        .select("user_id, org_id, org_role, status")
        .eq("org_id", str(org_id))
        .eq("user_id", str(user_id))
        .maybe_single()
        .execute()
    )
    return resp.data if resp is not None else None


def list_active_memberships(
    db: Any,
    org_id: str,
    *,
    only_roles: Optional[Iterable[str]] = None,
    exclude_roles: Optional[Iterable[str]] = None,
) -> list[dict]:
    """Every ACTIVE membership of ``org_id`` (paged -- never the silent 1 000-row cap).

    ``only_roles`` / ``exclude_roles`` filter IN the query (a product roster lists its staff
    only; an org shared with end customers may hold thousands of customer memberships)."""
    only = sorted(only_roles) if only_roles is not None else None
    excluded = sorted(exclude_roles) if exclude_roles else None

    def _page(start: int, end: int) -> list:
        query = (
            db.table("org_memberships")
            .select("user_id, org_role, created_at")
            .eq("org_id", str(org_id))
            .eq("status", "active")
        )
        if only is not None:
            # postgrest-unbounded-ok: a role vocabulary (a handful of slugs), never data-sized.
            query = query.in_("org_role", only)
        if excluded:
            query = query.not_.in_("org_role", excluded)
        return query.order("user_id").range(start, end).execute().data

    return list(iter_paged_rows(_page, id_key="user_id", label=f"active memberships of org {org_id}"))


def list_user_active_memberships(db: Any, user_id: str) -> list[dict]:
    """Every ACTIVE membership OF a user, most recently updated first (an ordinary user belongs
    to a handful of orgs; paged anyway so the cap can never hide one)."""
    rows = list(iter_paged_rows(
        lambda start, end: (
            db.table("org_memberships")
            .select("org_id, org_role, updated_at")
            .eq("user_id", str(user_id))
            .eq("status", "active")
            .order("org_id")
            .range(start, end)
            .execute()
            .data
        ),
        id_key="org_id",
        label=f"active memberships of user {user_id}",
    ))
    rows.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
    return rows


def active_member_user_ids(db: Any, org_id: str) -> list[str]:
    return [str(r["user_id"]) for r in list_active_memberships(db, org_id)]


def count_active_members(db: Any, org_id: str) -> int:
    """Seats in use: ACTIVE memberships (``invited`` is not a seat until accepted)."""
    resp = (
        db.table("org_memberships")
        .select("user_id", count="exact")
        .eq("org_id", str(org_id))
        .eq("status", "active")
        .execute()
    )
    return resp.count if resp.count is not None else len(resp.data or [])


def profiles_by_id(db: Any, user_ids: list[str], columns: str) -> dict[str, dict]:
    """``noctus_users`` rows for ``user_ids`` keyed by id (``columns`` must include ``id``)."""
    out: dict[str, dict] = {}
    for chunk in _batched(list(user_ids)):
        rows = db.table("noctus_users").select(columns).in_("id", chunk).execute().data or []
        for row in rows:
            out[str(row["id"])] = row
    return out


def list_member_profiles(
    db: Any,
    org_id: str,
    columns: str,
    *,
    only_roles: Optional[Iterable[str]] = None,
    exclude_roles: Optional[Iterable[str]] = None,
) -> list[dict]:
    """The ACTIVE members of ``org_id`` as profile rows, each carrying the role IN THIS ORG.

    ``org_id`` / ``org_role`` of each row are the membership's -- never the profile's
    last-active org. An active membership without a profile cannot be named or acted on: it is
    logged at error and left out (never silently). Ordered by ``created_at``."""
    memberships = list_active_memberships(db, org_id, only_roles=only_roles, exclude_roles=exclude_roles)
    profiles = profiles_by_id(db, [str(m["user_id"]) for m in memberships], columns)
    rows = []
    for m in memberships:
        p = profiles.get(str(m["user_id"]))
        if p is None:
            logger.error("team: active membership without a noctus_users profile org=%s user=%s",
                         org_id, m["user_id"])
            continue
        rows.append({
            **p,
            "org_id": str(org_id),
            "org_role": m.get("org_role"),
            "created_at": p.get("created_at") or m.get("created_at"),
        })
    rows.sort(key=lambda r: str(r.get("created_at") or ""))
    return rows


class MembershipSuspended(Exception):
    """The person's membership of the org is ``suspended``: an org decision a join must not lift."""


def join_org(
    db: Any,
    user_id: str,
    org_id: str,
    org_role: str,
    *,
    invited_by: Optional[str] = None,
) -> dict:
    """Make a person WITH a profile an ACTIVE member of ``org_id``. Idempotent.

    - already ACTIVE -> the row untouched (``joined: False``; the caller compares roles);
    - ``suspended`` -> :class:`MembershipSuspended`;
    - ``removed`` / ``invited`` -> re-activated with ``org_role``;
    - none -> inserted ACTIVE.

    The profile (``noctus_users.org_id``) is never moved: the new org is reached through the
    org picker. Returns ``{user_id, org_id, org_role, status, joined}``.
    """
    existing = get_membership(db, org_id, user_id)
    if existing is not None:
        status = existing.get("status")
        if status == "active":
            return {**existing, "joined": False}
        if status == "suspended":
            raise MembershipSuspended(f"membership of user {user_id} in org {org_id} is suspended")
        payload: dict = {"org_role": org_role, "status": "active", "ended_at": None}
        if invited_by:
            payload["invited_by"] = str(invited_by)
        (
            db.table("org_memberships").update(payload)
            .eq("org_id", str(org_id)).eq("user_id", str(user_id))
            .in_("status", list(_REJOINABLE))
            .execute()
        )
        logger.info("join_org: re-activated user_id=%s in org_id=%s (%s)", user_id, org_id, org_role)
    else:
        row: dict = {"user_id": str(user_id), "org_id": str(org_id), "org_role": org_role, "status": "active"}
        if invited_by:
            row["invited_by"] = str(invited_by)
        db.table("org_memberships").insert(row).execute()
        logger.info("join_org: user_id=%s joined org_id=%s (%s)", user_id, org_id, org_role)
    return {"user_id": str(user_id), "org_id": str(org_id), "org_role": org_role,
            "status": "active", "joined": True}


__all__ = [
    "MembershipSuspended",
    "active_member_user_ids",
    "count_active_members",
    "get_membership",
    "join_org",
    "list_active_memberships",
    "list_member_profiles",
    "list_user_active_memberships",
    "profiles_by_id",
]
