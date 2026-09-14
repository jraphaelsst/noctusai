"""Inbound HTTP shapes for the certidões module.

`StrictHttpModel` (`extra="forbid"`) rather than a plain `BaseModel`: Pydantic's
default is to SILENTLY DROP an unknown field, so a frontend that sends
`nomeMae` instead of `nome_mae` would get a 200 and a certidão issued without
the mother's name — which for TJSP is a rejected request three minutes later,
attributed to nothing. → KB § PATTERNS/backend/pydantic-strict-http.md
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

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


class VincularParteRequest(StrictHttpModel):
    """Attach a consulta to one party of an atendimento.

    `atendimento_parte_id`, not `cliente_id`: the party's `cliente_id` is
    resolved server-side off the `atendimento_partes` row (migration 073) so
    a caller cannot link a consulta to a person who is not actually party to
    this atendimento — see `routers/certidoes.py::vincular_parte`.
    """

    atendimento_parte_id: UUID


class ResultadoPatch(StrictHttpModel):
    """A human's correction/confirmation of one resultado's structured
    fields. Every field is OPTIONAL — an empty body is a valid "I reviewed
    the API/IA-suggested values and they are correct" confirmation, not a
    no-op; see `routers/certidoes.py::confirmar_ou_corrigir_resultado`.

    `resultado`'s `Literal` MUST stay in sync with migration 107's
    `certidao_resultados_resultado_check` and `registry.RESULTADO_VALUES`.
    """

    numero: Optional[str] = Field(None, max_length=100)
    emitida_em: Optional[date] = None
    validade_ate: Optional[date] = None
    resultado: Optional[Literal[
        "negativa", "positiva", "positiva_com_efeito_de_negativa", "nao_emitida",
    ]] = None


__all__ = ["ConsultaCreate", "ResultadoPatch", "VincularParteRequest"]
