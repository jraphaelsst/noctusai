"""Request/response schemas for `app.routers.users`."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

# 🔴 PARITY CONTRACT: keep identical to `ORG_ROLES` in
# `seed/lib/frontend/src/roles.ts` — the canonical 7-role org hierarchy every
# product's UI renders from. The prior `^(owner|admin|member)$` accepted only
# 3 of the 7, so the admin panel's own role dropdown (which renders
# `ASSIGNABLE_ROLES`) 422'd on manager / viewer / dev / test.
ORG_ROLE_PATTERN = "^(owner|admin|manager|member|viewer|dev|test)$"

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
