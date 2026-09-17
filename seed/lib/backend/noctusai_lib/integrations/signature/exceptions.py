"""Typed error taxonomy for the `signature` seed IO module — contract §1.2.

One base (`SignatureError`), plain `Exception` subclasses — NOT
`AppException`. A signature call can happen inside a request handler, a
background job, or the webhook receiver, so raising an HTTP-flavored
exception here would be the wrong shape (same rationale as
`noctusai_lib.integrations.live_rooms.errors.LiveRoomError`). The
product's router/service translates each of these to the endpoint's own
error taxonomy (contract §3.1's `codigo` / status table) — that mapping is
a different slice's job, not this module's.

🔴 No silent fallback. `ProvedorNaoConfigurado` is what a credential-less
org gets from `make_signature_adapter(real=True, ...)` — there is no
`_enviar_interno` and no adapter here ever returns a Fake envelope dressed
up as real (F1: the DocuSign scaffold this replaces did exactly that,
returning `"dry_run": False` from a mock).
"""
from __future__ import annotations

from typing import Optional, Sequence


class SignatureError(Exception):
    """Base class for every `signature` adapter error.

    Args:
        message: human-readable detail (English, this is a library
            exception — the pt-BR user-facing message is the consuming
            product's job).
        provedor: which provider raised this ("d4sign").
        details: structured extra context a catcher can fold into its own
            error response `details` dict (e.g. `{"faltando": [...]}`,
            `{"provedor_mensagem": "..."}`) without re-parsing the message.
    """

    def __init__(
        self,
        message: str,
        *,
        provedor: str = "d4sign",
        details: Optional[dict] = None,
    ) -> None:
        self.provedor = provedor
        self.details = details or {}
        super().__init__(message)


class ProvedorNaoConfigurado(SignatureError):
    """Credentials absent for this org/provider.

    Raised by `make_signature_adapter` — it never returns a Fake in
    `real=True` mode. `faltando` names WHICH credential keys are missing
    (e.g. `["d4sign_api_token", "d4sign_safe_uuid"]`), mirrored into
    `details["faltando"]` so a catcher doesn't need to know this
    exception's Python shape to render it.
    """

    def __init__(self, faltando: Sequence[str], *, provedor: str = "d4sign") -> None:
        self.faltando = list(faltando)
        message = (
            f"{provedor}: credenciais ausentes: {', '.join(self.faltando)}"
        )
        super().__init__(message, provedor=provedor, details={"faltando": self.faltando})


class WebhookInvalido(SignatureError):
    """The webhook's signature header is missing, malformed, or does not
    verify — or the (already-authenticated) body could not be parsed into
    an `EventoAssinatura`. `validar_webhook` raises this; it never returns
    None."""


class DocumentoAssinadoIndisponivel(SignatureError):
    """`baixar_assinado` was called before the envelope reached
    `status == "concluido"`."""


class ProvedorIndisponivel(SignatureError):
    """Transport failure, timeout, or a 5xx from the provider — the
    provider itself is unreachable/broken, not rejecting the request."""


class EnvelopeRecusado(SignatureError):
    """The provider answered with a 4xx — the request itself was
    rejected. `details["provedor_mensagem"]` carries the provider's own
    error text when one was returned."""

    def __init__(
        self,
        message: str,
        *,
        provedor: str = "d4sign",
        provedor_mensagem: Optional[str] = None,
    ) -> None:
        super().__init__(
            message,
            provedor=provedor,
            details={"provedor_mensagem": provedor_mensagem},
        )


__all__ = [
    "DocumentoAssinadoIndisponivel",
    "EnvelopeRecusado",
    "ProvedorIndisponivel",
    "ProvedorNaoConfigurado",
    "SignatureError",
    "WebhookInvalido",
]
