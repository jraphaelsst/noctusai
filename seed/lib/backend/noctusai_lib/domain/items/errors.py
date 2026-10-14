"""Items errors -- `AppException` subclasses rendered as `{"error": {"code", "message", "details"}}`."""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

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


class ItemsError(OrganError):
    """An items refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(ItemsError)


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
