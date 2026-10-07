"""Request/response schemas for `app.routers.users`."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.primitives.roles import ORG_ROLES

# DERIVED from the canonical `ORG_ROLES` (seed roles.py ↔ roles.ts) — a
# hand-written alternation here drifted twice (3 of 7 roles, then corretor
# missing) and the admin panel's own dropdown 422'd on the absent ones.
ORG_ROLE_PATTERN = "^(" + "|".join(ORG_ROLES) + ")$"

# Platform role: only these two exist in `noctus_users.role` — `manager` is an
# ORG role, never a platform one.
PLATFORM_ROLE_PATTERN = "^(admin|user)$"


class UserUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = Field(default=None, pattern=PLATFORM_ROLE_PATTERN)
    org_role: Optional[str] = Field(default=None, pattern=ORG_ROLE_PATTERN)
    org_id: Optional[UUID] = Field(
        default=None,
        description=(
            "Reassign the user to this organization. `noctus_users.org_id` is "
            "NOT NULL and there is no membership join table, so a user belongs "
            "to exactly one org — 'revoke' is expressed as a move to another org."
        ),
    )
