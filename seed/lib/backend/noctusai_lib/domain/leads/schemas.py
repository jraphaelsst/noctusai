"""Request bodies of the leads API."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class _Base(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, v):  # a cleared form input arrives as "" -- that is "no value", not an empty string
        return None if isinstance(v, str) and not v.strip() else v


class LeadBody(_Base):
    name: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = Field(None, max_length=40)
    email: Optional[str] = Field(None, max_length=254)
    origin: Optional[str] = Field(None, max_length=60)
    stage: Optional[str] = Field(None, max_length=60)
    notes: Optional[str] = Field(None, max_length=5000)
    tags: list[str] = Field(default_factory=list, max_length=30)
    first_contact_at: Optional[datetime] = None


class LeadPatch(_Base):
    name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=40)
    email: Optional[str] = Field(None, max_length=254)
    origin: Optional[str] = Field(None, max_length=60)
    stage: Optional[str] = Field(None, max_length=60)
    notes: Optional[str] = Field(None, max_length=5000)
    tags: Optional[list[str]] = Field(None, max_length=30)
    first_contact_at: Optional[datetime] = None


class LeadMove(BaseModel):
    stage: str = Field(min_length=1, max_length=60)
    #: destination index inside the stage's column (0 = top), as the kanban `onMove` reports it
    position: int = Field(0, ge=0, le=100000)


__all__ = ["LeadBody", "LeadMove", "LeadPatch"]
