"""Inbound bodies — strict at the HTTP boundary (`extra="forbid"`)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from noctusai_lib.api import StrictHttpModel


class LoteIniciarBody(StrictHttpModel):
    imovel_codigo: str = Field(min_length=1, max_length=40)
    nome: Optional[str] = Field(default=None, min_length=1, max_length=120)
    velocidade: Optional[Literal["urgente", "economico"]] = None
