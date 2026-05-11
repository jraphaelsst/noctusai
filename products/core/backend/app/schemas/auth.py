"""Request/response schemas for `app.routers.auth`."""
from __future__ import annotations

from typing import Optional

from noctusai_lib.api import StrictHttpModel


class SignupRequest(StrictHttpModel):
    nome: str
    email: str
    password: str
    empresa: str  # Organization name


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
