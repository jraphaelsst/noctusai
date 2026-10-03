"""HTTP-boundary shapes for aditivos — strict (`extra="forbid"`), and the
ONE place the structured amendment vocabulary is spelled.

An amendment is `{tipo, clausula_alvo, …parameters}` — a discriminated union
on `tipo`, so a posse amendment cannot carry a stray `texto` and an `outro`
cannot omit it. The persisted `alteracoes` JSONB is exactly
`model_dump(mode="json")` of these models, so what the gate/render read back
is what this module validated.

Contract for the FE: `products/social-wiring/projects/contrato-aditivos-CONTRACT.md`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Optional, Union
from uuid import UUID

from pydantic import Field, model_validator

from noctusai_lib.api import StrictHttpModel

ESTILOS: tuple[str, ...] = ("house", "formal")
TIPOS_ALTERACAO: tuple[str, ...] = ("pagamento", "posse", "comissao", "outro")
#: `atendimento_negociacao_parcelas`' vocabulary minus 'permuta' — migration
#: 190's CHECK (a permuta is settled by deed; amending it is an `outro`).
TIPOS_PARCELA_ADITIVO: tuple[str, ...] = (
    "sinal", "intermediaria", "financiamento", "fgts", "saldo", "direta",
)

#: The original's clause an amendment rewrites, by NUMBER (1 = Primeira).
ClausulaAlvo = Annotated[int, Field(ge=1, le=59)]


class AlteracaoPagamento(StrictHttpModel):
    """The payment schedule is RESTATED in full (the corpus' 858/868 shape):
    the new parcelas live in `parcelas` on the aditivo, never in free text.
    `novo_valor` set = the price itself changes (else the new parcelas must
    sum to the original price)."""

    tipo: Literal["pagamento"]
    clausula_alvo: ClausulaAlvo
    novo_valor: Optional[Decimal] = Field(default=None, gt=0, max_digits=14, decimal_places=2)


class AlteracaoPosse(StrictHttpModel):
    """827 (posse precária for a purpose) / 867 (posse definitiva on a date)."""

    tipo: Literal["posse"]
    clausula_alvo: ClausulaAlvo
    data: date
    precaria: bool = False
    #: Required when `precaria` — "com o objetivo de realizar {finalidade}".
    finalidade: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _finalidade_quando_precaria(self) -> "AlteracaoPosse":
        if self.precaria and not (self.finalidade or "").strip():
            raise ValueError("posse precária exige a finalidade")
        return self


class AlteracaoComissao(StrictHttpModel):
    """858/867: WHEN a commission installment is paid. `marco='parcela'`
    names a parcela by its printed number — of the aditivo's restated
    schedule when the aditivo also amends the payment, else of the original
    ("Parcela NN do contrato original")."""

    tipo: Literal["comissao"]
    clausula_alvo: ClausulaAlvo
    #: Which installment of the corretagem (1 = a primeira).
    parcela_corretagem: int = Field(ge=1, le=12)
    marco: Literal["parcela", "data", "financiamento"]
    parcela_numero: Optional[int] = Field(default=None, ge=1, le=99)
    data: Optional[date] = None

    @model_validator(mode="after")
    def _marco_completo(self) -> "AlteracaoComissao":
        if self.marco == "parcela" and self.parcela_numero is None:
            raise ValueError("marco 'parcela' exige parcela_numero")
        if self.marco == "data" and self.data is None:
            raise ValueError("marco 'data' exige data")
        return self


class AlteracaoOutro(StrictHttpModel):
    """Free text, printed as an extra clause — and named in the version's
    legal review (it is the one amendment the system cannot vouch for)."""

    tipo: Literal["outro"]
    clausula_alvo: Optional[ClausulaAlvo] = None
    titulo: str = Field(min_length=3, max_length=120)
    texto: str = Field(min_length=10, max_length=8000)


Alteracao = Annotated[
    Union[AlteracaoPagamento, AlteracaoPosse, AlteracaoComissao, AlteracaoOutro],
    Field(discriminator="tipo"),
]


class ParcelaAditivoIn(StrictHttpModel):
    """Same fields as a negociação parcela (`negociacao_estruturada_router.
    ParcelaCreateBody`), minus permuta links. Order = list order."""

    tipo: Literal["sinal", "intermediaria", "financiamento", "fgts", "saldo", "direta"]
    valor: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    vencimento: Optional[date] = None
    evento: Optional[str] = Field(default=None, max_length=500)
    forma_pagamento: Optional[str] = Field(default=None, max_length=60)
    favorecido_id: Optional[UUID] = None
    confissao_divida: bool = False


def _uma_por_tipo_exclusivo(alteracoes: list) -> None:
    for tipo in ("pagamento", "posse"):
        if sum(1 for a in alteracoes if a.tipo == tipo) > 1:
            raise ValueError(f"no máximo uma alteração do tipo '{tipo}' por aditivo")


class AditivoCreateBody(StrictHttpModel):
    estilo: Literal["house", "formal"] = "house"
    alteracoes: list[Alteracao] = Field(default_factory=list, max_length=20)
    #: Replace-all: the restated schedule of a `pagamento` amendment.
    parcelas: list[ParcelaAditivoIn] = Field(default_factory=list, max_length=60)
    assinatura_data: Optional[date] = None
    modalidade_assinatura: Literal["digital", "fisica"] = "digital"

    @model_validator(mode="after")
    def _exclusivos(self) -> "AditivoCreateBody":
        _uma_por_tipo_exclusivo(self.alteracoes)
        return self


class AditivoPatchBody(StrictHttpModel):
    """Every field optional; a present `alteracoes`/`parcelas` REPLACES the
    whole list. `status` follows the contract's any-to-any vocabulary."""

    estilo: Optional[Literal["house", "formal"]] = None
    alteracoes: Optional[list[Alteracao]] = Field(default=None, max_length=20)
    parcelas: Optional[list[ParcelaAditivoIn]] = Field(default=None, max_length=60)
    assinatura_data: Optional[date] = None
    modalidade_assinatura: Optional[Literal["digital", "fisica"]] = None
    status: Optional[
        Literal["rascunho", "em_revisao", "enviado_assinatura", "assinado", "cancelado"]
    ] = None

    @model_validator(mode="after")
    def _exclusivos(self) -> "AditivoPatchBody":
        if self.alteracoes is not None:
            _uma_por_tipo_exclusivo(self.alteracoes)
        return self


class GerarAditivoBody(StrictHttpModel):
    #: Dates the aditivo — absent: the stored `assinatura_data`, then today.
    assinatura_data: Optional[date] = None


__all__ = [
    "AditivoCreateBody",
    "AditivoPatchBody",
    "Alteracao",
    "AlteracaoComissao",
    "AlteracaoOutro",
    "AlteracaoPagamento",
    "AlteracaoPosse",
    "ESTILOS",
    "GerarAditivoBody",
    "ParcelaAditivoIn",
    "TIPOS_ALTERACAO",
    "TIPOS_PARCELA_ADITIVO",
]
