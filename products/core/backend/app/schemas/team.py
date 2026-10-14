"""Request/response schemas for `app.routers.team`.

`TeamMemberRoleUpdate` was renamed from `RoleUpdate` by W1 of the
core-schemas-extraction (2026-05-11) to disambiguate from
`app.schemas.roles.RoleUpdate` (RBAC role definitions vs team member role
assignment — same name, different concern).
"""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class InviteCreate(StrictHttpModel):
    email: str = Field(..., max_length=255)
    role: str = Field(default="member", max_length=50)


class TeamMemberRoleUpdate(StrictHttpModel):
    role: str = Field(..., max_length=50)


class AcceptInviteRequest(StrictHttpModel):
    token: str = Field(..., max_length=128)
    nome: Optional[str] = Field(default=None, max_length=200)


class MemberMoveRequest(StrictHttpModel):
    """D3 (owner, 2026-10-14): move ``user_id`` from ``source_org_id`` to ``target_org_id``.
    ``mode``: ``transfer`` ends the source membership, ``add`` keeps it. ``role`` is the role in
    the target, never above the actor's own role there."""

    user_id: UUID
    source_org_id: UUID
    target_org_id: UUID
    role: str = Field(..., max_length=50)
    mode: Literal["transfer", "add"]


class ProductAccessUpdate(StrictHttpModel):
    """D5: ``blocked=true`` blocks the member from the product inside the org; ``false`` unblocks."""

    blocked: bool
