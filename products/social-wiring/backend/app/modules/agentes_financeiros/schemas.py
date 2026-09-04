"""Request bodies for the financing-agent registry.

`StrictHttpModel` (the seed's base) forbids unknown keys, so a typo in a
client's payload is a 422 naming the field rather than a silently ignored
value. See `KB § PATTERNS/backend/pydantic-strict-http.md`.
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class AgenteFinanceiroCreateBody(StrictHttpModel):
    """Register a financing agent.

    `nome` is the only required field. Everything else is contact detail an
    agency fills in over time, and refusing to save a partly-filled form
    loses whatever they had typed — the same call migration 100 makes by
    leaving every column but the name nullable.
    """

    nome: str = Field(min_length=1, max_length=255)
    #: Brazilian payment-system code — "104" for Caixa. A string, not an int:
    #: the codes are zero-padded and "001" is not 1 on any document that
    #: prints it.
    codigo_banco: Optional[str] = Field(default=None, max_length=16)
    agencia: Optional[str] = Field(default=None, max_length=32)
    contato_nome: Optional[str] = Field(default=None, max_length=255)
    contato_email: Optional[str] = Field(default=None, max_length=255)
    contato_telefone: Optional[str] = Field(default=None, max_length=32)
    observacoes: Optional[str] = Field(default=None, max_length=2000)
    ativo: Optional[bool] = None


class AgenteFinanceiroPatchBody(StrictHttpModel):
    """Update an agent. Every field optional — `exclude_unset` in the route
    is what makes an omitted key mean "leave it alone" and an explicit null
    mean "clear it"."""

    nome: Optional[str] = Field(default=None, min_length=1, max_length=255)
    codigo_banco: Optional[str] = Field(default=None, max_length=16)
    agencia: Optional[str] = Field(default=None, max_length=32)
    contato_nome: Optional[str] = Field(default=None, max_length=255)
    contato_email: Optional[str] = Field(default=None, max_length=255)
    contato_telefone: Optional[str] = Field(default=None, max_length=32)
    observacoes: Optional[str] = Field(default=None, max_length=2000)
    #: Retiring an agent is a PATCH of this field — never a DELETE. The
    #: registry's whole point is that history keeps rendering the bank that
    #: financed it.
    ativo: Optional[bool] = None
