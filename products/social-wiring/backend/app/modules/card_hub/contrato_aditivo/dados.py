"""The aditivo's pure input — what the gate and the render read besides the
original contract's own `DadosContrato` (parties, imóvel, testemunhas,
favorecidos, the original schedule), which `contrato_gerador.carregador`
loads unchanged.

`alteracoes` are the validated `schemas.Alteracao` models (parsed back from
the stored JSONB), `parcelas` are `contrato_gerador.dados.Parcela` — the SAME
type the generator's sum/order gate and parcela wording consume, so neither
is re-implemented here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from pydantic import TypeAdapter

from app.modules.card_hub.contrato_aditivo.schemas import Alteracao
from app.modules.card_hub.contrato_gerador.dados import Parcela

_ALTERACOES = TypeAdapter(list[Alteracao])


def alteracoes_de_json(bruto: object) -> list:
    """Stored JSONB -> validated models. A row written by this module always
    re-validates; anything else is a loud error, never a silent drop."""
    return _ALTERACOES.validate_python(bruto or [])


def alteracoes_para_json(alteracoes: list) -> list[dict]:
    return _ALTERACOES.dump_python(alteracoes, mode="json")


@dataclass
class DadosAditivo:
    aditivo_id: str
    contrato_id: str
    ordinal: int
    estilo: str
    status: str
    alteracoes: list = field(default_factory=list)
    #: The restated schedule (a `pagamento` amendment), in print order.
    parcelas: list[Parcela] = field(default_factory=list)
    assinatura_data: Optional[date] = None
    modalidade_assinatura: str = "digital"
    #: The ORIGINAL contract's lifecycle — what makes an aditivo possible.
    original_status: str = "rascunho"
    #: The date the original was signed — cited by every aditivo.
    original_assinatura_data: Optional[date] = None
    original_origem: str = "upload"

    def alteracoes_do_tipo(self, tipo: str) -> list:
        return [a for a in self.alteracoes if a.tipo == tipo]

    @property
    def pagamento(self):
        achadas = self.alteracoes_do_tipo("pagamento")
        return achadas[0] if achadas else None


__all__ = ["DadosAditivo", "alteracoes_de_json", "alteracoes_para_json"]
