"""Finance errors -- `AppException` subclasses so the seed's handlers render
`{"error": {"code", "message", "details"}}` with the right status.

Contract-pinned pt-BR codes are constants so tests and the frontend organ never
retype the string.
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

CATEGORIA_EM_USO = "categoria_em_uso"
LANCAMENTO_COM_BAIXA = "lancamento_com_baixa"
LANCAMENTO_CANCELADO = "lancamento_cancelado"
BAIXA_EXCEDE_SALDO = "baixa_excede_saldo"
ESTORNO_EXCEDE_PAGO = "estorno_excede_pago"
BAIXA_JA_ESTORNADA = "baixa_ja_estornada"
BAIXA_DUPLICADA = "baixa_duplicada"
CONTA_GATEWAY_DUPLICADA = "conta_gateway_duplicada"
CONTA_COM_MOVIMENTO = "conta_com_movimento"
CONTA_INATIVA = "conta_inativa"
CATEGORIA_DUPLICADA = "categoria_duplicada"
CENTRO_CUSTO_DUPLICADO = "centro_custo_duplicado"
LANCAMENTO_DUPLICADO = "lancamento_duplicado"
ANEXO_INVALIDO = "anexo_invalido"
ANEXO_GRANDE_DEMAIS = "anexo_grande_demais"
ANEXO_LIMITE = "anexo_limite"
DOCUMENTO_INVALIDO = "documento_invalido"
LANCAMENTO_COM_HISTORICO = "lancamento_com_historico"
LANCAMENTO_DE_SISTEMA = "lancamento_de_sistema"
CONTA_EM_USO = "conta_em_uso"


class FinanceError(OrganError):
    """A finance refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(FinanceError)


__all__ = [
    "ANEXO_GRANDE_DEMAIS",
    "ANEXO_INVALIDO",
    "ANEXO_LIMITE",
    "BAIXA_DUPLICADA",
    "BAIXA_EXCEDE_SALDO",
    "BAIXA_JA_ESTORNADA",
    "CATEGORIA_DUPLICADA",
    "CATEGORIA_EM_USO",
    "CENTRO_CUSTO_DUPLICADO",
    "CONTA_COM_MOVIMENTO",
    "CONTA_EM_USO",
    "CONTA_GATEWAY_DUPLICADA",
    "CONTA_INATIVA",
    "DOCUMENTO_INVALIDO",
    "ESTORNO_EXCEDE_PAGO",
    "FinanceError",
    "LANCAMENTO_CANCELADO",
    "LANCAMENTO_COM_BAIXA",
    "LANCAMENTO_COM_HISTORICO",
    "LANCAMENTO_DE_SISTEMA",
    "LANCAMENTO_DUPLICADO",
    "conflict",
    "invalid",
    "not_found",
]
