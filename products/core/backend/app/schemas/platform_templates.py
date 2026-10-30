"""Request schemas for `app.routers.platform_templates` (admin > Templates)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.services.platform_templates.service import MAX_BODY_CHARS

Kind = Literal["design_system", "agent", "message", "document", "repo_workflow"]
Format = Literal["json", "markdown", "text"]
PRODUCT_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"
KEY_PATTERN = r"^[a-z0-9][a-z0-9_.-]{0,79}$"


class TemplateCreate(StrictHttpModel):
    product: Optional[str] = Field(default=None, pattern=PRODUCT_PATTERN)  # None = platform-wide
    kind: Kind
    key: str = Field(..., pattern=KEY_PATTERN)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    format: Format
    body: str = Field(..., max_length=MAX_BODY_CHARS)


class TemplateUpdate(StrictHttpModel):
    """Partial. On a draft it edits in place; on an active/archived version it spawns a NEW draft."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    format: Optional[Format] = None
    body: Optional[str] = Field(default=None, max_length=MAX_BODY_CHARS)
