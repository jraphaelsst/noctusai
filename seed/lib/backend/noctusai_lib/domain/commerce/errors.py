"""Commerce errors — `AppException` subclasses so the seed's exception handlers
render them as `{"error": {"code", "message", "details"}}` with the right status.

The three CONTRACT-pinned codes are constants so a test (and the frontend
organ) never retypes the string.
"""
from __future__ import annotations

from typing import Optional

from noctusai_lib.primitives.exceptions import AppException, NotFoundError
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

CNPJ_INVALIDO = "cnpj_invalido"
VERSAO_CONFLITANTE = "versao_conflitante"
ACEITE_OBRIGATORIO = "aceite_obrigatorio"


class CommerceError(AppException):
    """A commerce refusal carrying its stable machine `code`."""

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


def invalid(field: str, message: str, code: str = "invalid") -> CommerceError:
    return CommerceError(code, message, 422, field=field)


def conflict(code: str, message: str, **details) -> CommerceError:
    return CommerceError(code, message, 409, details=details)


def not_found(what: str) -> NotFoundError:
    """The platform's 404 (`NOT_FOUND`, pt-BR gendered message) -- same shape as every other organ."""
    return NotFoundError(what)


class GatewayNotConfigured(Exception, IntegrationNotConfigured):
    """The org has no usable payment gateway credentials (checkout answers 503)."""


__all__ = [
    "ACEITE_OBRIGATORIO",
    "CNPJ_INVALIDO",
    "CommerceError",
    "GatewayNotConfigured",
    "VERSAO_CONFLITANTE",
    "conflict",
    "invalid",
    "not_found",
]
