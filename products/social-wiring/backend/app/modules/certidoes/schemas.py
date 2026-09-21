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


class ConsultaManualCreate(ConsultaCreate):
    """`POST /consultas/manual` — same shape as `ConsultaCreate`, plus an
    OPTIONAL, mutually exclusive link to a party or a card's titular, done
    atomically at creation time rather than in a second `vincular-*` call.

    Both `atendimento_parte_id` and `cliente_id` are optional and neither is
    required: the "record a certidão obtained elsewhere" use case creates an
    unlinked ad-hoc consulta exactly like `ConsultaCreate` always could, and
    `routers/certidoes.py::criar_consulta_manual` still fans out one
    placeholder resultado per required type either way. See that function's
    own docstring for why sending BOTH is refused rather than one silently
    winning.
    """

    atendimento_parte_id: Optional[UUID] = None
    cliente_id: Optional[UUID] = None


class VincularParteRequest(StrictHttpModel):
    """Attach a consulta to one party of an atendimento.

    `atendimento_parte_id`, not `cliente_id`: the party's `cliente_id` is
    resolved server-side off the `atendimento_partes` row (migration 073) so
    a caller cannot link a consulta to a person who is not actually party to
    this atendimento — see `routers/certidoes.py::vincular_parte`.
    """

    atendimento_parte_id: UUID


class VincularClienteRequest(StrictHttpModel):
    """Attach a consulta to a card's TITULAR — `atendimentos.cliente_id`.

    `vincular_parte`'s sibling for the one party it cannot reach: the
    titular has no `atendimento_partes` row at all (migration 073's header),
    so there is nothing to resolve a `cliente_id` off — the caller names it
    directly. `cliente_id` is still validated against THIS org server-side
    (`routers/certidoes.py::vincular_cliente`), the same way `vincular_parte`
    validates its party — a caller cannot link a consulta to a stranger's
    record either way.
    """

    cliente_id: UUID


class ResultadoPatch(StrictHttpModel):
    """A human's correction/confirmation of one resultado's structured
    fields. Every field is OPTIONAL — an empty body is a valid "I reviewed
    the API/IA-suggested values and they are correct" confirmation, not a
    no-op; see `routers/certidoes.py::confirmar_ou_corrigir_resultado`.

    `resultado`'s `Literal` MUST stay in sync with migration 107 (widened by
    116 to add `negativa_com_homonimos`)'s `certidao_resultados_resultado_
    check` and `registry.RESULTADO_VALUES`.
    """

    numero: Optional[str] = Field(None, max_length=100)
    emitida_em: Optional[date] = None
    validade_ate: Optional[date] = None
    resultado: Optional[Literal[
        "negativa", "positiva", "positiva_com_efeito_de_negativa", "nao_emitida",
        "negativa_com_homonimos",
    ]] = None


class SituacaoCadastralPatch(StrictHttpModel):
    """A human's manual entry of the CNPJ/CPF's registration status
    (migration 116) — `situacao_cadastral` / `data_situacao` on the
    CONSULTA, not on any one resultado: the registration state is a fact
    about the document being investigated, not about any single certificate
    type. See `routers/certidoes.py::atualizar_situacao_cadastral`.

    Both fields optional, but at least one is required — the router refuses
    an empty body with a 422 rather than silently stamping
    `situacao_origem='manual'` over nothing.
    """

    situacao_cadastral: Optional[Literal[
        "ativa", "baixada", "inapta", "suspensa", "nula",
    ]] = None
    data_situacao: Optional[date] = None


__all__ = [
    "ConsultaCreate",
    "ConsultaManualCreate",
    "ResultadoPatch",
    "SituacaoCadastralPatch",
    "VincularClienteRequest",
    "VincularParteRequest",
]
