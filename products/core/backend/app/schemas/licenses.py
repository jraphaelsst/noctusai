"""Request/response schemas for `app.routers.licenses`."""
from __future__ import annotations

from typing import Optional

from noctusai_lib.api import StrictHttpModel


class LicenseGrant(StrictHttpModel):
    org_id: str
    product_id: str
    fim: Optional[str] = None  # ISO 8601 datetime, null = perpetual
