"""Request bodies for the structured-matrícula routes (migrations 109, 115).

`StrictHttpModel` (house default) rejects unknown keys, so a typo'd field is a
422 naming it rather than a silently-ignored value.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.integrations.documents import NaturezaAto


class ExtracaoDeDocumentoBody(StrictHttpModel):
    """Transcribe a matrícula PDF already attached to an imóvel."""

    codigo: str = Field(min_length=1, max_length=64)
    imovel_documento_id: UUID


class SelecaoPermutaBody(StrictHttpModel):
    """The acts quoted from the matrícula of a property given in EXCHANGE
    (migration 115). `extracao_id`'s imóvel must be the permuta ativo's."""

    permuta_ativo_id: UUID
    extracao_id: UUID
    ato_ids: list[UUID] = Field(min_length=1, max_length=500)


class SelecaoAtosBody(StrictHttpModel):
    """The acts a contract quotes, in the order they appear in it.

    Replaces the whole selection — the object's acts AND every permuta's. An
    empty `ato_ids` clears the object's quote (and then `extracao_id` may be
    omitted); otherwise every id must belong to `extracao_id`.
    """

    extracao_id: Optional[UUID] = None
    ato_ids: list[UUID] = Field(default_factory=list, max_length=500)
    permutas: list[SelecaoPermutaBody] = Field(default_factory=list, max_length=20)


class FontesMatriculaBody(StrictHttpModel):
    """The operator's choice of título aquisitivo / ônus source acts.

    Absence means "leave alone" (`model_fields_set`, never `is None`): `null`
    for the título, or `null` / `[]` for the ônus, clears that pointer. Writing
    a pointer IS the confirmation — the heuristic never writes one.
    """

    titulo_aquisitivo_ato_id: Optional[UUID] = None
    onus_ato_ids: Optional[list[UUID]] = Field(default=None, max_length=200)


class ParteBody(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=200)
    cpf_cnpj: Optional[str] = Field(default=None, max_length=32)


class InstrumentoBody(StrictHttpModel):
    tipo: Optional[str] = Field(default=None, max_length=200)
    data: Optional[date] = None
    tabelionato: Optional[str] = Field(default=None, max_length=200)
    livro: Optional[str] = Field(default=None, max_length=40)
    folhas: Optional[str] = Field(default=None, max_length=40)
    cidade: Optional[str] = Field(default=None, max_length=120)


class AtoReferidoBody(StrictHttpModel):
    kind: Literal["R", "AV"]
    numero: int = Field(ge=0, le=99999)


class DetalhesAtoBody(StrictHttpModel):
    """Confirm an act's details, editing any subset (migration 115).

    Absence means "keep the suggestion"; `null` (or `[]`) clears the field. An
    empty body confirms the suggestion as it stands — the request IS the
    confirmation.
    """

    natureza: Optional[NaturezaAto] = None
    data_registro: Optional[date] = None
    valor: Optional[Decimal] = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    transmitentes: Optional[list[ParteBody]] = Field(default=None, max_length=50)
    adquirentes: Optional[list[ParteBody]] = Field(default=None, max_length=50)
    credor: Optional[str] = Field(default=None, max_length=300)
    instrumento: Optional[InstrumentoBody] = None
    atos_referidos: Optional[list[AtoReferidoBody]] = Field(default=None, max_length=100)


class TituloAquisitivoTextoBody(StrictHttpModel):
    """The título aquisitivo phrase the operator confirms. Required key;
    `null` (or blank) clears the confirmation."""

    texto: Optional[str] = Field(..., max_length=2000)


class OnusCredorBody(StrictHttpModel):
    """The ônus creditor the operator confirms. Required key; `null` clears."""

    credor: Optional[str] = Field(..., max_length=300)


__all__ = [
    "AtoReferidoBody",
    "DetalhesAtoBody",
    "ExtracaoDeDocumentoBody",
    "FontesMatriculaBody",
    "InstrumentoBody",
    "OnusCredorBody",
    "ParteBody",
    "SelecaoAtosBody",
    "SelecaoPermutaBody",
    "TituloAquisitivoTextoBody",
]
