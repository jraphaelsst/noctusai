"""Request bodies for the parties routes (`StrictHttpModel`, `extra="forbid"`).

Pydantic's silent drop of unknown keys would swallow a misspelled field on a WRITE; forbidding
extras turns it into a 422.
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from .types import PartyKind, PartyRole

#: Phones per party (a sanity bound, not a business rule).
MAX_PHONES = 5


class Address(StrictHttpModel):
    street: Optional[str] = Field(default=None, max_length=200)
    number: Optional[str] = Field(default=None, max_length=20)
    complement: Optional[str] = Field(default=None, max_length=100)
    district: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=2)
    zip: Optional[str] = Field(default=None, max_length=12)
    country: Optional[str] = Field(default=None, max_length=60)


ADDRESS_FIELDS: tuple[str, ...] = tuple(Address.model_fields)


class PartyBody(StrictHttpModel):
    kind: PartyKind
    doc: Optional[str] = Field(default=None, max_length=24)
    legal_name: str = Field(min_length=1, max_length=200)
    trade_name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    phones: list[str] = Field(default_factory=list, max_length=MAX_PHONES)
    address: Optional[Address] = None
    state_registration: Optional[str] = Field(default=None, max_length=30)
    municipal_registration: Optional[str] = Field(default=None, max_length=30)
    notes: Optional[str] = Field(default=None, max_length=2000)
    roles: list[PartyRole] = Field(default_factory=list, max_length=len(PartyRole))


class PartyPatch(StrictHttpModel):
    kind: Optional[PartyKind] = None
    doc: Optional[str] = Field(default=None, max_length=24)
    legal_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    trade_name: Optional[str] = Field(default=None, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    phones: Optional[list[str]] = Field(default=None, max_length=MAX_PHONES)
    address: Optional[Address] = None
    state_registration: Optional[str] = Field(default=None, max_length=30)
    municipal_registration: Optional[str] = Field(default=None, max_length=30)
    notes: Optional[str] = Field(default=None, max_length=2000)
    roles: Optional[list[PartyRole]] = Field(default=None, max_length=len(PartyRole))


class RolesBody(StrictHttpModel):
    roles: list[PartyRole] = Field(max_length=len(PartyRole))


__all__ = ["ADDRESS_FIELDS", "Address", "MAX_PHONES", "PartyBody", "PartyPatch", "RolesBody"]
