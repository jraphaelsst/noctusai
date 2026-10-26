"""Leads errors -- `AppException`s so the seed handlers render `{"error": {"code", "message", "details"}}`."""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

ETAPA_INVALIDA = "etapa_invalida"
ORIGEM_INVALIDA = "origem_invalida"
TELEFONE_INVALIDO = "telefone_invalido"
LEAD_DUPLICADO = "lead_duplicado"
FILTRO_INVALIDO = "filtro_invalido"


class LeadsError(OrganError):
    """A leads refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(LeadsError)


class LeadConflictError(Exception):
    """The store refused an insert: the (org, connection, chat) lead already exists (UNIQUE guard)."""


__all__ = [
    "ETAPA_INVALIDA",
    "FILTRO_INVALIDO",
    "LEAD_DUPLICADO",
    "LeadConflictError",
    "LeadsError",
    "ORIGEM_INVALIDA",
    "TELEFONE_INVALIDO",
    "conflict",
    "invalid",
    "not_found",
]
