"""Inventory errors -- `AppException` subclasses (stable pt-BR `code`s, rendered by the seed handlers).

The RPC refusal codes (raised inside Postgres) are the same constants: the service maps
`{"status": "refused", "code": ...}` straight onto `InventoryError(code, ...)`.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

ESTOQUE_INSUFICIENTE = "estoque_insuficiente"
DEPOSITO_INVALIDO = "deposito_invalido"
DEPOSITO_INATIVO = "deposito_inativo"
SEM_DEPOSITO_PADRAO = "sem_deposito_padrao"
DEPOSITO_DUPLICADO = "deposito_duplicado"
DEPOSITO_COM_ESTOQUE = "deposito_com_estoque"
ITEM_INVALIDO = "item_invalido"
SEM_RESERVA = "sem_reserva"
RESERVA_LIBERADA = "reserva_liberada"
RESERVA_CONSUMIDA = "reserva_consumida"
ABAIXO_RESERVADO = "abaixo_reservado"
QUANTIDADE_DIVERGENTE = "quantidade_divergente"
QUANTIDADE_INVALIDA = "quantidade_invalida"
CUSTO_INVALIDO = "custo_invalido"
TRANSFERENCIA_MESMO_DEPOSITO = "transferencia_mesmo_deposito"

#: Codes the RPCs may answer with; anything else is a bug and surfaces loudly.
RPC_REFUSAL_CODES = frozenset(
    {
        ESTOQUE_INSUFICIENTE,
        DEPOSITO_INVALIDO,
        DEPOSITO_INATIVO,
        SEM_DEPOSITO_PADRAO,
        ITEM_INVALIDO,
        SEM_RESERVA,
        RESERVA_LIBERADA,
        RESERVA_CONSUMIDA,
        ABAIXO_RESERVADO,
        QUANTIDADE_DIVERGENTE,
        QUANTIDADE_INVALIDA,
        CUSTO_INVALIDO,
        TRANSFERENCIA_MESMO_DEPOSITO,
    }
)

_MESSAGES = {
    ESTOQUE_INSUFICIENTE: "Estoque disponível insuficiente.",
    DEPOSITO_INVALIDO: "Depósito não encontrado.",
    DEPOSITO_INATIVO: "O depósito está inativo.",
    SEM_DEPOSITO_PADRAO: "Não há depósito padrão: informe o depósito ou cadastre um padrão.",
    ITEM_INVALIDO: "Item não encontrado.",
    SEM_RESERVA: "Não há reserva para este pedido/item.",
    RESERVA_LIBERADA: "A reserva já foi liberada.",
    RESERVA_CONSUMIDA: "A reserva já foi baixada (commit).",
    ABAIXO_RESERVADO: "A contagem ficaria abaixo da quantidade reservada.",
    QUANTIDADE_DIVERGENTE: "A quantidade difere da reserva.",
    QUANTIDADE_INVALIDA: "Quantidade inválida.",
    CUSTO_INVALIDO: "Custo unitário inválido.",
    TRANSFERENCIA_MESMO_DEPOSITO: "Origem e destino da transferência são o mesmo depósito.",
}


class InventoryError(AppException):
    """An inventory refusal carrying its stable machine `code`."""

    def __init__(
        self, code: str, message: str, status_code: int = 422, *, field: Optional[str] = None, details: Optional[dict] = None
    ) -> None:
        merged = dict(details or {})
        if field:
            merged["field"] = field
        super().__init__(code=code, message=message, status_code=status_code, details=merged)


def invalid(field: str, message: str, code: str = "invalid") -> InventoryError:
    return InventoryError(code, message, 422, field=field)


def conflict(code: str, message: str, **details) -> InventoryError:
    return InventoryError(code, message, 409, details=details)


def not_found(what: str) -> NotFoundError:
    """The platform's 404 -- a foreign-org id is indistinguishable from a missing one."""
    return NotFoundError(what)


def from_refusal(payload: dict) -> InventoryError:
    """Map an RPC `{"status": "refused", "code", "item_id"?}` onto the right HTTP error (409 stock, 422 input)."""
    code = str(payload.get("code") or "")
    if code not in RPC_REFUSAL_CODES:
        raise RuntimeError(f"inventory RPC answered an unknown refusal code {code!r}: {payload!r}")
    status = 409 if code in {ESTOQUE_INSUFICIENTE, ABAIXO_RESERVADO, RESERVA_LIBERADA, RESERVA_CONSUMIDA} else 422
    details = {k: payload[k] for k in ("item_id", "warehouse_id") if payload.get(k)}
    return InventoryError(code, _MESSAGES.get(code, code), status, details=details)


__all__ = [
    "ABAIXO_RESERVADO",
    "CUSTO_INVALIDO",
    "DEPOSITO_COM_ESTOQUE",
    "DEPOSITO_DUPLICADO",
    "DEPOSITO_INATIVO",
    "DEPOSITO_INVALIDO",
    "ESTOQUE_INSUFICIENTE",
    "ITEM_INVALIDO",
    "InventoryError",
    "QUANTIDADE_DIVERGENTE",
    "QUANTIDADE_INVALIDA",
    "RESERVA_CONSUMIDA",
    "RESERVA_LIBERADA",
    "RPC_REFUSAL_CODES",
    "SEM_DEPOSITO_PADRAO",
    "SEM_RESERVA",
    "TRANSFERENCIA_MESMO_DEPOSITO",
    "conflict",
    "from_refusal",
    "invalid",
    "not_found",
]
