"""Pydantic schemas for contacts."""
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class ContactCreate(BaseModel):
    email: EmailStr
    nome: Optional[str] = None
    telefone: Optional[str] = None
    empresa: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    custom_fields: dict = Field(default_factory=dict)
    source: str = "manual"


class ContactUpdate(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    empresa: Optional[str] = None
    tags: Optional[list[str]] = None
    custom_fields: Optional[dict] = None


class ContactImport(BaseModel):
    """CSV import — expects a list of contacts."""
    contacts: list[ContactCreate]
