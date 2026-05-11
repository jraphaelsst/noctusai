"""Request/response schemas for `app.routers.admin_cache`."""
from __future__ import annotations

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class FlushBody(StrictHttpModel):
    """Flush target — all fields required to avoid accidentally wiping everything."""
    product: str = Field(..., description="Product slug (e.g. 'erp-imobiliario')")
    provider: str = Field(..., description="Provider name (e.g. 'openai')")
    model: str = Field(..., description="Model ID (e.g. 'gpt-4o-mini')")
