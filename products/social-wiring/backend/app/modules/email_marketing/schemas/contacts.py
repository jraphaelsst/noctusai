"""Pydantic schemas for contacts."""
from typing import Optional
from pydantic import EmailStr, Field
from noctusai_lib.api import StrictHttpModel


class ContactCreate(StrictHttpModel):
    email: EmailStr
    nome: Optional[str] = None
    telefone: Optional[str] = None
    empresa: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    custom_fields: dict = Field(default_factory=dict)
    source: str = "manual"


class ContactUpdate(StrictHttpModel):
    # `email` is editable (a typo'd address must be correctable). It was
    # absent here while the Contatos edit form sent it — and because this
    # is a StrictHttpModel (`extra="forbid"`), EVERY contact edit 422'd in
    # prod. Re-adding it makes the schema match the contract the FE has
    # always spoken.
    #
    # The column carries UNIQUE(org_id, email), so re-pointing a contact at
    # an address already used in the org raises PostgREST 23505 — which the
    # seed's `postgrest_exception_handler` (registered in `app_factory`)
    # already maps to a 409 CONFLICT. No local try/except needed; adding one
    # would fork that seam.
    email: Optional[EmailStr] = None
    nome: Optional[str] = None
    telefone: Optional[str] = None
    empresa: Optional[str] = None
    tags: Optional[list[str]] = None
    custom_fields: Optional[dict] = None


class ContactImport(StrictHttpModel):
    """CSV import — expects a list of contacts."""
    contacts: list[ContactCreate]
