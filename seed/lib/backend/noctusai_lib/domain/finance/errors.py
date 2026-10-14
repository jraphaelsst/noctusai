"""Finance errors -- `AppException` subclasses so the seed's handlers render
`{"error": {"code", "message", "details"}}` with the right status.

Contract-pinned pt-BR codes are constants so tests and the frontend organ never
retype the string.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

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


class FinanceError(AppException):
    """A finance refusal carrying its stable machine `code`."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 422,
        *,
        field: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        merged = dict(details or {})
        if field:
            merged["field"] = field
        super().__init__(code=code, message=message, status_code=status_code, details=merged)


def invalid(field: str, message: str, code: str = "invalid") -> FinanceError:
    return FinanceError(code, message, 422, field=field)


def conflict(code: str, message: str, **details) -> FinanceError:
    return FinanceError(code, message, 409, details=details)


def not_found(what: str) -> NotFoundError:
    """The platform's 404 -- a foreign-org id is indistinguishable from a missing one."""
    return NotFoundError(what)


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
    "CONTA_GATEWAY_DUPLICADA",
    "CONTA_INATIVA",
    "DOCUMENTO_INVALIDO",
    "ESTORNO_EXCEDE_PAGO",
    "FinanceError",
    "LANCAMENTO_CANCELADO",
    "LANCAMENTO_COM_BAIXA",
    "LANCAMENTO_DUPLICADO",
    "conflict",
    "invalid",
    "not_found",
]
