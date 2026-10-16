"""Request bodies for the reminders routes (`StrictHttpModel`, `extra="forbid"`)."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from .types import MAX_OFFSET_DAYS, MIN_OFFSET_DAYS


class SettingsBody(StrictHttpModel):
    enabled: Optional[bool] = None
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=64)


class RuleBody(StrictHttpModel):
    channel: str = "whatsapp"
    offset_days: int = Field(ge=MIN_OFFSET_DAYS, le=MAX_OFFSET_DAYS)
    template: str = Field(min_length=1, max_length=2000)
    enabled: bool = True


class RulePatch(StrictHttpModel):
    channel: Optional[str] = None
    offset_days: Optional[int] = Field(default=None, ge=MIN_OFFSET_DAYS, le=MAX_OFFSET_DAYS)
    template: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    enabled: Optional[bool] = None


class OptOutBody(StrictHttpModel):
    opt_out: bool


__all__ = ["OptOutBody", "RuleBody", "RulePatch", "SettingsBody"]
