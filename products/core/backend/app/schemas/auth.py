"""Request/response schemas for `app.routers.auth`."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class SignupRequest(StrictHttpModel):
    nome: str
    email: str
    password: str
    empresa: str  # Organization name
    org_type: Literal["individual", "company"] = Field(
        default="individual",
        description="Org type — 'individual' or 'company'. Drives slug prefix and number_of_users.",
    )
    number_of_users: int = Field(
        default=1,
        ge=1,
        description="Number of users — required (>=1) when org_type='company'.",
    )


class LoginRequest(StrictHttpModel):
    email: str
    password: str


class ProfileUpdate(StrictHttpModel):
    nome: Optional[str] = None
    avatar_url: Optional[str] = None


class PasswordChange(StrictHttpModel):
    new_password: str


class RefreshRequest(StrictHttpModel):
    refresh_token: str
