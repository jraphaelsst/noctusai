"""Engagement HTTP-layer errors (`AppException`s -> the `{"error": {...}}` envelope). Domain rule errors stay
`EngagementRuleError` (raised for a malformed rule config only)."""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

REGRA_INVALIDA = "regra_invalida"
REGRA_DUPLICADA = "regra_duplicada"
EVENTO_INVALIDO = "evento_invalido"
FILTRO_INVALIDO = "filtro_invalido"
SEM_PERMISSAO = "sem_permissao"


class EngagementError(OrganError):
    """An engagement refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(EngagementError)


def forbidden(message: str) -> EngagementError:
    return EngagementError(SEM_PERMISSAO, message, 403)


__all__ = [
    "EVENTO_INVALIDO", "EngagementError", "FILTRO_INVALIDO", "REGRA_DUPLICADA", "REGRA_INVALIDA", "SEM_PERMISSAO",
    "conflict", "forbidden", "invalid", "not_found",
]
