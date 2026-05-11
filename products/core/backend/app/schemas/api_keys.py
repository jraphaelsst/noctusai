"""Request/response schemas for `app.routers.api_keys`."""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class ApiKeyCreate(StrictHttpModel):
    name: str = Field(..., max_length=100)
    scopes: List[str] = Field(default=["read"])
    expires_at: Optional[str] = None


class ApiKeyUpdate(StrictHttpModel):
    name: Optional[str] = Field(default=None, max_length=100)
    scopes: Optional[List[str]] = None
    expires_at: Optional[str] = None
