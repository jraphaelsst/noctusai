"""Request/response schemas for `app.routers.settings`."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class PlatformSettingBody(StrictHttpModel):
    value: str = Field(..., min_length=1)
    description: Optional[str] = None
    is_secret: bool = False


class OrgSettingBody(StrictHttpModel):
    value: str = Field(..., min_length=1)
    is_secret: bool = False
