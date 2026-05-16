"""Pydantic schemas for contact lists."""
from typing import Optional
from pydantic import Field
from noctusai_lib.api import StrictHttpModel


class ListCreate(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=200)
    descricao: Optional[str] = None
    tipo: str = "static"
    filtros: dict = Field(default_factory=dict)


class ListUpdate(StrictHttpModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    filtros: Optional[dict] = None


class ListMembersAdd(StrictHttpModel):
    contact_ids: list[str]


class ListMembersRemove(StrictHttpModel):
    contact_ids: list[str]
