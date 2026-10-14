"""Parties errors -- `AppException` subclasses so the seed's handlers render
`{"error": {"code", "message", "details"}}` with the right status. pt-BR codes are constants so
tests and the frontend organ never retype the string.
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found

DOCUMENTO_INVALIDO = "documento_invalido"
DOCUMENTO_DUPLICADO = "documento_duplicado"
PARCEIRO_EM_USO = "parceiro_em_uso"
EMAIL_INVALIDO = "email_invalido"
TELEFONE_INVALIDO = "telefone_invalido"
PAPEL_INVALIDO = "papel_invalido"
IMPORTACAO_INVALIDA = "importacao_invalida"
IMPORTACAO_GRANDE_DEMAIS = "importacao_grande_demais"
EXPORTACAO_GRANDE_DEMAIS = "exportacao_grande_demais"


class PartiesError(OrganError):
    """A parties refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(PartiesError)


__all__ = [
    "DOCUMENTO_DUPLICADO",
    "DOCUMENTO_INVALIDO",
    "EMAIL_INVALIDO",
    "EXPORTACAO_GRANDE_DEMAIS",
    "IMPORTACAO_GRANDE_DEMAIS",
    "IMPORTACAO_INVALIDA",
    "PAPEL_INVALIDO",
    "PARCEIRO_EM_USO",
    "PartiesError",
    "TELEFONE_INVALIDO",
    "conflict",
    "invalid",
    "not_found",
]
