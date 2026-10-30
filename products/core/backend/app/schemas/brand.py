"""Request schemas for `app.routers.brand` (CONTRACT org-brand-identity §3)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.services.brand.extraction import MAX_BRAND_BOOK_CHARS


class BrandVoiceBody(StrictHttpModel):
    tone: str = Field(default="", max_length=2000)
    vocabulary: list[str] = Field(default_factory=list, max_length=100)
    do: list[str] = Field(default_factory=list, max_length=50)
    dont: list[str] = Field(default_factory=list, max_length=50)


class BrandIdentityPatch(StrictHttpModel):
    """Partial update of a DRAFT. ``tokens`` is merged field-wise then strictly
    re-validated server-side (the regexes in ``services.brand.tokens``)."""

    tokens: Optional[dict[str, Any]] = None
    brand_book: Optional[str] = Field(default=None, max_length=MAX_BRAND_BOOK_CHARS)
    voice: Optional[BrandVoiceBody] = None
