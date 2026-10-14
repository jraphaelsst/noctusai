"""Contracts errors -- `AppException` subclasses (`{"error": {"code", "message", "details"}}`)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

CONTRATO_FINALIZADO = "contrato_finalizado"
TRANSICAO_INVALIDA = "transicao_invalida"
CONTRATO_VIGENTE = "contrato_vigente_use_aditivo"
CONTRATO_NAO_RASCUNHO = "contrato_nao_rascunho"
PARTE_INVALIDA = "parte_invalida"
ITEM_INVALIDO = "item_invalido"
NUMERO_DUPLICADO = "numero_duplicado"
COTACAO_DUPLICADA = "cotacao_duplicada"
MODELO_COBRANCA_INVALIDO = "modelo_cobranca_invalido"
REAJUSTE_NAO_APLICAVEL = "reajuste_nao_aplicavel"
AVISO_PREVIO = "aviso_previo_nao_cumprido"
PERIODO_JA_FATURADO = "periodo_ja_faturado"
USO_NAO_APLICAVEL = "uso_nao_aplicavel"
ASSINATURA_NAO_CONFIGURADA = "assinatura_nao_configurada"
ASSINATURA_EM_ANDAMENTO = "assinatura_em_andamento"
ASSINATURA_REQUERIDA = "assinatura_requerida"
SIGNATARIO_INVALIDO = "signatario_invalido"
DOCUMENTO_NAO_GERADO = "documento_nao_gerado"
ARMAZENAMENTO_NAO_CONFIGURADO = "armazenamento_nao_configurado"
ANEXO_LIMITE = "anexo_limite"
COBRANCA_NAO_CONFIGURADA = "cobranca_nao_configurada"


class ContractsError(OrganError):
    """A contracts refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(ContractsError)


__all__ = [
    "ANEXO_LIMITE",
    "ARMAZENAMENTO_NAO_CONFIGURADO",
    "ASSINATURA_EM_ANDAMENTO",
    "ASSINATURA_NAO_CONFIGURADA",
    "ASSINATURA_REQUERIDA",
    "AVISO_PREVIO",
    "COBRANCA_NAO_CONFIGURADA",
    "CONTRATO_FINALIZADO",
    "CONTRATO_NAO_RASCUNHO",
    "CONTRATO_VIGENTE",
    "COTACAO_DUPLICADA",
    "DOCUMENTO_NAO_GERADO",
    "ITEM_INVALIDO",
    "MODELO_COBRANCA_INVALIDO",
    "NUMERO_DUPLICADO",
    "PARTE_INVALIDA",
    "PERIODO_JA_FATURADO",
    "REAJUSTE_NAO_APLICAVEL",
    "SIGNATARIO_INVALIDO",
    "TRANSICAO_INVALIDA",
    "USO_NAO_APLICAVEL",
    "ContractsError",
    "conflict",
    "invalid",
    "not_found",
]
