"""Post schemas — covers the post lifecycle from draft to ready."""
from __future__ import annotations

from typing import Literal, Optional

from noctusai_lib.api import StrictHttpModel

PostFormat = Literal["carousel", "single", "video"]
PostStatus = Literal["draft", "ready", "published"]


class PostCreate(StrictHttpModel):
    brand_kit_id: str
    title: str
    idea: str
    format: PostFormat = "carousel"
    variant: str = "premium"
    slide_count: int = 5
    cta: Optional[str] = None
    audience: Optional[str] = None
    key_message: Optional[str] = None


class PostUpdate(StrictHttpModel):
    title: Optional[str] = None
    idea: Optional[str] = None
    format: Optional[PostFormat] = None
    variant: Optional[str] = None
    slide_count: Optional[int] = None
    cta: Optional[str] = None
    audience: Optional[str] = None
    key_message: Optional[str] = None
    status: Optional[PostStatus] = None
