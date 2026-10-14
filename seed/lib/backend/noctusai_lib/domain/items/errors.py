"""Items errors -- `AppException` subclasses rendered as `{"error": {"code", "message", "details"}}`."""
from __future__ import annotations

from typing import Optional

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

SKU_DUPLICADO = "sku_duplicado"
SKU_INVALIDO = "sku_invalido"
CATEGORIA_DUPLICADA = "categoria_duplicada"
CATEGORIA_EM_USO = "categoria_em_uso"
CATEGORIA_CICLO = "categoria_ciclo"
NCM_INVALIDO = "ncm_invalido"
CEST_INVALIDO = "cest_invalido"
CFOP_INVALIDO = "cfop_invalido"
ORIGEM_INVALIDA = "origem_invalida"
GTIN_INVALIDO = "gtin_invalido"
CAMPO_OBRIGATORIO = "campo_obrigatorio"
IMPORTACAO_INVALIDA = "importacao_invalida"
EXPORTACAO_GRANDE_DEMAIS = "exportacao_grande_demais"


class ItemsError(AppException):
    """An items refusal carrying its stable machine `code`."""

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


def invalid(field: str, message: str, code: str = "invalid") -> ItemsError:
    return ItemsError(code, message, 422, field=field)


def conflict(code: str, message: str, **details) -> ItemsError:
    return ItemsError(code, message, 409, details=details)


def not_found(what: str) -> NotFoundError:
    """A foreign-org id is indistinguishable from a missing one."""
    return NotFoundError(what)


__all__ = [
    "CAMPO_OBRIGATORIO",
    "CATEGORIA_CICLO",
    "CATEGORIA_DUPLICADA",
    "CATEGORIA_EM_USO",
    "CEST_INVALIDO",
    "CFOP_INVALIDO",
    "EXPORTACAO_GRANDE_DEMAIS",
    "GTIN_INVALIDO",
    "IMPORTACAO_INVALIDA",
    "ItemsError",
    "NCM_INVALIDO",
    "ORIGEM_INVALIDA",
    "SKU_DUPLICADO",
    "SKU_INVALIDO",
    "conflict",
    "invalid",
    "not_found",
]
