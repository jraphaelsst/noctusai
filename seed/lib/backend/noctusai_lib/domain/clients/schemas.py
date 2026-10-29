"""Request bodies of the clients API (`StrictHttpModel`: an unknown key is a 422, never a silently dropped write)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import Field, field_validator

from noctusai_lib.api.schemas import StrictHttpModel

_HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class _Base(StrictHttpModel):
    @field_validator("*", mode="before")
    @classmethod
    def _blank_to_none(cls, v):  # a cleared form input arrives as "" -- that is "no value", not an empty string
        return None if isinstance(v, str) and not v.strip() else v


class ClientBody(_Base):
    name: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = Field(None, max_length=40)
    email: Optional[str] = Field(None, max_length=254)
    doc: Optional[str] = Field(None, max_length=20)
    birth_date: Optional[date] = None
    status: Optional[str] = Field(None, max_length=60)
    tags: list[str] = Field(default_factory=list, max_length=30)
    notes: Optional[str] = Field(None, max_length=10000)
    default_price_cents: Optional[int] = Field(None, ge=0, le=100_000_000)
    session_duration_min: Optional[int] = Field(None, ge=1, le=1440)
    started_at: Optional[date] = None


class ClientPatch(_Base):
    name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=40)
    email: Optional[str] = Field(None, max_length=254)
    doc: Optional[str] = Field(None, max_length=20)
    birth_date: Optional[date] = None
    status: Optional[str] = Field(None, max_length=60)
    tags: Optional[list[str]] = Field(None, max_length=30)
    notes: Optional[str] = Field(None, max_length=10000)
    default_price_cents: Optional[int] = Field(None, ge=0, le=100_000_000)
    session_duration_min: Optional[int] = Field(None, ge=1, le=1440)
    started_at: Optional[date] = None


class SessionBody(_Base):
    #: an instant; without an offset it is read as the org's wall-clock time
    starts_at: datetime
    duration_min: Optional[int] = Field(None, ge=1, le=1440)
    status: Optional[str] = Field(None, max_length=60)
    price_cents: Optional[int] = Field(None, ge=0, le=100_000_000)
    waive_charge: bool = False
    notes: Optional[str] = Field(None, max_length=10000)


class SessionPatch(_Base):
    starts_at: Optional[datetime] = None
    duration_min: Optional[int] = Field(None, ge=1, le=1440)
    status: Optional[str] = Field(None, max_length=60)
    price_cents: Optional[int] = Field(None, ge=0, le=100_000_000)
    waive_charge: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=10000)


class ScheduleBody(_Base):
    weekday: int = Field(ge=0, le=6)
    time: str = Field(pattern=_HHMM)
    duration_min: Optional[int] = Field(None, ge=1, le=1440)
    price_cents: Optional[int] = Field(None, ge=0, le=100_000_000)
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None


class SchedulePatch(_Base):
    weekday: Optional[int] = Field(None, ge=0, le=6)
    time: Optional[str] = Field(None, pattern=_HHMM)
    duration_min: Optional[int] = Field(None, ge=1, le=1440)
    price_cents: Optional[int] = Field(None, ge=0, le=100_000_000)
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    active: Optional[bool] = None


class PaymentBody(_Base):
    amount_cents: int = Field(gt=0, le=100_000_000_000)
    paid_on: date
    account_id: UUID
    method: str = Field(min_length=1, max_length=60)
    entry_ids: Optional[list[UUID]] = Field(None, max_length=500)
    notes: Optional[str] = Field(None, max_length=2000)


__all__ = ["ClientBody", "ClientPatch", "PaymentBody", "ScheduleBody", "SchedulePatch", "SessionBody", "SessionPatch"]
