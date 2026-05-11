"""Request/response schemas for `app.routers.organizations`."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class OrgUpdate(StrictHttpModel):
    nome: Optional[str] = None
    plano: Optional[str] = None
    category: Optional[str] = Field(default=None, pattern="^(normal|test)$")
