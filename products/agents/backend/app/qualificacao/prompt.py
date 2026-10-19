"""A pinned standard version as the prompt compiler's pure input (CONTRACT §2.6 / §3).

``qualificacao_data`` is the single adapter from the standard's rows (:class:`VersaoPadrao`) to
:class:`~app.studio.models.QualificacaoData`: every word the model reads about the standard is a row
(criterion label/description/options, stage label/description); this module only selects and orders.
"""
from __future__ import annotations

from app.qualificacao.models import VersaoPadrao
from app.qualificacao.regras import criterios_referenciados
from app.studio.models import CriterioData, EstagioData, QualificacaoData

__all__ = ["qualificacao_data"]


def qualificacao_data(v: VersaoPadrao) -> QualificacaoData:
    ativos = [c for c in v.criterios if c.ativo and c.tipo != "derivado"]
    return QualificacaoData(
        versao_id=v.id,
        criterios=tuple(
            CriterioData(
                chave=c.chave, rotulo=c.rotulo, descricao_modelo=c.descricao_modelo, grupo=c.grupo,
                ordem=c.ordem, opcoes=tuple((o.valor, o.rotulo, o.descricao_modelo) for o in c.opcoes),
            )
            for c in ativos if c.tipo != "identificacao"
        ),
        estagios=tuple(
            EstagioData(chave=e.chave, rotulo=e.rotulo, descricao=e.descricao, ordem=e.ordem)
            for e in v.estagios
        ),
        minimo_para_ofertar=tuple(criterios_referenciados(v.parametros.minimo_para_ofertar)),
        identidade=tuple((c.chave, c.descricao_modelo) for c in ativos if c.tipo == "identificacao"),
    )
