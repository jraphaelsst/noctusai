"""Parties errors -- `AppException` subclasses so the seed's handlers render
`{"error": {"code", "message", "details"}}` with the right status. pt-BR codes are constants so
tests and the frontend organ never retype the string.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.primitives.exceptions import AppException, NotFoundError

DOCUMENTO_INVALIDO = "documento_invalido"
DOCUMENTO_DUPLICADO = "documento_duplicado"
PARCEIRO_EM_USO = "parceiro_em_uso"
EMAIL_INVALIDO = "email_invalido"
TELEFONE_INVALIDO = "telefone_invalido"
PAPEL_INVALIDO = "papel_invalido"
IMPORTACAO_INVALIDA = "importacao_invalida"
IMPORTACAO_GRANDE_DEMAIS = "importacao_grande_demais"
EXPORTACAO_GRANDE_DEMAIS = "exportacao_grande_demais"


class PartiesError(AppException):
    """A parties refusal carrying its stable machine `code`."""

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


def invalid(field: str, message: str, code: str = "invalid") -> PartiesError:
    return PartiesError(code, message, 422, field=field)


def conflict(code: str, message: str, **details) -> PartiesError:
    return PartiesError(code, message, 409, details=details)


def not_found(what: str) -> NotFoundError:
    """The platform's 404 -- a foreign-org id is indistinguishable from a missing one."""
    return NotFoundError(what)


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
