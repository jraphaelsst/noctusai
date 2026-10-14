"""Commerce errors — `AppException` subclasses so the seed's exception handlers
render them as `{"error": {"code", "message", "details"}}` with the right status.

The three CONTRACT-pinned codes are constants so a test (and the frontend
organ) never retypes the string.
"""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories, not_found
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured

CNPJ_INVALIDO = "cnpj_invalido"
VERSAO_CONFLITANTE = "versao_conflitante"
ACEITE_OBRIGATORIO = "aceite_obrigatorio"


class CommerceError(OrganError):
    """A commerce refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(CommerceError)


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
