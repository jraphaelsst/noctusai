"""Organ auth -- ONE role resolution for every organ mount (finance, items, parties, inventory, ...).

`auth_dependency` yields `(user, token, org_id)` where `org_id` is the SELECTED (effective) org. The
admin decision MUST come from the same resolution that produced that `org_id`: the HOME-org role
(`is_org_admin(core, uid)`) would make a home-org owner who is a plain member of org B an admin in B.

`make_organ_auth` wraps the host's `auth_dependency` so the role is resolved ONCE per request with
`resolve_org_membership(core, uid, token=..., acting_header=...)`, requires `membership.org_id == org_id`
and `org_role in ADMIN_ORG_ROLES`, and fails closed on any mismatch. The wrapped value is an
:class:`OrganAuth` (a `(user, token, org_id)` tuple with `.is_admin`), so existing unpackers keep working.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request, Response

__all__ = ["OrganAuth", "OrganAuthDeps", "make_organ_auth"]

logger = logging.getLogger(__name__)


class OrganAuth(tuple):
    """`(user, token, org_id)` + `.is_admin` (trusted role in the SELECTED org)."""

    is_admin: bool

    def __new__(cls, base: Any, is_admin: bool) -> "OrganAuth":
        self = super().__new__(cls, tuple(base))
        self.is_admin = bool(is_admin)
        return self


@dataclass(frozen=True)
class OrganAuthDeps:
    auth: Callable[..., Any]   # wrapped auth dependency -> OrganAuth
    admin: Callable[..., Any]  # 403 unless admin in the selected org (+ admin-MFA policy)


def make_organ_auth(
    auth_dependency: Callable[..., Any],
    get_core_client: Callable[[], Any],
    *,
    context: str = "Esta ação",
) -> OrganAuthDeps:
    from noctusai_lib.api.auth._blocking import run_blocking
    from noctusai_lib.api.auth.effective_org import acting_header_of
    from noctusai_lib.api.auth.session.scopes import (
        ADMIN_ORG_ROLES,
        assure_legacy_admin,
        resolve_org_membership,
    )

    def _is_admin(request: Request, user: Any, token: Any, org_id: Any) -> bool:
        uid = getattr(user, "id", None)
        membership = resolve_org_membership(
            get_core_client(), uid, token=token, acting_header=acting_header_of(request)
        )
        return (
            membership is not None
            and str(membership.get("org_id")) == str(org_id)
            and membership.get("org_role") in ADMIN_ORG_ROLES
        )

    async def auth(request: Request, base: Any = Depends(auth_dependency)) -> OrganAuth:
        user, token, org_id = base
        # Sync PostgREST round trips: off the event loop (else concurrent requests serialize).
        return OrganAuth(base, await run_blocking(_is_admin, request, user, token, org_id))

    async def admin(request: Request, response: Response, a: OrganAuth = Depends(auth)) -> OrganAuth:
        if not a.is_admin:
            raise HTTPException(status_code=403, detail=f"{context} restrito a administradores.")
        user, token, org_id = a
        await assure_legacy_admin(request, response, user, token, org_id)
        return a

    return OrganAuthDeps(auth=auth, admin=admin)
