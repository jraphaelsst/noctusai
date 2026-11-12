"""`UserDirectory` -- who belongs to the org (the people a team can hold): Protocol + Fake + Real.

Real reads the ACTIVE `public.org_memberships` of the org (`org_memberships.list_member_profiles`), never `noctus_users.org_id`
(that is each person's LAST-ACTIVE org: a member whose last pick is elsewhere would vanish from the team picker). A person who
left the org stops being eligible even while a stale `asg_members` row names them.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Protocol, Sequence, runtime_checkable

from noctusai_lib.domain import org_memberships


@runtime_checkable
class UserDirectory(Protocol):
    def members(self, org_id: str) -> list[dict]:
        """`[{id, name, role}]` of the org's active members (name falls back to None, never to a made-up label)."""
        ...


class FakeUserDirectory:
    def __init__(self, members: Optional[Mapping[str, Sequence[Mapping[str, Any]]]] = None) -> None:
        self._members = {k: [dict(m) for m in v] for k, v in (members or {}).items()}

    def add(self, org_id: str, user_id: str, name: Optional[str] = None, role: str = "member") -> None:
        self._members.setdefault(str(org_id), []).append({"id": str(user_id), "name": name, "role": role})

    def remove(self, org_id: str, user_id: str) -> None:
        self._members[str(org_id)] = [m for m in self._members.get(str(org_id), []) if m["id"] != str(user_id)]

    def members(self, org_id: str) -> list[dict]:
        return [dict(m) for m in self._members.get(str(org_id), [])]


class CoreUserDirectory:
    """The Real directory over the CORE client (`get_core_client()`)."""

    def __init__(self, get_core_client: Callable[[], Any]) -> None:
        self._get_core = get_core_client

    def members(self, org_id: str) -> list[dict]:
        rows = org_memberships.list_member_profiles(self._get_core(), str(org_id), "id, nome")
        return [{"id": str(r["id"]), "name": r.get("nome"), "role": r.get("org_role")} for r in rows]


__all__ = ["CoreUserDirectory", "FakeUserDirectory", "UserDirectory"]
