"""Schemas for the public checkout flow — contract §Checkout, amendments
A1-A5/A10, product decisions P1 (CPF) / P2 (Turnstile).
"""
from __future__ import annotations

import re
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

_PHONE_RE = r"^\+[1-9]\d{7,14}$"
_NON_DIGITS_RE = re.compile(r"\D+")

CheckoutMetodo = Literal["cartao", "pix", "boleto"]


class CheckoutCreate(BaseModel):
    """Request body for `POST /api/checkout` (PUBLIC)."""

    model_config = ConfigDict(extra="forbid")

    plano_id: UUID
    metodo: CheckoutMetodo
    nome: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    telefone: str = Field(..., pattern=_PHONE_RE)
    # Product decision P1: required (11 digits) for pix/boleto, FORBIDDEN
    # for cartao — both branches 422 via this validator, never persisted
    # anywhere (see checkout_service.py's module docstring).
    cpf: Optional[str] = Field(None, max_length=32)
    # Product decision P2: the Cloudflare Turnstile token the FE widget
    # produced. Optional at the Pydantic level on purpose — a missing
    # token is a 403 BUSINESS rule (contract-pinned message), not a 422
    # shape error; enforced in `checkout_service.py`.
    turnstile_token: Optional[str] = None

    @model_validator(mode="after")
    def _validate_cpf(self) -> "CheckoutCreate":
        if self.metodo == "cartao":
            if self.cpf is not None:
                raise ValueError("cpf não deve ser enviado para o método cartão.")
            return self
        # pix / boleto
        if not self.cpf:
            raise ValueError("cpf é obrigatório para pix e boleto.")
        digits = _NON_DIGITS_RE.sub("", self.cpf)
        if len(digits) != 11:
            raise ValueError("cpf deve conter 11 dígitos.")
        self.cpf = digits
        return self


class PixQrOut(BaseModel):
    """Contract's `pix_qr` sub-object."""

    payload: str
    imagem_base64: str
    expira_em: Optional[str] = None


class CheckoutOut(BaseModel):
    """Response body for `POST /api/checkout`.

    `status` is `None` on the ordinary happy path; amendment A2 sets it
    to `"verifique_seu_email"` when the resolved email already belongs
    to an `ativo` member (the SAME status code + key set either way — no
    public response may vary on whether the email exists). The
    contract's amendment A10 asaas-only reuse-dedupe (see
    `checkout_service.py`) sets it to `"checkout_em_andamento"`.
    """

    checkout_url: Optional[str] = None
    assinatura_id: UUID
    membro_id: UUID
    pix_qr: Optional[PixQrOut] = None
    status: Optional[str] = None
