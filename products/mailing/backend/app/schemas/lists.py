"""Pydantic schemas for contact lists."""
from typing import Optional
from pydantic import BaseModel, Field


class ListCreate(BaseModel):
    nome: str = Field(..., min_length=1, max_length=200)
    descricao: Optional[str] = None
    tipo: str = "static"
    filtros: dict = Field(default_factory=dict)


class ListUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    filtros: Optional[dict] = None


class ListMembersAdd(BaseModel):
    contact_ids: list[str]


class ListMembersRemove(BaseModel):
    contact_ids: list[str]
