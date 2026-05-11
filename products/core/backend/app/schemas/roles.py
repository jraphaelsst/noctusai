"""Request/response schemas for `app.routers.roles`."""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class RoleCreate(StrictHttpModel):
    name: str = Field(..., max_length=100)
    slug: str = Field(..., max_length=50)
    permissions: List[str] = Field(default_factory=list)


class RoleUpdate(StrictHttpModel):
    name: Optional[str] = Field(default=None, max_length=100)
    permissions: Optional[List[str]] = None
