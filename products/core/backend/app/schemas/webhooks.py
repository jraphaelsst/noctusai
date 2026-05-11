"""Request/response schemas for `app.routers.webhooks`."""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class WebhookCreate(StrictHttpModel):
    url: str = Field(..., max_length=500)
    events: List[str] = Field(default_factory=list)
    is_active: bool = True


class WebhookUpdate(StrictHttpModel):
    url: Optional[str] = Field(default=None, max_length=500)
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None
