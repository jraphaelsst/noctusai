"""Request/response schemas for `app.routers.team`.

`TeamMemberRoleUpdate` was renamed from `RoleUpdate` by W1 of the
core-schemas-extraction (2026-05-11) to disambiguate from
`app.schemas.roles.RoleUpdate` (RBAC role definitions vs team member role
assignment — same name, different concern).
"""
from __future__ import annotations

from typing import Optional

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
