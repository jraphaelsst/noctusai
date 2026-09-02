"""Inbound HTTP shapes for the certidões module.

`StrictHttpModel` (`extra="forbid"`) rather than a plain `BaseModel`: Pydantic's
default is to SILENTLY DROP an unknown field, so a frontend that sends
`nomeMae` instead of `nome_mae` would get a 200 and a certidão issued without
the mother's name — which for TJSP is a rejected request three minutes later,
attributed to nothing. → KB § PATTERNS/backend/pydantic-strict-http.md
"""
from __future__ import annotations

from typing import Literal, Optional

from noctusai_lib.api import StrictHttpModel
from pydantic import Field


class ConsultaCreate(StrictHttpModel):
    """A request to issue the full certificate set for one CPF/CNPJ.

    The optional fields are not decoration: `data_nascimento` is required by
    CND Federal and TJSP, and `rg` / `genero` / `nome_mae` / `nome_pai` are what
    TJSP uses to disambiguate a common name. They are optional because the
    other eight certificates do not need them, and refusing the whole request
    for a field only one endpoint wants would block nine that would have
    succeeded.
    """

    tipo_documento: Literal["cpf", "cnpj"]
    documento: str = Field(..., min_length=11, max_length=18)
    nome: str = Field(..., min_length=2, max_length=200)
    data_nascimento: Optional[str] = None
    genero: Optional[Literal["M", "F"]] = None
    rg: Optional[str] = None
    nome_mae: Optional[str] = None
    nome_pai: Optional[str] = None


__all__ = ["ConsultaCreate"]
