"""Schema for `POST /api/cadastro` — contract §Identity, slice BE-A.
PUBLIC, rate-limited, Turnstile-gated (checked like `/api/checkout`).
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

#: Same shape as `schemas/membros.py`'s `_PHONE_RE` — duplicated rather
#: than imported (that module is module 1's, this is BE-A's own).
_PHONE_RE = r"^\+[1-9]\d{7,14}$"


class CadastroCreate(BaseModel):
    """Request body for `POST /api/cadastro`."""

    model_config = ConfigDict(extra="forbid")

    nome: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    telefone: Optional[str] = Field(None, pattern=_PHONE_RE)
    senha: str = Field(..., min_length=8, max_length=72)
    # Optional at the Pydantic level on purpose, same as
    # `schemas/checkout.py`'s `CheckoutCreate.turnstile_token` — a missing
    # token is a 403 BUSINESS rule (contract-pinned message), not a 422
    # shape error; enforced in `cadastro_service.py`.
    turnstile_token: Optional[str] = None
    aceite_termos: bool


class CadastroOut(BaseModel):
    """Response body for `POST /api/cadastro` (201)."""

    membro_id: UUID
    email: str
    proximo_passo: str
