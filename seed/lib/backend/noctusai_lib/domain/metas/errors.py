"""Metas errors -- `AppException`s so the seed handlers render `{"error": {"code", "message", "details"}}`."""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

PERIODO_INVALIDO = "periodo_invalido"
PERIODO_FECHADO = "periodo_fechado"
PERIODO_DUPLICADO = "periodo_duplicado"
META_INVALIDA = "meta_invalida"
META_DUPLICADA = "meta_duplicada"
EQUIPE_INVALIDA = "equipe_invalida"
EQUIPE_DUPLICADA = "equipe_duplicada"
MEMBRO_DUPLICADO = "membro_duplicado"
EVENTO_INVALIDO = "evento_invalido"
REGRA_INVALIDA = "regra_invalida"
REGRA_DUPLICADA = "regra_duplicada"
CONFIGURACAO_INVALIDA = "configuracao_invalida"
FILTRO_INVALIDO = "filtro_invalido"
SEM_PERMISSAO = "sem_permissao"
FECHAMENTO_EXISTENTE = "fechamento_existente"


class MetasError(OrganError):
    """A metas refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(MetasError)


def forbidden(message: str) -> MetasError:
    return MetasError(SEM_PERMISSAO, message, 403)


__all__ = [
    "CONFIGURACAO_INVALIDA",
    "EQUIPE_DUPLICADA",
    "EQUIPE_INVALIDA",
    "EVENTO_INVALIDO",
    "FECHAMENTO_EXISTENTE",
    "FILTRO_INVALIDO",
    "MEMBRO_DUPLICADO",
    "META_DUPLICADA",
    "META_INVALIDA",
    "MetasError",
    "PERIODO_DUPLICADO",
    "PERIODO_FECHADO",
    "PERIODO_INVALIDO",
    "REGRA_DUPLICADA",
    "REGRA_INVALIDA",
    "SEM_PERMISSAO",
    "conflict",
    "forbidden",
    "invalid",
    "not_found",
]
