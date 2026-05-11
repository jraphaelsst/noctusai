"""
Pydantic models for ``imobi_scheduling.users`` — agency staff + media crew.

The `users` row is the bot's authorization domain entity (distinct from
`auth.users` which holds Supabase auth state). LID-aware via
``linked_identity`` per sibling's `security-hardening` parity.

Inputs end in ``Create`` / ``Update``; outputs end in ``Out``. Wire shape
intentionally diverges from the DB row when needed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field
from noctusai_lib.api import StrictHttpModel

UserRole = Literal["real_estate_agent", "media_crew", "admin"]


class UserCreate(StrictHttpModel):
    """Request body for ``POST /api/users`` (admin-only)."""

    name: str = Field(..., min_length=1, max_length=120)
    role: UserRole
    phone_number: str = Field(..., min_length=8, max_length=32)
    email: str | None = Field(None, max_length=255)
    linked_identity: str | None = Field(None, max_length=128)
    active: bool = True


class UserUpdate(StrictHttpModel):
    """Patch body for ``PATCH /api/users/{id}`` (admin-only)."""

    name: str | None = Field(None, min_length=1, max_length=120)
    role: UserRole | None = None
    email: str | None = Field(None, max_length=255)
    linked_identity: str | None = Field(None, max_length=128)
    active: bool | None = None


class UserOut(StrictHttpModel):
    """Response body for user list / detail."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    auth_user_id: UUID | None
    name: str
    role: UserRole
    phone_number: str
    email: str | None
    linked_identity: str | None
    active: bool
    created_at: datetime
    updated_at: datetime
