"""Request/response schemas for `app.routers.users`."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class UserUpdate(StrictHttpModel):
    nome: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = Field(default=None, pattern="^(admin|user)$")
    org_role: Optional[str] = Field(default=None, pattern="^(owner|admin|member)$")
